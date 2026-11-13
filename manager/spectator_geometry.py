"""Bounded, latest-only JKSG geometry transport, independent of image capture."""
from __future__ import annotations

import asyncio
import math
import socket
import struct
import time

HEADER = struct.Struct("<4s15I")
VERTEX = struct.Struct("<4f4B")
MAX_WIDTH, MAX_HEIGHT = 640, 360
MAX_VERTICES, MAX_INDICES, MAX_PAYLOAD = 65536, 196608, 2097152


def inactive_geometry(reason="Geometry capture is unavailable."):
    return {"available": False, "frame_available": False, "sequence": 0,
            "age_ms": None, "reason": reason, "profile": "flat-colour-v1"}


def validate_header(header):
    values = HEADER.unpack(header)
    magic, version, width, height, world, control, sequence, size, flags, age, vertices, indices, *reserved = values
    if (magic != b"JKSG" or version != 1 or not 1 <= width <= MAX_WIDTH or
            not 1 <= height <= MAX_HEIGHT or not world or not control or not sequence or flags or
            any(reserved) or vertices > MAX_VERTICES or indices > MAX_INDICES or indices % 3 or
            bool(vertices) != bool(indices) or size != vertices * VERTEX.size + indices * 4 or size > MAX_PAYLOAD):
        raise ValueError("Invalid bounded geometry frame envelope.")
    return {"world_epoch": world, "control_epoch": control, "sequence": sequence,
            "width": width, "height": height, "capture_age_ms": age,
            "vertex_count": vertices, "index_count": indices, "size": size}


def validate_payload(value, payload):
    vertex_bytes = value["vertex_count"] * VERTEX.size
    view = memoryview(payload)
    for vertex in VERTEX.iter_unpack(view[:vertex_bytes]):
        if any(not math.isfinite(number) for number in vertex[:4]) or vertex[7] != 255:
            raise ValueError("Invalid geometry vertex attributes.")
    if any(index >= value["vertex_count"] for (index,) in struct.iter_unpack("<I", view[vertex_bytes:])):
        raise ValueError("Invalid geometry triangle index.")


class GeometryChannel:
    def __init__(self, current_epochs):
        self.current_epochs = current_epochs
        self.parent = self.child = None
        self.latest = self.error = None
        self.task = None

    def prepare(self, environment):
        self.parent, self.child = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        self.parent.setblocking(False)
        self.child.setblocking(False)
        environment["OPENJKDF2_SPECTATOR_GEOMETRY_FD"] = str(self.child.fileno())
        self.task = asyncio.create_task(self._read_frames(), name="spectator-geometry")
        return self.child.fileno()

    def spawned(self):
        if self.child is not None:
            self.child.close()
            self.child = None

    async def _read_exact(self, size):
        parts = bytearray()
        while size:
            part = await asyncio.get_running_loop().sock_recv(self.parent, size)
            if not part:
                raise ConnectionError("The geometry channel closed.")
            parts.extend(part)
            size -= len(part)
        return bytes(parts)

    async def _read_frames(self):
        try:
            while True:
                first = await self._read_exact(1)
                started = time.monotonic()
                header = first + await self._read_exact(HEADER.size - 1)
                value = validate_header(header)  # Bound before reading/allocating payload.
                payload = await self._read_exact(value["size"])
                validate_payload(value, payload)
                value.update(header=header, payload=payload,
                             captured_at=started - value["capture_age_ms"] / 1000)
                if (value["world_epoch"], value["control_epoch"]) != self.current_epochs():
                    continue
                previous = self.latest
                if previous and (value["world_epoch"], value["control_epoch"], value["sequence"]) <= (
                        previous["world_epoch"], previous["control_epoch"], previous["sequence"]):
                    continue
                self.latest = value
        except asyncio.CancelledError:
            raise
        except (OSError, ValueError, struct.error) as exc:
            self.error = str(exc)
            self.latest = None
            if self.parent is not None:
                self.parent.close()

    async def close(self):
        self.latest = None
        if self.task:
            self.task.cancel()
        for channel in (self.parent, self.child):
            if channel is not None:
                channel.close()
        if self.task:
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None

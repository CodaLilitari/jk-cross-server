"""Authenticated camera control and latest-only independent image/geometry capture."""
from __future__ import annotations
import asyncio
import math
import os
import socket
import struct
import time

from .spectator_geometry import GeometryChannel, inactive_geometry

FRAME_HEADER = struct.Struct("<4s8I")
MAX_WIDTH, MAX_HEIGHT = 640, 360
MAX_PIXELS = MAX_WIDTH * MAX_HEIGHT * 4
MODES = ("off", "free", "follow")
REASONS = ("", "Observer rendering is unavailable.", "Waiting for the game world.",
           "The followed player left.", "The camera is outside the world.",
           "The frame channel closed.", "Observer rendering failed.", "View is closed.")
VIEWER_LEASE, STATE_MAX_AGE, FRAME_MAX_AGE = 5.0, 2.5, 2.0


class SpectatorError(RuntimeError):
    def __init__(self, message, status=503):
        super().__init__(message)
        self.status = status


def inactive_status(configured):
    return {"rendering_configured": configured, "available": False, "enabled": False,
            "mode": "off", "state": "stopped", "reason": "Start the server to use the host view." if configured else
            "Enable spectator rendering and restart the session to prepare the host view.",
            "restart_required": not configured, "world_epoch": 0, "control_epoch": 0,
            "target": None, "players": [], "frame": {"available": False, "sequence": 0,
            "width": 0, "height": 0, "age_ms": None}, "pose": None, "geometry": inactive_geometry()}


def uint32(value, name, *, allow_zero=False):
    if type(value) is not int or not (0 if allow_zero else 1) <= value <= 0xffffffff:
        raise ValueError(f"{name} must be a {'nonnegative' if allow_zero else 'positive'} uint32 integer.")
    return value


class SpectatorController:
    def __init__(self, ipc, configured, session_ready):
        self.ipc, self.configured, self.session_ready = ipc, configured, session_ready
        self._native = self._latest = None
        self._state_at = self._roster_at = 0.
        self._control_error = self._frame_error = None
        self._parent = self._child = None
        self._tasks = []
        self._lock = asyncio.Lock()
        self._geometry = GeometryChannel(lambda: (self._native["world_epoch"], self._native["control_epoch"])
                                         if self._native else None)
        self._geometry_control_error = None
        self._geometry_renewed_at = 0.
        self._geometry_renewed_epochs = None
        self._closed = False
        self._viewer_deadline = None
        self._last_input = 0
        self._unsubscribe = ipc.subscribe_state(self._connection_state)

    def prepare_launch(self, environment):
        environment.pop("OPENJKDF2_SPECTATOR_FD", None)
        environment.pop("OPENJKDF2_SPECTATOR_GEOMETRY_FD", None)
        if not self.configured:
            return ()
        if os.name == "nt":
            self._frame_error = "The inherited host-view channel currently requires a Unix server."
            return ()
        self._parent, self._child = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        self._parent.setblocking(False)
        self._child.setblocking(False)
        environment["OPENJKDF2_SPECTATOR_FD"] = str(self._child.fileno())
        self._tasks.append(asyncio.create_task(self._read_frames(), name="spectator-frames"))
        geometry_fds = ()
        try:
            geometry_fds = (self._geometry.prepare(environment),)
        except OSError as exc:
            self._geometry.error = f"The geometry channel could not be prepared: {exc}"
        return (self._child.fileno(),) + geometry_fds

    def spawned(self):
        self._geometry.spawned()
        if self._child is not None:
            self._child.close()
            self._child = None

    def start(self):
        if self.configured and not self._closed:
            self._tasks.append(asyncio.create_task(self._poll(), name="spectator-status"))

    def _connection_state(self, connected):
        if not connected:
            self._geometry.latest = None
            self._geometry_renewed_epochs = None
            self._native = self._latest = None
            self._state_at = self._roster_at = 0.
            self._viewer_deadline = None
            self._last_input = 0
            self._control_error = "The observer connection ended."

    async def _read_exact(self, size):
        chunks, remaining = [], size
        while remaining:
            chunk = await asyncio.get_running_loop().sock_recv(self._parent, remaining)
            if not chunk:
                raise ConnectionError("The frame channel closed.")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    async def _read_frames(self):
        try:
            while not self._closed:
                magic, version, width, height, world, control, sequence, size, flags = FRAME_HEADER.unpack(
                    await self._read_exact(FRAME_HEADER.size))
                if (magic != b"JKSV" or version != 1 or flags or not world or not control or not sequence or
                        not 1 <= width <= MAX_WIDTH or not 1 <= height <= MAX_HEIGHT or
                        size != width * height * 4 or size > MAX_PIXELS):
                    raise ValueError("Invalid bounded RGBA frame envelope.")
                pixels = await self._read_exact(size)
                incoming = {"world_epoch": world, "control_epoch": control, "sequence": sequence,
                            "width": width, "height": height, "pixels": pixels, "received": time.monotonic()}
                old = self._latest
                if old and (world, control, sequence) <= (old["world_epoch"], old["control_epoch"], old["sequence"]):
                    continue
                # One completed frame replaces the previous one; no disk/queue.
                self._latest = incoming
        except asyncio.CancelledError:
            raise
        except (OSError, ValueError, struct.error) as exc:
            self._frame_error = str(exc)
            self._latest = None
            if self._parent is not None:
                self._parent.close()

    def _fresh(self):
        return bool(not self._closed and self.ipc.connected and self._native and
                    time.monotonic() - self._state_at <= STATE_MAX_AGE and not self._control_error)

    def _frame(self):
        value, native = self._latest, self._native
        if (not self._fresh() or self._frame_error or not self.session_ready() or not value or not native["mode"] or
                native["capabilities"] & 3 != 3 or not native["flags"] & 1 or native["flags"] & 64 or
                (value["world_epoch"], value["control_epoch"]) != (native["world_epoch"], native["control_epoch"]) or
                time.monotonic() - value["received"] > FRAME_MAX_AGE):
            return None
        # Receipt time alone cannot freshen an old frame left in a socket
        # buffer while the event loop was delayed. Compare native capture age.
        if (value["sequence"] < native["frame_sequence"] or
                (value["sequence"] == native["frame_sequence"] and
                 native["frame_age_ms"] / 1000 + time.monotonic() - self._state_at > FRAME_MAX_AGE)):
            return None
        return value

    def status(self):
        result = inactive_status(self.configured)
        if not self.configured:
            return result
        native, fresh = self._native, self._fresh()
        result["geometry"] = self._geometry_status()
        result["state"] = "unavailable"
        result["reason"] = self._frame_error or self._control_error or "Waiting for observer capabilities."
        if not native or not fresh:
            return result
        available = bool(native["capabilities"] & 3 == 3 and not self._frame_error and not native["flags"] & 64)
        enabled = bool(native["mode"] and native["flags"] & 32)
        result.update(available=available, enabled=enabled, mode=MODES[native["mode"]],
                      state="active" if enabled else "off", reason=self._frame_error or REASONS[native["reason"]],
                      world_epoch=native["world_epoch"], control_epoch=native["control_epoch"],
                      target={"peer_id": native["target_peer"], "generation": native["target_generation"]}
                             if native["mode"] == 2 else None,
                      players=native["players"], pose=native["pose"])
        if not available:
            result.update(state="unavailable", reason=result["reason"] or "This engine has no prepared observer context.")
        elif enabled and not native["flags"] & 1:
            result["state"] = "waiting"
        frame = self._frame()
        if frame:
            result["frame"] = {"available": True, "sequence": frame["sequence"], "width": frame["width"],
                               "height": frame["height"], "age_ms": round((time.monotonic() - frame["received"]) * 1000)}
        return result

    def _apply(self, native):
        if self._closed:
            raise SpectatorError("The observer session ended.")
        previous = self._native
        if previous and (native["world_epoch"], native["control_epoch"]) < (previous["world_epoch"], previous["control_epoch"]):
            return
        if native["operation"] != 0:
            native["players"] = previous["players"] if previous and previous["world_epoch"] == native["world_epoch"] else []
        changed = previous is None or (native["world_epoch"], native["control_epoch"]) != (previous["world_epoch"], previous["control_epoch"])
        if changed:
            self._last_input = 0
            self._geometry_renewed_epochs = None
            self._geometry_control_error = None
            self._geometry.latest = None
            if self._latest and (self._latest["world_epoch"], self._latest["control_epoch"]) != (native["world_epoch"], native["control_epoch"]):
                self._latest = None
        self._native, self._state_at, self._control_error = native, time.monotonic(), None
        if native["operation"] == 0:
            self._roster_at = self._state_at
        if not native["mode"]:
            self._geometry.latest = None
            self._latest, self._viewer_deadline = None, None

    async def _call_locked(self, operation, **kwargs):
        try:
            native = await self.ipc.spectator_request(operation, **kwargs)
        except (ConnectionError, RuntimeError, asyncio.TimeoutError) as exc:
            self._control_error = str(exc) or "Observer status timed out."
            self._latest = None
            raise SpectatorError(self._control_error) from None
        self._apply(native)
        result = native["result"]
        if result:
            messages = {1: "The observer rejected the request.", 2: "The observer world or control epoch changed.",
                        3: "The selected player is no longer available.", 4: "Observer rendering is unavailable.",
                        5: "Free-camera input requires free mode."}
            raise SpectatorError(messages[result], 409 if result in (2, 3, 5) else 503)
        return self.status()

    async def refresh(self):
        if not self.configured:
            return self.status()
        if self._closed or not self.ipc.connected:
            raise SpectatorError("The observer is not connected.")
        async with self._lock:
            return await self._call_locked(0)

    def _epochs(self, value):
        for name in ("world_epoch", "control_epoch"):
            uint32(value[name], name, allow_zero=True)
        native = self._native
        if not self._fresh() or not native or (value["world_epoch"], value["control_epoch"]) != (native["world_epoch"], native["control_epoch"]):
            raise SpectatorError("The observer world or control epoch changed; refresh the view controls.", 409)

    async def configure(self, value):
        if not isinstance(value, dict) or set(value) != {"world_epoch", "control_epoch", "mode", "target"}:
            raise ValueError("Observer configuration accepts epochs, mode and target only.")
        if value["mode"] not in MODES:
            raise ValueError("Observer mode must be off, free or follow.")
        peer, generation = 0, 0
        if value["mode"] == "follow":
            target = value["target"]
            if not isinstance(target, dict) or set(target) != {"peer_id", "generation"}:
                raise ValueError("A follow target needs its peer_id and generation.")
            peer, generation = uint32(target["peer_id"], "peer_id"), uint32(target["generation"], "generation")
            if peer < 2:
                raise ValueError("The host is not a follow target.")
        elif value["target"] is not None:
            raise ValueError("Off/free mode does not accept a player target.")
        async with self._lock:
            self._epochs(value)
            if value["mode"] != "off" and (not self.status()["available"] or not self.session_ready()):
                raise SpectatorError("The game session or observer context is not ready.")
            # Native may apply the mutation even when its reply is lost. Bound
            # that possible view before sending; status/input cannot renew it.
            if value["mode"] != "off" and (self._viewer_deadline is None or self._viewer_deadline <= time.monotonic()):
                self._viewer_deadline = time.monotonic() + VIEWER_LEASE
            return await self._call_locked(1, world_epoch=value["world_epoch"], control_epoch=value["control_epoch"],
                                           mode=MODES.index(value["mode"]), peer_id=peer, generation=generation)

    async def input(self, value):
        keys = {"world_epoch", "control_epoch", "sequence", "forward", "right", "up", "yaw_delta", "pitch_delta"}
        if not isinstance(value, dict) or set(value) != keys:
            raise ValueError("Supply only observer epochs, sequence and five camera input values.")
        sequence = uint32(value["sequence"], "sequence")
        axes = tuple(value[key] for key in ("forward", "right", "up", "yaw_delta", "pitch_delta"))
        if (any(type(number) not in (int, float) or not math.isfinite(number) for number in axes) or
                any(abs(number) > 1 for number in axes[:3]) or any(abs(number) > math.pi for number in axes[3:])):
            raise ValueError("Camera input must be finite: axes -1..1 and look deltas -pi..pi radians.")
        if self._lock.locked():
            raise SpectatorError("Observer controls are busy; send the latest input again.", 429)
        async with self._lock:
            self._epochs(value)
            if self._native["mode"] != 1 or sequence <= self._last_input or not self.session_ready():
                raise SpectatorError("Free-camera mode or its input sequence changed.", 409)
            if self._viewer_deadline is None or self._viewer_deadline <= time.monotonic():
                raise SpectatorError("The viewer lease expired; reopen the view.", 409)
            result = await self._call_locked(2, world_epoch=value["world_epoch"], control_epoch=value["control_epoch"],
                                             sequence=sequence, axes=axes)
            self._last_input = sequence
            return result

    def frame(self, *, after=0, world_epoch=None, control_epoch=None):
        uint32(after, "after", allow_zero=True)
        if world_epoch is not None or control_epoch is not None:
            if world_epoch is None or control_epoch is None:
                raise ValueError("Supply both world_epoch and control_epoch.")
            self._epochs({"world_epoch": world_epoch, "control_epoch": control_epoch})
        status = self.status()
        if not status["available"] or not status["enabled"] or not self.session_ready():
            raise SpectatorError(status["reason"] or "Open a ready observer view first.")
        if self._viewer_deadline is None or self._viewer_deadline <= time.monotonic():
            raise SpectatorError("The viewer lease expired; reopen the view.", 409)
        # Authenticated image fetching renews the shared viewer lease.
        self._viewer_deadline = time.monotonic() + VIEWER_LEASE
        frame = self._frame()
        return frame if frame and frame["sequence"] > after else None

    def _geometry_frame(self):
        value, native = self._geometry.latest, self._native
        if (not self._fresh() or self._geometry.error or self._geometry_control_error or
                not self.session_ready() or not native["mode"] or not native["flags"] & 32 or
                native["capabilities"] & 19 != 19 or not native["flags"] & 1 or native["flags"] & 64 or
                not value or (value["world_epoch"], value["control_epoch"]) !=
                (native["world_epoch"], native["control_epoch"]) or
                value["sequence"] < native["frame_sequence"]):
            return None
        age = self._geometry_age(value)
        return value if age <= FRAME_MAX_AGE * 1000 else None

    def _geometry_age(self, value):
        now = time.monotonic()
        age = (now - value["captured_at"]) * 1000
        native = self._native
        if native and value["sequence"] == native["frame_sequence"]:
            age = max(age, native["frame_age_ms"] + (now - self._state_at) * 1000)
        return age

    def _geometry_status(self):
        native = self._native
        reason = self._geometry.error or self._geometry_control_error
        available = bool(self._fresh() and native["capabilities"] & 19 == 19 and
                         self._geometry.parent is not None and not reason)
        if not reason:
            reason = ("" if available else "This engine has no prepared geometry channel.")
        result = inactive_geometry(reason)
        result["available"] = available
        frame = self._geometry_frame()
        if frame:
            result.update(frame_available=True, sequence=frame["sequence"], age_ms=round(self._geometry_age(frame)))
        return result

    async def geometry(self, *, after=0, world_epoch=None, control_epoch=None):
        uint32(after, "after", allow_zero=True)
        if world_epoch is None or control_epoch is None:
            raise ValueError("Geometry fetch requires both world_epoch and control_epoch.")
        async with self._lock:
            self._epochs({"world_epoch": world_epoch, "control_epoch": control_epoch})
            native = self._native
            if not self._geometry_status()["available"]:
                raise SpectatorError(self._geometry_status()["reason"])
            if (not self.session_ready() or not native["mode"] or not native["flags"] & 32 or
                    not native["flags"] & 1 or native["flags"] & 64):
                raise SpectatorError("Open a ready observer view before requesting geometry.")
            if self._viewer_deadline is None or self._viewer_deadline <= time.monotonic():
                raise SpectatorError("The viewer lease expired; reopen the view.", 409)
            epochs = (world_epoch, control_epoch)
            if self._geometry_renewed_epochs != epochs or time.monotonic() - self._geometry_renewed_at >= 1:
                self._geometry_renewed_epochs, self._geometry_renewed_at = epochs, time.monotonic()
                try:
                    reply = await self.ipc.spectator_request(3, world_epoch=world_epoch,
                            control_epoch=control_epoch, geometry_enabled=1)
                except (ConnectionError, RuntimeError, asyncio.TimeoutError) as exc:
                    self._geometry_control_error = str(exc) or "Geometry activation timed out."
                    self._geometry.latest = None
                    raise SpectatorError(self._geometry_control_error) from None
                self._apply(reply)
                if reply["result"]:
                    self._geometry.latest = None
                    if reply["result"] == 2:
                        raise SpectatorError("The observer world or control epoch changed.", 409)
                    self._geometry_control_error = "Geometry activation was rejected."
                    raise SpectatorError(self._geometry_control_error)
                self._epochs({"world_epoch": world_epoch, "control_epoch": control_epoch})
            self._viewer_deadline = time.monotonic() + VIEWER_LEASE
            value = self._geometry_frame()
            if not value or value["sequence"] <= after:
                return None
            # Recompute at delivery; include transfer time and matching native capture age.
            age = math.ceil(self._geometry_age(value))
            if age > FRAME_MAX_AGE * 1000:
                return None
            header = value["header"]
            return header[:36] + struct.pack("<I", age) + header[40:] + value["payload"]

    async def _poll(self):
        while not self._closed:
            try:
                if self.ipc.connected and not self._lock.locked():
                    async with self._lock:
                        if self._viewer_deadline is not None and self._viewer_deadline <= time.monotonic():
                            await self._call_locked(0)
                            if self._native["mode"]:
                                await self._call_locked(1, world_epoch=self._native["world_epoch"],
                                                        control_epoch=self._native["control_epoch"], mode=0)
                        elif time.monotonic() - self._roster_at >= .5:
                            await self._call_locked(0)
            except SpectatorError:
                pass
            await asyncio.sleep(.25)

    async def close(self):
        self._closed = True
        self._unsubscribe()
        await self._geometry.close()
        self._native = self._latest = None
        self._viewer_deadline = None
        for task in self._tasks:
            task.cancel()
        for channel in (self._parent, self._child):
            if channel is not None:
                channel.close()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

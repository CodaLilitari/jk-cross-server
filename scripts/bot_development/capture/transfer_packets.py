#!/usr/bin/env python3
"""Transport caller-selected artifacts as bounded, hashed JSON packets.

This has no network or service-specific transport. A receiver verifies per-packet
bounds and hashes, then checks the independently supplied total size and digest.
"""
import argparse
import base64
import contextlib
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

MAX_PACKET = 1024 * 1024


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def chunk(path, offset, size):
    total = path.stat().st_size
    if not 0 <= offset < total or not 1 <= size <= MAX_PACKET:
        raise ValueError("Invalid offset or packet size")
    with path.open("rb") as stream:
        stream.seek(offset)
        data = stream.read(min(size, total - offset))
    if len(data) != min(size, total - offset):
        raise OSError("Input changed during packet read")
    return {"offset": offset, "bytes": len(data), "total": total,
            "sha256": hashlib.sha256(data).hexdigest(),
            "base64": base64.b64encode(data).decode("ascii")}


def unpack_packet(packet):
    offset, size, total = (packet[k] for k in ("offset", "bytes", "total"))
    if not (type(offset) is int and type(size) is int and type(total) is int
            and 0 <= offset < total and 1 <= size <= MAX_PACKET and offset + size <= total):
        raise ValueError("Invalid packet bounds")
    data = base64.b64decode(packet["base64"], validate=True)
    if len(data) != size or hashlib.sha256(data).hexdigest() != packet["sha256"]:
        raise ValueError("Packet digest or size mismatch")
    return offset, total, data


def pack(source, output, size):
    expected = digest(source)
    total = source.stat().st_size
    if total == 0:
        raise ValueError("Empty files do not have bounded transfer packets")
    with output.open("x", encoding="utf-8") as stream:
        for offset in range(0, total, size):
            stream.write(json.dumps(chunk(source, offset, size)) + "\n")
    if source.stat().st_size != total or digest(source) != expected:
        raise ValueError("Source changed during export; discard the packet file")
    return {"bytes": total, "sha256": expected, "packets": (total + size - 1) // size}


def unpack(source, output, total, expected):
    if total <= 0 or len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise ValueError("Expected positive size and lowercase SHA-256")
    if output.exists():
        if output.stat().st_size == total and digest(output) == expected:
            return {"bytes": total, "sha256": expected, "already_present": True}
        raise FileExistsError("Conflicting destination already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix="packet-", suffix=".partial", dir=output.parent, delete=False) as dest:
            temporary = Path(dest.name)
            size = 0
            full = hashlib.sha256()
            source_context = contextlib.nullcontext(sys.stdin) if source == "-" else Path(source).open(encoding="utf-8")
            with source_context as stream:
                for line in stream:
                    if not line.strip():
                        continue
                    offset, packet_total, data = unpack_packet(json.loads(line))
                    if offset != size or packet_total != total:
                        raise ValueError("Missing, duplicated, reordered or inconsistent packet")
                    dest.write(data)
                    full.update(data)
                    size += len(data)
            if size != total or full.hexdigest() != expected:
                raise ValueError("Full artifact size or digest mismatch")
            dest.flush()
            os.fsync(dest.fileno())
        if output.exists():
            raise FileExistsError("Destination appeared during transfer")
        # Atomic no-clobber install on the destination filesystem.
        os.link(temporary, output)
        if digest(output) != expected:
            raise ValueError("Installed artifact failed readback")
        return {"bytes": total, "sha256": expected, "already_present": False}
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    one = sub.add_parser("chunk", help="Print one bounded packet as JSON")
    one.add_argument("source", type=Path)
    one.add_argument("--offset", required=True, type=int)
    one.add_argument("--size", type=int, default=MAX_PACKET)
    export = sub.add_parser("pack", help="Write all packets to a new JSONL file")
    export.add_argument("source", type=Path)
    export.add_argument("packets", type=Path)
    export.add_argument("--size", type=int, default=MAX_PACKET)
    receive = sub.add_parser("unpack", help="Verify and install complete JSONL packets; '-' reads stdin")
    receive.add_argument("packets")
    receive.add_argument("output", type=Path)
    receive.add_argument("--bytes", type=int, required=True)
    receive.add_argument("--sha256", required=True)
    args = parser.parse_args()
    if args.action in ("chunk", "pack") and not 1 <= args.size <= MAX_PACKET:
        parser.error("Packet size must be 1..1048576 bytes")
    if args.action == "chunk":
        result = chunk(args.source, args.offset, args.size)
    elif args.action == "pack":
        result = pack(args.source, args.packets, args.size)
    else:
        result = unpack(args.packets, args.output, args.bytes, args.sha256)
    print(json.dumps(result))


if __name__ == "__main__":
    main()

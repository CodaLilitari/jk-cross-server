"""Private stdio protocol for an isolated trusted-local executable policy."""
import base64
import hashlib
import json
import os
from pathlib import Path
import sys

MAX_SOURCE = 192 * 1024
MAX_PACKET = 320 * 1024
MAX_DECISION = 24 * 1024


def encode(value, maximum=MAX_PACKET):
    raw = json.dumps(value, allow_nan=False, separators=(",", ":")).encode("utf-8") + b"\n"
    if len(raw) > maximum:
        raise ValueError("Packet exceeds bound")
    return raw


def read(stream, maximum):
    raw = stream.readline(maximum + 1)
    if not raw or len(raw) > maximum or not raw.endswith(b"\n"):
        raise ValueError("Incomplete or excessive worker packet")
    value = json.loads(raw)
    # parse_constant alone does not guard overflowing exponents like 1e999.
    encode(value, maximum)
    return value


def main():
    # Preserve the protocol pipes, including on Windows where select() cannot
    # watch anonymous subprocess pipes. Policy prints and input() use NUL.
    with os.fdopen(os.dup(0), "rb") as inbound, os.fdopen(os.dup(1), "wb", buffering=0) as outbound:
        with open(os.devnull, "r+b") as null:
            os.dup2(null.fileno(), 0)
            os.dup2(null.fileno(), 1)
        try:
            stage = read(inbound, MAX_PACKET)
            source = base64.b64decode(stage["source"], validate=True)
            if len(source) > MAX_SOURCE or hashlib.sha256(source).hexdigest() != stage["digest"]:
                raise ValueError("Invalid staged identity")
            # Imports of installed repo modules are supported. The staged
            # policy itself is compiled from these bytes, never from pycache.
            sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
            namespace = {"__name__": "lily_local_policy"}
            exec(compile(source, "<lily-policy>", "exec", dont_inherit=True), namespace)
            if type(namespace.get("ABI_VERSION")) is not int or namespace["ABI_VERSION"] != 1:
                raise ValueError("Unsupported policy ABI")
            decide = namespace["decide"]
            if not callable(decide):
                raise ValueError("Missing policy callable")
            version = namespace.get("STATE_VERSION")
            if version is not None and (type(version) is not int or not 1 <= version <= 65535):
                raise ValueError("Invalid state version")
            outbound.write(encode({"ready": True, "state_version": version}))
            while True:
                request = read(inbound, MAX_PACKET)
                result = decide(request["observation"], request["context"])
                outbound.write(encode({"decision": result}, MAX_DECISION))
        except (Exception, SystemExit) as exc:
            # Exception messages can include private file paths or observations.
            outbound.write(encode({"error": type(exc).__name__}))
            return 1


if __name__ == "__main__":
    raise SystemExit(main())

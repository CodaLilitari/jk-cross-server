"""Run a bounded Lily controller against the local companion."""
import argparse
import http.client
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
import time

from bots.companion_cli import call, load_private
from .memory import ExperienceStore
from .runtime import Supervisor


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials", required=True, type=Path)
    parser.add_argument("--policy", type=Path, default=Path(__file__).with_name("policies") / "adaptive.py")
    parser.add_argument("--memory", required=True, type=Path)
    parser.add_argument("--environment-id", required=True, help="Stable identity for the level geometry and rules.")
    parser.add_argument("--directive-file", type=Path, help="Trusted local fenced directive JSON.")
    parser.add_argument("--trace", type=Path, help="Append privacy-filtered JSON lines.")
    parser.add_argument("--duration-seconds", required=True, type=float, help="Run for 0.1 to 3600 seconds.")
    args = parser.parse_args(argv)
    if not math.isfinite(args.duration_seconds) or not .1 <= args.duration_seconds <= 3600:
        parser.error("--duration-seconds must be in 0.1..3600")
    paths = [p.resolve() for p in (args.credentials, args.policy, args.memory, args.directive_file, args.trace) if p]
    if len(set(paths)) != len(paths):
        parser.error("Use distinct files for credentials, policy, memory, directives, and trace")
    store = trace = supervisor = None
    try:
        credential = load_private(args.credentials)
        if credential["bot_id"] != "lily":
            raise ValueError("Expected the scoped Lily credential")

        def transport(route, body=None):
            try:
                return call(credential, route, body)
            except http.client.HTTPException as exc:
                raise OSError("Interrupted companion request") from exc

        caps = transport("capabilities")
        if caps.get("run_id") != credential["run_id"] or (caps.get("lily") or {}).get("version") != 1:
            raise ValueError("Credential run or adaptive capability mismatch")
        # Create new output files privately before sqlite opens its own handle.
        os.close(os.open(args.memory, os.O_CREAT | os.O_WRONLY, 0o600))
        store = ExperienceStore(args.memory)
        if args.trace:
            fd = os.open(args.trace, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
            trace = os.fdopen(fd, "a", encoding="utf-8", buffering=1)

        def emit(row):
            if trace:
                trace.write(json.dumps(row, allow_nan=False, separators=(",", ":")) + "\n")
            if row["event"] in ("activated", "rejected", "fallback"):
                print(json.dumps({k: row[k] for k in ("event", "policy_hash", "reason") if k in row}), flush=True)

        supervisor = Supervisor(args.policy, store, args.environment_id, transport, trace=emit,
                                directive_file=args.directive_file)
        end = time.monotonic() + args.duration_seconds
        while time.monotonic() < end:
            try:
                requested_at = time.monotonic()
                observation = transport("observation")
            except (OSError, ValueError):
                if supervisor.fence:
                    supervisor.step(dict(supervisor.fence, native_active=False))
                time.sleep(min(.1, max(0, end - time.monotonic())))
                continue
            if observation["run_id"] != credential["run_id"]:
                raise ValueError("Credential run changed")
            supervisor.step(observation, observed_at=requested_at)
            time.sleep(min(.025, max(0, end - time.monotonic())))
    except KeyboardInterrupt:
        return 130
    except (KeyError, OSError, ValueError, sqlite3.Error) as exc:
        # Companions/credentials/paths are local. Do not echo responses or secrets.
        print("Lily runtime stopped (" + type(exc).__name__ + "). Check the credential, capability, and output paths.",
              file=sys.stderr)
        return 1
    finally:
        if supervisor:
            supervisor.close()
        if trace:
            trace.close()
        if store:
            store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

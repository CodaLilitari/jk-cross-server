#!/usr/bin/env python3
"""Run the JK Cross Server local control panel."""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
from pathlib import Path
import signal
import sys

from aiohttp import web
from manager.admin import create_admin_app
from manager import config as conf
from manager.content import preflight
from manager.runtime import ServerManager


async def serve(args):
    manager = ServerManager(args.config, args.state_dir)
    app = create_admin_app(manager, port=args.port)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    try:
        await web.TCPSite(runner, "127.0.0.1", args.port).start()
        print(f"JK Cross Server control panel: http://127.0.0.1:{args.port}/", flush=True)
        if args.start:
            try:
                await manager.start()
                print("Dedicated session started.", flush=True)
            except Exception as exc:
                print(f"Session startup failed: {exc}. The control panel remains available.", file=sys.stderr, flush=True)
        stopped = asyncio.Event()
        loop = asyncio.get_running_loop()
        for signum in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(signum, stopped.set)
        await stopped.wait()
    finally:
        await manager.close()
        await runner.cleanup()


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--config", type=Path, default=Path("config/server.json"))
    parser.add_argument("--state-dir", type=Path, default=Path("runtime"))
    parser.add_argument("--port", type=int, default=8765, help="Local control panel port (default 8765)")
    parser.add_argument("--check", action="store_true", help="Validate configuration and game archives, then exit")
    parser.add_argument("--start", action="store_true", help="Start the saved session when the panel opens")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("--port must be between 1024 and 65535")
    if args.check:
        try:
            value = conf.validate(conf.load(args.config), require_paths=True)
            print(json.dumps(preflight(value), indent=2))
            return 0
        except (ValueError, OSError) as exc:
            print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
            return 1
    try:
        asyncio.run(serve(args))
        return 0
    except KeyboardInterrupt:
        return 0
    except (ValueError, OSError) as exc:
        print(f"Unable to start control panel: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

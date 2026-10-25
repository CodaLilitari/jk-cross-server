#!/usr/bin/env python3
"""Run the JK Cross Server local control panel."""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
from pathlib import Path
import signal
import sys

async def serve(args, updater):
    # Recover interrupted updates before importing the normal server modules.
    from aiohttp import web
    from manager.admin import create_admin_app
    from manager.runtime import ServerManager
    from manager.updates import UpdateController

    stopped = asyncio.Event()
    restart_requested = False

    def request_restart():
        nonlocal restart_requested
        restart_requested = True
        stopped.set()

    manager = ServerManager(args.config, args.state_dir, updater=updater)
    updates = UpdateController(manager, updater, request_restart=request_restart)
    # Actual sessions take their own lease after these protected imports.
    updater.release_session_lease()
    app = create_admin_app(manager, port=args.port, updates=updates)
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
        updates.start()
        loop = asyncio.get_running_loop()
        for signum in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(signum, stopped.set)
        await stopped.wait()
    finally:
        manager.panel_closing = True
        await updates.close()
        await manager.close()
        await runner.cleanup()
    return restart_requested


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
    try:
        from manager.updater import ReleaseUpdater
        updater = ReleaseUpdater(Path(__file__).resolve().parent, args.state_dir,
                                 protected_paths=[args.config, args.state_dir])
        if updater.recover():
            print("An interrupted update was rolled back. Reloading the restored control panel.", flush=True)
            arguments = [arg for arg in sys.argv[1:] if arg != "--start"]
            os.execv(sys.executable, [sys.executable, str(Path(__file__).resolve()), *arguments])
        updater.acquire_session_lease()
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"Unable to recover the server installation: {exc}", file=sys.stderr)
        return 1
    if args.check:
        try:
            from manager import config as conf
            from manager.content import preflight
            value = conf.validate(conf.load(args.config), require_paths=True)
            print(json.dumps(preflight(value), indent=2))
            return 0
        except (ValueError, OSError) as exc:
            print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
            return 1
        finally:
            updater.release_session_lease()
    try:
        restart_requested = asyncio.run(serve(args, updater))
        if restart_requested:
            # An update must not reapply --start to a deliberately stopped game.
            arguments = [arg for arg in sys.argv[1:] if arg != "--start"]
            os.execv(sys.executable, [sys.executable, str(Path(__file__).resolve()), *arguments])
        return 0
    except KeyboardInterrupt:
        return 0
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"Unable to start control panel: {exc}", file=sys.stderr)
        return 1
    finally:
        updater.release_session_lease()


if __name__ == "__main__":
    raise SystemExit(main())

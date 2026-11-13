#!/usr/bin/env python3
"""Run the Linux server behind a byte-preserving local administration proxy."""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
from pathlib import Path
import signal
import sys


def ensure_config(data_root: Path) -> Path:
    """Create container defaults once; existing operator settings always win."""
    path = data_root / "config/server.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    config = {
        "version": 1,
        "game": "jk",
        "episode": "JK1MP",
        "map": "m2.jkl",
        "engine": "/app/bin/linux-x86_64/openjkdf2",
        "bots_engine": "/app/bin/bots-linux-x86_64/jk-bot-client",
        "game_data": "/game-data",
        "web_client": "/opt/jk-web",
        "web_bind": "0.0.0.0",
        "web_enabled": True,
        "spectator_rendering": True,
        "bots_enabled": False,
        "retail_enabled": False,
    }
    try:
        with path.open("x", encoding="utf-8") as stream:
            json.dump(config, stream, indent=2)
            stream.write("\n")
    except FileExistsError:
        pass
    return path


class LoopbackProxy:
    """Forward streams without rewriting HTTP Host, Origin, or authentication.

    Compose exposes this port only on the host loopback address. The actual
    administration server still accepts only loopback, same-origin requests.
    """

    def __init__(self, *, upstream_port=8765, host="0.0.0.0", port=8766):
        self.upstream_port = upstream_port
        self.host = host
        self.port = port
        self.server = None
        self.tasks = set()

    async def start(self):
        self.server = await asyncio.start_server(self._accept, self.host, self.port)

    def _accept(self, reader, writer):
        task = asyncio.create_task(self._relay(reader, writer))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    @staticmethod
    async def _copy(reader, writer):
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
        if writer.can_write_eof():
            writer.write_eof()

    async def _relay(self, reader, writer):
        upstream_writer = None
        pipes = []
        try:
            upstream_reader, upstream_writer = await asyncio.open_connection("127.0.0.1", self.upstream_port)
            pipes = [asyncio.create_task(self._copy(reader, upstream_writer)),
                     asyncio.create_task(self._copy(upstream_reader, writer))]
            await asyncio.gather(*pipes)
        except (ConnectionError, OSError):
            # The panel may still be starting, or the browser may have closed.
            pass
        finally:
            for task in pipes:
                task.cancel()
            await asyncio.gather(*pipes, return_exceptions=True)
            for connection in (writer, upstream_writer):
                if connection is not None:
                    connection.close()
                    with contextlib.suppress(ConnectionError, OSError):
                        await connection.wait_closed()

    async def close(self):
        if self.server is not None:
            self.server.close()
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if self.server is not None:
            await self.server.wait_closed()


async def run_runtime(app_root: Path, data_root: Path, *, proxy_port=8766, panel_port=8765):
    config = ensure_config(data_root)
    state = data_root / "runtime"
    state.mkdir(parents=True, exist_ok=True)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stop.set)
    proxy = LoopbackProxy(upstream_port=panel_port, port=proxy_port)
    child = None
    waiters = []
    try:
        await proxy.start()
        child = await asyncio.create_subprocess_exec(
            sys.executable, str(app_root / "app.py"), "--config", str(config),
            "--state-dir", str(state), "--port", str(panel_port), cwd=app_root,
        )
        # Omitting --start is deliberate: opening the package opens the panel.
        print("Control panel: http://127.0.0.1:8765/ (game session starts from the panel)", flush=True)
        print("Retail DirectPlay is disabled; this container does not include Wine or original DirectPlay runtime files.", flush=True)
        waiters = [asyncio.create_task(child.wait()), asyncio.create_task(stop.wait())]
        await asyncio.wait(waiters, return_when=asyncio.FIRST_COMPLETED)
        if child.returncode is None:
            child.terminate()
            try:
                await asyncio.wait_for(child.wait(), timeout=45)
            except asyncio.TimeoutError:
                child.kill()
                await child.wait()
        return child.returncode if child.returncode >= 0 else 128 - child.returncode
    finally:
        for task in waiters:
            task.cancel()
        await asyncio.gather(*waiters, return_exceptions=True)
        if child is not None and child.returncode is None:
            child.kill()
            await child.wait()
        await proxy.close()
        for signum in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(signum)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-root", type=Path, default=Path("/app"))
    parser.add_argument("--data-root", type=Path, default=Path("/data"))
    parser.add_argument("--proxy-port", type=int, default=8766)
    parser.add_argument("--panel-port", type=int, default=8765)
    args = parser.parse_args()
    return asyncio.run(run_runtime(args.app_root, args.data_root,
                                   proxy_port=args.proxy_port, panel_port=args.panel_port))


if __name__ == "__main__":
    raise SystemExit(main())

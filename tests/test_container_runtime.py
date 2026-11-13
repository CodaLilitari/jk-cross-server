"""Container configuration, unchanged admin guards, and owned-child shutdown."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "packaging/container_runtime.py"


def load_runtime(test):
    test.assertTrue(RUNTIME.is_file(), "The container runtime has not been implemented")
    spec = importlib.util.spec_from_file_location("jk_container_runtime", RUNTIME)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ConfigurationTests(unittest.TestCase):
    def test_first_launch_creates_usable_container_paths_without_enabling_bots(self):
        runtime = load_runtime(self)
        with tempfile.TemporaryDirectory() as directory:
            path = runtime.ensure_config(Path(directory))
            config = json.loads(path.read_text())
            self.assertEqual(path, Path(directory) / "config/server.json")
            self.assertEqual(config["engine"], "/app/bin/linux-x86_64/openjkdf2")
            self.assertEqual(config["bots_engine"], "/app/bin/bots-linux-x86_64/jk-bot-client")
            self.assertEqual(config["game_data"], "/game-data")
            self.assertEqual(config["web_client"], "/opt/jk-web")
            self.assertEqual(config["web_bind"], "0.0.0.0")
            self.assertEqual((config["game"], config["episode"], config["map"]), ("jk", "JK1MP", "m2.jkl"))
            self.assertFalse(config["bots_enabled"])
            self.assertFalse(config["retail_enabled"])
            self.assertTrue(config["spectator_rendering"])

    def test_restart_keeps_existing_configuration_bytes_even_if_invalid(self):
        runtime = load_runtime(self)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config/server.json"
            path.parent.mkdir()
            original = b'{"name":"My server", "unfinished":'
            path.write_bytes(original)
            self.assertEqual(runtime.ensure_config(Path(directory)), path)
            self.assertEqual(path.read_bytes(), original)


class ProxyTests(unittest.IsolatedAsyncioTestCase):
    async def test_proxy_preserves_host_origin_and_existing_admin_authentication(self):
        runtime = load_runtime(self)
        from aiohttp import ClientSession, web
        from manager.admin import create_admin_app

        runner = web.AppRunner(create_admin_app(object(), port=None, token="fixture-token"))
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        upstream_port = site._server.sockets[0].getsockname()[1]
        proxy = runtime.LoopbackProxy(upstream_port=upstream_port, host="127.0.0.1", port=0)
        try:
            await proxy.start()
            port = proxy.server.sockets[0].getsockname()[1]
            base = f"http://127.0.0.1:{port}"
            async with ClientSession() as session:
                async with session.get(base + "/", headers={"Origin": base}) as response:
                    self.assertEqual(response.status, 200)
                    self.assertIn("fixture-token", await response.text())
                async with session.get(base + "/", headers={"Host": "hostile.example"}) as response:
                    self.assertEqual(response.status, 403)
                async with session.get(base + "/", headers={"Origin": "https://hostile.example"}) as response:
                    self.assertEqual(response.status, 403)
                async with session.get(base + "/api/status") as response:
                    self.assertEqual(response.status, 401)
        finally:
            await proxy.close()
            await runner.cleanup()

    async def test_proxy_transmits_stream_bytes_and_closes_active_connections(self):
        runtime = load_runtime(self)

        async def echo(reader, writer):
            try:
                while data := await reader.read(65536):
                    writer.write(data)
                    await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()

        upstream = await asyncio.start_server(echo, "127.0.0.1", 0)
        proxy = runtime.LoopbackProxy(
            upstream_port=upstream.sockets[0].getsockname()[1], host="127.0.0.1", port=0)
        await proxy.start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", proxy.server.sockets[0].getsockname()[1])
            payload = bytes(range(256)) * 1024
            writer.write(payload)
            await writer.drain()
            self.assertEqual(await asyncio.wait_for(reader.readexactly(len(payload)), 5), payload)
            await asyncio.wait_for(proxy.close(), 3)
            self.assertEqual(await asyncio.wait_for(reader.read(), 2), b"")
            writer.close()
            await writer.wait_closed()
        finally:
            await proxy.close()
            upstream.close()
            await upstream.wait_closed()


@unittest.skipUnless(os.name == "posix", "Container signal lifecycle requires POSIX")
class LifecycleTests(unittest.TestCase):
    def test_runtime_forwards_termination_and_starts_panel_without_starting_match(self):
        load_runtime(self)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / "app"
            app.mkdir()
            (app / "app.py").write_text(
                "import json, pathlib, signal, sys, time\n"
                "signal.signal(signal.SIGTERM, lambda *args: sys.exit(0))\n"
                "pathlib.Path('started.json').write_text(json.dumps(sys.argv[1:]))\n"
                "try:\n"
                " while True: time.sleep(0.1)\n"
                "finally: pathlib.Path('stopped').write_text('clean')\n"
            )
            process = subprocess.Popen([
                sys.executable, str(RUNTIME), "--app-root", str(app), "--data-root", str(root / "data"),
                "--proxy-port", "0", "--panel-port", "18765",
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                deadline = time.monotonic() + 5
                while not (app / "started.json").is_file() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue((app / "started.json").is_file(), "Panel child never started")
                argv = json.loads((app / "started.json").read_text())
                self.assertEqual(argv, ["--config", str(root / "data/config/server.json"),
                                        "--state-dir", str(root / "data/runtime"), "--port", "18765"])
                process.send_signal(signal.SIGTERM)
                stdout, stderr = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 0, stdout + stderr)
                self.assertEqual((app / "stopped").read_text(), "clean")
            finally:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=5)

    def test_unexpected_panel_exit_ends_container_with_same_status(self):
        load_runtime(self)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / "app"
            app.mkdir()
            (app / "app.py").write_text("raise SystemExit(7)\n")
            result = subprocess.run([
                sys.executable, str(RUNTIME), "--app-root", str(app), "--data-root", str(root / "data"),
                "--proxy-port", "0",
            ], capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 7, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()

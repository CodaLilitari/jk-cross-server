"""Local control-panel API integration checks with a clearly marked fake engine."""
import copy
import unittest

from aiohttp import ClientSession, web
from manager.admin import create_admin_app
from manager.config import DEFAULT, ConfigError, validate


class FakeManager:
    def __init__(self):
        self.config = copy.deepcopy(DEFAULT)
        self.state = "stopped"

    async def update_config(self, value):
        if self.state != "stopped":
            raise ConfigError("Stop the session before changing its settings.")
        self.config = validate(value)
        return self.config

    async def start(self):
        self.state = "running"
        return self.status()

    async def stop(self):
        self.state = "stopped"
        return self.status()

    def status(self):
        return {"state": self.state, "uptime_seconds": 0, "native_connected": self.state == "running",
                "retail_ready": False, "browser": None, "session": None,
                "logs": [{"time": "2026-10-24T00:00:00Z", "source": "fixture", "text": "Control panel fixture; no game is running."}]}


class AdminIntegration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.manager = FakeManager()
        self.token = "local-test-token"
        self.runner = web.AppRunner(create_admin_app(self.manager, port=None, token=self.token))
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        self.url = "http://127.0.0.1:" + str(site._server.sockets[0].getsockname()[1])
        self.client = ClientSession()
        self.headers = {"Authorization": "Bearer " + self.token}

    async def asyncTearDown(self):
        await self.client.close()
        await self.runner.cleanup()

    async def test_panel_and_auth(self):
        async with self.client.get(self.url) as result:
            self.assertEqual(result.status, 200)
            self.assertIn(self.token, await result.text())
            self.assertEqual(result.headers["Cache-Control"], "no-store")
        async with self.client.get(self.url + "/api/config") as result:
            self.assertEqual(result.status, 401)
        async with self.client.get(self.url + "/api/config", headers=self.headers) as result:
            self.assertEqual(result.status, 200)

    async def test_cross_origin_and_host_rejected(self):
        async with self.client.get(self.url + "/api/config", headers=self.headers | {"Origin": "https://other.invalid"}) as result:
            self.assertEqual(result.status, 403)
        async with self.client.get(self.url, headers={"Host": "other.invalid"}) as result:
            self.assertEqual(result.status, 403)

    async def test_save_start_stop_and_running_edit_gate(self):
        value = dict(self.manager.config, name="Panel test")
        async with self.client.put(self.url + "/api/config", json=value, headers=self.headers) as result:
            self.assertEqual(result.status, 200)
        async with self.client.post(self.url + "/api/start", headers=self.headers) as result:
            self.assertEqual((await result.json())["state"], "running")
        async with self.client.put(self.url + "/api/config", json=value, headers=self.headers) as result:
            self.assertEqual(result.status, 400)
        async with self.client.post(self.url + "/api/stop", headers=self.headers) as result:
            self.assertEqual((await result.json())["state"], "stopped")

    async def test_catalog_error_is_readable_json(self):
        async with self.client.post(self.url + "/api/catalog", json={"config": self.manager.config}, headers=self.headers) as result:
            self.assertEqual(result.status, 400)
            self.assertIn("game data folder", (await result.json())["error"])


if __name__ == "__main__":
    unittest.main()

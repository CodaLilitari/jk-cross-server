"""Update scheduling and real control-panel lifecycle checks; no game launched."""
import asyncio
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from aiohttp import ClientSession, web

from manager.admin import create_admin_app
from manager.config import DEFAULT, ConfigError
from manager.runtime import ServerManager
from manager.updates import UpdateController
from manager.updater import InstallationBusy


class FixtureUpdater:
    def __init__(self):
        self.checks = self.installs = self.leases = 0
        self.protected = []
        self.release = None
        self.error = None
        self.changed = False
        self.entered = asyncio.Event()
        self.continue_install = None
        self.busy_once = False

    def status(self):
        return {"current_version": "0.4.0-dev" if self.changed else "0.3.0-dev",
                "running_version": "0.3.0-dev", "latest_version": self.release,
                "update_available": bool(self.release) and not self.changed,
                "install_supported": True, "restart_required": self.changed,
                "checking": False, "installing": False, "error": self.error}

    async def check(self):
        self.checks += 1
        self.release = "0.4.0-dev"
        return self.status()

    async def install(self):
        self.installs += 1
        self.entered.set()
        if self.busy_once:
            self.busy_once = False
            self.error = "Another session is using this installation."
            raise InstallationBusy(self.error)
        self.error = None
        if self.continue_install:
            await self.continue_install.wait()
        self.changed = True
        return self.status()

    def set_protected_paths(self, paths):
        self.protected = paths

    def acquire_session_lease(self):
        self.leases += 1

    def release_session_lease(self):
        self.leases = 0


class UpdateLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.updater = FixtureUpdater()
        self.manager = ServerManager(self.root / "config.json", self.root / "runtime", updater=self.updater)
        self.restarted = asyncio.Event()
        self.controller = UpdateController(self.manager, self.updater, request_restart=self.restarted.set)

    async def asyncTearDown(self):
        await self.controller.close()
        await self.manager.close()
        self.temp.cleanup()

    async def test_default_checks_are_automatic_but_installation_is_not(self):
        await self.controller.tick()
        await self.controller.tick()
        self.assertEqual(self.updater.checks, 1)
        self.assertEqual(self.updater.installs, 0)
        self.assertTrue(self.controller.status()["update_available"])
        self.assertFalse(self.controller.status()["auto_install"])

    async def test_auto_install_waits_for_stop_then_requests_restart(self):
        self.manager.state = "running"
        await self.controller.configure({"enabled": True, "auto_install": True})
        await self.controller.tick()
        self.assertEqual(self.updater.installs, 0)
        self.assertTrue(self.controller.status()["waiting_for_stop"])
        self.manager.state = "stopped"
        await self.controller.tick()
        self.assertEqual(self.updater.installs, 1)
        self.assertTrue(self.controller.restart_pending)
        await asyncio.wait_for(self.restarted.wait(), 2)
        self.assertEqual(self.manager.state, "stopped")

    async def test_active_or_remaining_process_prevents_manual_install(self):
        for state in ("starting", "running", "stopping"):
            self.manager.state = state
            with self.assertRaisesRegex(ValueError, "Stop the game session"):
                await self.controller.install()
        self.manager.state = "stopped"
        self.manager.processes["fixture"] = type("Process", (), {"returncode": None})()
        with self.assertRaisesRegex(ValueError, "Stop the game session"):
            await self.controller.install()
        self.manager.processes.clear()
        self.assertEqual(self.updater.installs, 0)

    async def test_update_settings_persist_and_can_disable_all_automatic_work(self):
        await self.controller.configure({"enabled": False, "auto_install": False})
        another = UpdateController(self.manager, self.updater)
        await another.tick()
        self.assertEqual(self.updater.checks, 0)
        self.assertFalse(another.settings["enabled"])
        for bad in ({"enabled": "yes", "auto_install": False},
                    {"enabled": False, "auto_install": True}, {"enabled": True}):
            with self.assertRaises(ValueError):
                await self.controller.configure(bad)

    async def test_shutdown_waits_for_install_and_protects_configured_data(self):
        self.manager.config["game_data"] = str(self.root / "owned-game")
        self.updater.continue_install = asyncio.Event()
        install = asyncio.create_task(self.controller.install())
        await self.updater.entered.wait()
        self.assertTrue(self.manager.lock.locked())
        closing = asyncio.create_task(self.controller.close())
        await asyncio.sleep(0)
        self.assertFalse(closing.done())
        self.updater.continue_install.set()
        await install
        await closing
        self.assertIn(self.root / "owned-game", self.updater.protected)
        self.assertIn(self.manager.config_path, self.updater.protected)
        self.assertIn(self.manager.state_dir, self.updater.protected)

    async def test_auto_install_retries_after_other_instance_stops(self):
        self.controller.idle_interval = 0
        self.updater.busy_once = True
        await self.controller.configure({"enabled": True, "auto_install": True})
        await self.controller.tick()
        self.assertEqual(self.updater.installs, 1)
        self.assertTrue(self.controller.status()["waiting_for_other_sessions"])
        self.assertFalse(self.controller.restart_pending)
        await self.controller.tick()
        self.assertEqual(self.updater.installs, 2)
        self.assertTrue(self.controller.restart_pending)

    async def test_failed_install_waits_for_fresh_check_before_retry(self):
        await self.controller.configure({"enabled": True, "auto_install": True})
        with patch.object(self.updater, "install", side_effect=ValueError("fixture install failure")) as failing:
            await self.controller.tick()
            await self.controller.tick()
            self.assertEqual(failing.await_count, 1)
        await self.controller.check()
        await self.controller.tick()
        self.assertEqual(self.updater.installs, 1)

    async def test_restart_grace_period_rejects_new_session(self):
        await self.controller.restart()
        with self.assertRaisesRegex(ConfigError, "restarting or closing"):
            await self.manager.start()
        self.assertEqual(self.manager.state, "stopped")

    async def test_stale_panel_cannot_start_and_failed_boot_releases_lease(self):
        self.updater.changed = True
        with self.assertRaisesRegex(ConfigError, "Restart this control panel"):
            await self.manager.start()
        self.assertEqual(self.updater.leases, 0)
        self.updater.changed = False
        with patch("manager.runtime.conf.validate", return_value=copy.deepcopy(DEFAULT)), \
                patch("manager.runtime.preflight", side_effect=ValueError("fixture preflight failure")):
            with self.assertRaisesRegex(ValueError, "fixture preflight failure"):
                await self.manager.start()
        self.assertEqual(self.updater.leases, 0)
        self.assertEqual(self.manager.state, "failed")

    async def test_admin_update_endpoints_use_existing_auth_and_session_gate(self):
        app = create_admin_app(self.manager, port=None, token="fixture-token", updates=self.controller)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        url = "http://127.0.0.1:" + str(site._server.sockets[0].getsockname()[1])
        headers = {"Authorization": "Bearer fixture-token"}
        try:
            async with ClientSession() as client:
                for endpoint in ("check", "install", "restart"):
                    async with client.post(url + "/api/updates/" + endpoint) as response:
                        self.assertEqual(response.status, 401)
                async with client.put(url + "/api/updates/settings", json={"enabled": False, "auto_install": False}, headers=headers) as response:
                    self.assertEqual(response.status, 200)
                    self.assertFalse((await response.json())["enabled"])
                async with client.post(url + "/api/updates/check", headers=headers) as response:
                    self.assertEqual(response.status, 200)
                    self.assertTrue((await response.json())["update_available"])
                self.manager.state = "running"
                async with client.post(url + "/api/updates/install", headers=headers) as response:
                    self.assertEqual(response.status, 400)
                async with client.get(url + "/api/status", headers=headers) as response:
                    self.assertEqual((await response.json())["updates"]["latest_version"], "0.4.0-dev")
        finally:
            self.manager.state = "stopped"
            await runner.cleanup()


if __name__ == "__main__":
    unittest.main()

"""Control-panel and owned-process checks; helpers are not game clients."""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from aiohttp import ClientSession, web

from bots.settings import BEHAVIOR_FIELDS, PROFILE_IDS, write_behavior
from manager import config as conf
from manager.admin import create_admin_app
from manager.runtime import ServerManager


class BotConfigurationTests(unittest.TestCase):
    def test_defaults_preserve_manual_server_sessions(self):
        value = conf.validate({})
        self.assertFalse(value["bots_enabled"])
        self.assertFalse(value["bots_sabers_only"])
        self.assertTrue(value["bots_fists_peace"])
        self.assertTrue(value["bots_force_enabled"])
        self.assertEqual(value["bots_profiles"], ["boba_fett", "jan_ors"])
        value["bots_profiles"].append("yun")
        self.assertEqual(len(conf.validate({})["bots_profiles"]), 2)

    def test_invalid_bot_settings_and_unsupported_sessions_are_rejected(self):
        cases = [{key: 1} for key in (*BEHAVIOR_FIELDS, "bots_enabled", "bots_taunts")]
        cases += [{"bots_profiles": value} for value in ([], "boba_fett", ["unknown"], ["yun", "yun"], list(PROFILE_IDS[:5]))]
        cases += [{"bots_enabled": True, **value} for value in
                  ({"max_players": 2}, {"game": "mots"}, {"password": "private"},
                   {"episode": "custom"}, {"mod_dir": "/tmp/mod"}, {"game_flags": 4096},
                   {"teams": True}, {"episode": "JK1CTF"})]
        for value in cases:
            with self.subTest(value=value), self.assertRaises(conf.ConfigError):
                conf.validate(value)
        for value in ({"rank": 8}, {"teams": True, "game_flags": 256},
                      {"episode": "JK1CTF", "teams": True}):
            self.assertTrue(conf.validate({"bots_enabled": True, **value})["bots_enabled"])

    def test_behavior_file_replacement_has_complete_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "behavior.cfg"
            write_behavior(path, conf.validate({}))
            old = path.read_bytes()
            with self.assertRaises(ValueError):
                write_behavior(path, {"bots_sabers_only": "yes"})
            self.assertEqual(path.read_bytes(), old)
            write_behavior(path, {"bots_sabers_only": True, "bots_fists_peace": False, "bots_force_enabled": False})
            self.assertEqual(path.read_text(), "version=1\nsabers_only=1\nfists_peace=0\nforce_enabled=0\n")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertFalse(path.with_name("behavior.cfg.tmp").exists())

    def test_enabled_bot_capacity_reserves_conservative_launcher_headroom(self):
        for count, too_small, enough in ((1, 2, 3), (4, 5, 6)):
            settings = {"bots_enabled": True, "bots_profiles": list(PROFILE_IDS[:count])}
            with self.subTest(bots=count, slots=too_small), self.assertRaisesRegex(conf.ConfigError, "headroom"):
                conf.validate({**settings, "max_players": too_small})
            with self.subTest(bots=count, slots=enough):
                saved = conf.validate({**settings, "max_players": enough})
                self.assertEqual(saved["max_players"], enough)
                self.assertEqual(len(saved["bots_profiles"]), count)

    def test_disabled_bots_preserve_small_manual_session_capacity(self):
        for slots in (1, 2, 5):
            with self.subTest(slots=slots):
                saved = conf.validate({"bots_enabled": False, "bots_profiles": list(PROFILE_IDS[:4]),
                                       "max_players": slots})
                self.assertEqual(saved["max_players"], slots)
                self.assertFalse(saved["bots_enabled"])


@unittest.skipUnless(sys.platform == "linux", "Managed bots use an owned Linux process group")
class BotManagerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="jk-managed-bots-test-")
        self.root = Path(self.temp.name)
        data = self.root / "game"
        (data / "resource").mkdir(parents=True)
        (data / "episode").mkdir()
        (data / "resource/res2.gob").write_bytes(b"fixture only")
        (data / "episode/jk1mp.gob").write_bytes(b"fixture only")
        self.engine = self.root / "helper-engine"
        self.engine.write_text("#!" + sys.executable + "\n" + '''
import json,os,time
from pathlib import Path
Path('observed.json').write_text(json.dumps({'pid':os.getpid(),'pgid':os.getpgrp(),'env':dict(os.environ)}))
print('BOT_JOINED slot=1 net='+str(os.getpid()),flush=True)
while True:
    Path('observed-rules.txt').write_text(Path(os.environ['JK_BOT_BEHAVIOR_FILE']).read_text())
    time.sleep(.03)
''')
        self.engine.chmod(0o700)
        # app.py defaults to a relative state directory; child argv must still
        # resolve correctly after the manager changes the subprocess cwd.
        self.manager = ServerManager(self.root / "server.json", Path(os.path.relpath(self.root / "runtime")))
        self.manager.config = conf.save(self.manager.config_path, {
            "bots_enabled": True, "bots_engine": str(self.engine), "game_data": str(data),
            "max_players": 4, "web_enabled": False,
        })
        self.manager.prepare()
        self.manager.state = "running"
        self.env = patch.dict(os.environ, {"DISPLAY": ":99"})
        self.env.start()

    async def asyncTearDown(self):
        await self.manager.close()
        self.env.stop()
        self.temp.cleanup()

    async def until(self, predicate, message):
        deadline = asyncio.get_running_loop().time() + 5
        while asyncio.get_running_loop().time() < deadline:
            if predicate():
                return
            await asyncio.sleep(.03)
        self.fail(message)

    async def roster(self):
        await self.manager.start_bots()
        await self.until(lambda: self.manager.bot_status()["state"] == "running", "Helpers did not report ordinary joins")
        receipt = json.loads((self.manager.run_dir / "bots-status.json").read_text())
        return receipt["bots"]

    @staticmethod
    def process_running(pid):
        try:
            # A zombie has already stopped and may briefly await the runner.
            return Path(f"/proc/{pid}/stat").read_text().split(") ", 1)[1][0] != "Z"
        except FileNotFoundError:
            return False

    async def test_managed_roster_live_rules_and_stop_leave_unrelated_process_alive(self):
        unrelated = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(30)"], start_new_session=True)
        try:
            rows = await self.roster()
            runner_pid = self.manager.processes["bots"].pid
            for row in rows:
                observed = json.loads((Path(row["directory"]) / "observed.json").read_text())
                self.assertEqual(observed["pgid"], runner_pid)
            self.assertEqual(self.manager.status()["bots"]["joined_count"], 2)
            for player in self.manager.status()["bots"]["players"]:
                self.assertEqual(player["requested_team"], 0)
                self.assertNotIn("team", player)
            rules = {"bots_sabers_only": True, "bots_fists_peace": False, "bots_force_enabled": False}
            saved = await self.manager.update_bot_behavior(rules)
            self.assertEqual(saved, rules)
            first = Path(rows[0]["directory"]) / "observed-rules.txt"
            await self.until(lambda: "sabers_only=1" in first.read_text() and "force_enabled=0" in first.read_text(),
                             "Updated rules did not reach the running client input file")
            self.assertEqual(conf.load(self.manager.config_path)["bots_sabers_only"], True)
            self.assertEqual(self.manager.processes["bots"].pid, runner_pid)
            with self.assertRaises(conf.ConfigError):
                await self.manager.update_config({**self.manager.config, "bots_profiles": ["yun"]})
            await self.manager.stop()
            await self.until(lambda: all(not self.process_running(row["pid"]) for row in rows), "Managed children survived stop")
            self.assertIsNone(unrelated.poll())
        finally:
            unrelated.terminate()
            unrelated.wait(timeout=3)

    async def test_runner_crash_cleans_children_and_keeps_human_session_running(self):
        rows = await self.roster()
        self.manager.processes["bots"].kill()
        await self.until(lambda: self.manager.bots_error is not None, "Runner crash was not reported")
        await self.until(lambda: all(not self.process_running(row["pid"]) for row in rows), "Runner crash left bot children alive")
        self.assertEqual(self.manager.state, "running")
        self.assertEqual(self.manager.bot_status()["state"], "failed")

    async def test_live_rule_schema_failure_preserves_running_and_saved_rules(self):
        await self.roster()
        before = self.manager.config_path.read_bytes()
        path = self.manager.run_dir / "bots-behavior.cfg"
        old = path.read_bytes()
        for value in ({}, {"bots_enabled": False},
                      {"bots_sabers_only": True, "bots_fists_peace": False, "bots_force_enabled": 1}):
            with self.subTest(value=value), self.assertRaises(conf.ConfigError):
                await self.manager.update_bot_behavior(value)
        self.assertEqual(self.manager.config_path.read_bytes(), before)
        self.assertEqual(path.read_bytes(), old)
        valid = {key: False for key in BEHAVIOR_FIELDS}
        with patch("manager.runtime.conf.save", side_effect=OSError("fixture write failure")):
            with self.assertRaisesRegex(OSError, "fixture write failure"):
                await self.manager.update_bot_behavior(valid)
        self.assertEqual(path.read_bytes(), old)
        self.assertEqual(self.manager.config_path.read_bytes(), before)

    async def test_bot_api_uses_existing_auth_and_rejects_roster_as_live_rule(self):
        self.manager.state = "stopped"
        runner = web.AppRunner(create_admin_app(self.manager, port=None, token="fixture-token"))
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        url = "http://127.0.0.1:" + str(site._server.sockets[0].getsockname()[1])
        auth = {"Authorization": "Bearer fixture-token"}
        try:
            async with ClientSession() as client:
                async with client.get(url + "/api/bots/profiles") as response:
                    self.assertEqual(response.status, 401)
                async with client.get(url + "/api/bots/profiles", headers=auth) as response:
                    self.assertEqual({p["id"] for p in await response.json()}, set(PROFILE_IDS))
                async with client.put(url + "/api/bots/behavior", json={key: True for key in BEHAVIOR_FIELDS}, headers=auth) as response:
                    self.assertEqual(response.status, 200)
                async with client.put(url + "/api/bots/behavior", json={"bots_profiles": ["yun"]}, headers=auth) as response:
                    self.assertEqual(response.status, 400)
        finally:
            await runner.cleanup()


if __name__ == "__main__":
    unittest.main()

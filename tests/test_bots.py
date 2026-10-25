"""Lifecycle and data-isolation tests for the ordinary-player bot launcher.

Small helper programs stand in for the engine; these tests do not claim game
AI or protocol compatibility. Live-game validation is recorded separately.
"""
from __future__ import annotations

import contextlib
import copy
import io
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from bots import run
from manager import config as conf


@unittest.skipUnless(sys.platform == "linux", "Bot runner is currently Linux-only")
class BotRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="jk-bot-test-")
        self.root = Path(self.temp.name)
        self.data = self.root / "game"
        for name in ("Resource", "Episode", "player"):
            (self.data / name).mkdir(parents=True)
        (self.data / "Resource/JK_.CD").write_bytes(b"")
        (self.data / "Resource/Res1.gob").write_bytes(b"original game resource")
        (self.data / "Episode/JK1MP.GOB").write_bytes(b"original multiplayer episode")
        (self.data / "player/human.plr").write_bytes(b"do not change human controls")
        (self.data / "registry.json").write_bytes(b"original human settings")
        self.config = conf.validate({"game_data": str(self.data), "max_players": 4})
        self.profiles = list(run.load_profiles().values())[:2]
        self.engine = self.program("engine", """
import json, os, sys, time
from pathlib import Path
Path('observed.json').write_text(json.dumps({'argv':sys.argv[1:], 'env':dict(os.environ),
                                           'pid':os.getpid(), 'pgid':os.getpgrp()}))
print('BOT_JOINED slot=1 net=' + str(os.getpid()), flush=True)
time.sleep(30)
""")
        self.env = patch.dict(os.environ, {"DISPLAY": ":99", "OPENJKDF2_GATEWAY_TOKEN": "must-not-inherit",
                                          "JK_GATEWAY_TOKEN": "must-not-inherit",
                                          "OPENJKDF2_REQUIRE_DP_POOL": "1", "JK_BOT_PASSWORD": "old-password"})
        self.env.start()
        self.output = contextlib.ExitStack()
        self.output.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.output.enter_context(contextlib.redirect_stderr(io.StringIO()))

    def tearDown(self):
        self.output.close()
        self.env.stop()
        self.temp.cleanup()

    def program(self, name, source):
        path = self.root / name
        path.write_text("#!" + sys.executable + "\n" + source, encoding="utf-8")
        path.chmod(0o700)
        return path

    def launch(self, **overrides):
        options = {"engine": self.engine, "connect": "127.0.0.1:3500", "runtime": self.root / "runs",
                   "seconds": 0.3, "taunts": True}
        options.update(overrides)
        return run.launch(self.config, self.profiles, **options)

    def test_stock_roster_has_eight_distinct_profiles_and_128_lines(self):
        profiles = run.load_profiles()
        self.assertEqual(len(profiles), 8)
        self.assertEqual(sum(len(lines) for row in profiles.values() for lines in row["taunts"].values()), 128)
        self.assertEqual(profiles["boba_fett"]["model"], "kyh4.3do")
        self.assertEqual(profiles["jan_ors"]["sound"], "kyfemale.snd")

    def test_invalid_profile_content_and_duplicate_names_are_rejected(self):
        original = json.loads(run.PROFILE_FILE.read_text())
        bad_values = [None, [], {"version": 1, "game": "jk", "profiles": []}]
        for field, value in [("name", "Bot name"), ("model", "../ky.3do"),
                             ("sound", "evil.snd\n"), ("id", "UPPER"),
                             ("taunts", {"spawn": ["only one context"]})]:
            changed = copy.deepcopy(original)
            changed["profiles"][0][field] = value
            bad_values.append(changed)
        changed = copy.deepcopy(original)
        changed["profiles"][0]["taunts"]["ambient"] = ["newline\ninside"]
        bad_values.append(changed)
        changed = copy.deepcopy(original)
        changed["profiles"][1]["name"] = "Bot_bobafett"
        bad_values.append(changed)
        changed = copy.deepcopy(original)
        changed["profiles"][0] = 12
        bad_values.append(changed)
        for index, value in enumerate(bad_values):
            with self.subTest(case=index):
                path = self.root / "bad.json"
                path.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    run.load_profiles(path)

    def test_scope_count_and_selection_guards(self):
        profiles = run.load_profiles()
        for value in ("", "boba_fett,boba_fett", "unknown", ",jan_ors",
                      "boba_fett,jan_ors,kyle_katarn,stormtrooper,bossk"):
            with self.subTest(selection=value), self.assertRaises(ValueError):
                run.select_profiles(profiles, value)
        for key, value in [("game", "mots"), ("rank", 1), ("teams", True),
                           ("game_flags", 16), ("password", "private"),
                           ("mod_dir", "/tmp/mod"), ("episode", "JKCTF"), ("max_players", 2)]:
            config = dict(self.config, **{key: value})
            with self.subTest(key=key), self.assertRaises(ValueError):
                run.check_scope(config, 2)

    def test_endpoint_rejects_arguments_and_unsupported_formats(self):
        for value in ("-host:3", "host;echo:3", "host:0", "host:65536", "::1:3500", "host", "host:3\n"):
            with self.subTest(endpoint=value), self.assertRaises(ValueError):
                run.endpoint(value)
        self.assertEqual(run.endpoint("example.local:03500"), "example.local:3500")

    def test_staging_preserves_original_human_data_with_links_and_copy_fallback(self):
        (self.data / "Resource/Video").mkdir()
        (self.data / "Resource/Video/cutscene.smk").write_bytes(b"not needed")
        before = {p.relative_to(self.data): p.read_bytes() for p in self.data.rglob("*") if p.is_file()}
        for copying in (False, True):
            directory = self.root / ("copy" if copying else "linked")
            context = patch.object(run.os, "link", side_effect=OSError("different device")) if copying else contextlib.nullcontext()
            with context:
                run.prepare_bot(self.data, directory, self.profiles[0])
            self.assertEqual((directory / "resource/res1.gob").read_bytes(), b"original game resource")
            self.assertTrue((directory / "resource/jk_.cd").exists())
            self.assertFalse((directory / "resource/video").exists())
            self.assertEqual(list((directory / "player").iterdir()), [])
            self.assertEqual((directory / "xdg").stat().st_mode & 0o777, 0o700)
            self.assertNotEqual((directory / "registry.json").read_bytes(), (self.data / "registry.json").read_bytes())
        self.assertEqual(before, {p.relative_to(self.data): p.read_bytes() for p in self.data.rglob("*") if p.is_file()})

    def test_case_collision_directory_cycle_and_output_overlap_rejected(self):
        (self.data / "Resource/res1.GOB").write_bytes(b"ambiguous")
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            run.prepare_bot(self.data, self.root / "ambiguous", self.profiles[0])
        (self.data / "Resource/res1.GOB").unlink()
        (self.data / "Resource/cycle").symlink_to(self.data / "Resource", target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "cycle"):
            run.prepare_bot(self.data, self.root / "cyclic", self.profiles[0])
        for output in (self.data, self.data / "bots", self.root):
            with self.subTest(output=output), self.assertRaisesRegex(ValueError, "overlapping"):
                run.ensure_separate(self.data, output)

    def test_actual_helper_clients_are_isolated_record_join_and_do_not_inherit_server_secrets(self):
        code, directory = self.launch()
        self.assertEqual(code, 0)
        receipt = json.loads((directory / "session.json").read_text())
        self.assertEqual(receipt["result"], "duration_complete")
        self.assertEqual(len(receipt["bots"]), 2)
        pids = set()
        for row in receipt["bots"]:
            self.assertTrue(row["joined"])
            self.assertIsNotNone(row["returncode"])
            observed = json.loads((Path(row["directory"]) / "observed.json").read_text())
            self.assertEqual(observed["pid"], observed["pgid"])
            pids.add(observed["pid"])
            env = observed["env"]
            for key in ("OPENJKDF2_GATEWAY_TOKEN", "JK_GATEWAY_TOKEN", "OPENJKDF2_REQUIRE_DP_POOL", "JK_BOT_PASSWORD"):
                self.assertNotIn(key, env)
            self.assertEqual(env["OPENJKDF2_ROOT"], row["directory"])
            self.assertEqual(env["JK_BOT_CHAT_LOCK"], str(directory / "chat.lock"))
            self.assertIn(row["name"], observed["argv"])
            self.assertIn(row["model"], observed["argv"])
        self.assertEqual(len(pids), 2)

    def test_finite_duration_without_join_is_failure_and_stops_owned_processes(self):
        self.engine = self.program("silent", "import time\ntime.sleep(30)\n")
        code, directory = self.launch(seconds=0.15)
        self.assertEqual(code, 1)
        receipt = json.loads((directory / "session.json").read_text())
        self.assertIn("before all bots joined", " ".join(receipt["errors"]))
        self.assertTrue(all(row["returncode"] is not None for row in receipt["bots"]))

    def test_join_watchdog_and_join_rejection_are_reported(self):
        self.engine = self.program("silent", "import time\ntime.sleep(30)\n")
        with patch.object(run, "JOIN_TIMEOUT", 0.1):
            code, directory = self.launch(seconds=2)
        receipt = json.loads((directory / "session.json").read_text())
        self.assertEqual(code, 1)
        self.assertIn("did not join", " ".join(receipt["errors"]))
        self.engine = self.program("rejected", "import time\nprint('BOT_JOIN_REJECTED reason=bad_map',flush=True)\ntime.sleep(30)\n")
        code, directory = self.launch(seconds=2)
        self.assertEqual(code, 1)
        self.assertIn("bad_map", (directory / "session.json").read_text())

    def test_an_unexpected_component_exit_fails_and_stops_siblings(self):
        self.engine = self.program("exits", "import sys,time\nprint('BOT_JOINED slot=1 net=123',flush=True)\ntime.sleep(.1)\nsys.exit(7)\n")
        code, directory = self.launch(seconds=2)
        self.assertEqual(code, 1)
        receipt = json.loads((directory / "session.json").read_text())
        self.assertIn("status 7", " ".join(receipt["errors"]))
        self.assertTrue(all(row["returncode"] is not None for row in receipt["bots"]))

    def test_cleanup_failure_does_not_skip_other_children_or_signal_restoration(self):
        previous = signal.getsignal(signal.SIGTERM)
        actual_stop = run.stop_group
        stopped = []
        def stop_then_error(process):
            actual_stop(process, grace=0.1)
            stopped.append(process.pid)
            if len(stopped) == 1:
                raise RuntimeError("injected cleanup failure after termination")
        with patch.object(run, "stop_group", side_effect=stop_then_error):
            code, directory = self.launch()
        self.assertEqual(code, 1)
        self.assertEqual(len(stopped), 2)
        self.assertEqual(signal.getsignal(signal.SIGTERM), previous)
        receipt = json.loads((directory / "session.json").read_text())
        self.assertTrue(all(row["returncode"] is not None for row in receipt["bots"]))
        self.assertIn("injected cleanup failure", " ".join(receipt["errors"]))

    def test_descendant_is_killed_even_after_its_group_leader_exits(self):
        read_fd, write_fd = os.pipe()
        child_code = "import os,signal,sys,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); os.write(int(sys.argv[1]),b'R'); time.sleep(30)"
        leader_code = "import subprocess,sys; subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[2]],pass_fds=(int(sys.argv[2]),))"
        process = subprocess.Popen([sys.executable, "-c", leader_code, child_code, str(write_fd)],
                                   pass_fds=(write_fd,), start_new_session=True)
        os.close(write_fd)
        try:
            self.assertTrue(select.select([read_fd], [], [], 3)[0], "Descendant did not start")
            self.assertEqual(os.read(read_fd, 1), b"R")
            process.wait(timeout=3)
            run.stop_group(process, grace=0.1)
            self.assertTrue(select.select([read_fd], [], [], 3)[0], "Descendant still owns the pipe")
            self.assertEqual(os.read(read_fd, 1), b"", "Descendant was not terminated")
        finally:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=3)
            os.close(read_fd)

    def test_stopping_bots_does_not_stop_unrelated_process(self):
        unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
        try:
            code, _ = self.launch()
            self.assertEqual(code, 0)
            self.assertIsNone(unrelated.poll())
        finally:
            unrelated.terminate()
            unrelated.wait(timeout=3)

    def test_display_readiness_pipe_stays_open_until_xvfb_stops(self):
        marker = self.root / "second-readiness-write.txt"
        fake_display = self.program("Xvfb", """
import os,sys,time
from pathlib import Path
fd=int(sys.argv[sys.argv.index('-displayfd')+1])
os.write(fd,b'777\\n')
time.sleep(.15)
os.write(fd,b'777\\n')
Path(%r).write_text('second readiness notification succeeded')
time.sleep(30)
""" % str(marker))
        with patch.dict(os.environ, {"DISPLAY": ""}), patch.object(run.shutil, "which", return_value=str(fake_display)):
            code, directory = self.launch(seconds=0.4)
        self.assertEqual(code, 0)
        self.assertTrue(marker.exists(), (directory / "xvfb.log").read_text())
        self.assertEqual(json.loads((directory / "session.json").read_text())["result"], "duration_complete")


if __name__ == "__main__":
    unittest.main()

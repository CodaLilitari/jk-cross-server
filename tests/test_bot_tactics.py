"""Tactic registry, companion route, command line, launcher plumbing and coach."""
import http.client
import json
import math
from pathlib import Path
import re
import struct
import tempfile
import unittest

from bots import coach
from bots import companion as c
from bots import companion_cli as cli
from bots import run
from bots import tactics

ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "native/bot-tactics.patch"


def state(seq, world=1, life=1, kills=0, deaths=0):
    data = bytearray(144)
    struct.pack_into("<4I", data, 0, 1, 42, 14, 88)
    struct.pack_into("<f", data, 32, 100.)
    struct.pack_into("<II", data, 48, kills, deaths)
    struct.pack_into("<iII", data, 60, -1, 4, 0xffffffff)
    return c.frame(c.STATE, world, life, seq, data)


class RegistryTests(unittest.TestCase):
    def test_registry_matches_the_engine_table(self):
        source = OVERLAY.read_text(encoding="utf-8")
        rows = tactics.engine_rows(source)
        self.assertEqual(rows, [row[:5] for row in tactics.TACTICS])
        limits = re.search(r"BOT_TACTICS_COMMIT_SECONDS = (\d+), BOT_TACTICS_WIRE_PAIRS = (\d+)", source)
        self.assertEqual(tuple(map(int, limits.groups())), (tactics.COMMIT_SECONDS, tactics.WIRE_PAIRS))
        self.assertEqual(int(re.search(r"CP_TACTICS=(\d+)", source).group(1)), c.TACTICS)
        self.assertEqual(c.KINDS["tactics"], 21)
        self.assertNotIn(c.TACTICS, (19, 20), "reserved by the adaptive-player branch")

    def test_table_is_well_formed(self):
        self.assertEqual(len(set(tactics.NAMES)), len(tactics.NAMES))
        self.assertLessEqual(len(tactics.NAMES), 255)
        for name, default, legacy, low, high, meaning in tactics.TACTICS:
            self.assertRegex(name, r"\A[a-z][a-z_]{1,30}\Z")
            self.assertTrue(low <= default <= high and low <= legacy <= high and meaning, name)
        # The largest command fits the engine's 118-byte receipt cache.
        self.assertLessEqual(8 + 2 + 5 * tactics.WIRE_PAIRS, 118)

    def test_presets_are_valid_and_legacy_turns_new_behaviour_off(self):
        self.assertEqual(set(tactics.PRESETS), set(tactics.PRESET_NOTES))
        for name, values in tactics.PRESETS.items():
            reset, merged = tactics.resolve(name)
            self.assertTrue(reset)
            self.assertEqual(merged, values)
            self.assertEqual(tactics.validate(values), values)
            self.assertLessEqual(len(tactics.wire(True, values)[1]), tactics.WIRE_PAIRS)
        legacy = tactics.table("legacy")
        self.assertEqual(legacy, tactics.LEGACY)
        for name in ("run", "exact_thrust", "strafe_run", "confine_seconds", "water_entry_cost", "dive_min_value"):
            self.assertEqual(legacy[name], 0)
        # Every preset keeps the concussion rifle worth a dive.
        for name in tactics.PRESETS:
            table = tactics.table(name)
            self.assertGreaterEqual(table["value_conc"], table["dive_min_value"], name)

    def test_validation_and_resolution(self):
        for bad in ([], {"nope": 1}, {"run": "1"}, {"run": True}, {"run": math.nan}, {"run": math.inf},
                    {"run": 1.5}, {"dive_seconds": 1.99}, {"value_conc": -0.1}):
            with self.assertRaises(ValueError, msg=repr(bad)):
                tactics.validate(bad)
        self.assertEqual(tactics.validate({"run": 0, "travel_cost": 0.05}), {"run": 0.0, "travel_cost": 0.05})
        self.assertEqual(tactics.resolve(None, {"run": 0}), (False, {"run": 0.0}))
        self.assertEqual(tactics.resolve(None, None, True), (True, {}))
        self.assertEqual(tactics.resolve("dry", {"run": 0})[1]["run"], 0.0)
        for arguments in ((None, None), ("nope", None), (None, {"run": 0}, "yes"), (3, None)):
            with self.assertRaises(ValueError):
                tactics.resolve(*arguments)
        with self.assertRaises(ValueError):
            tactics.resolve(None, dict(tactics.DEFAULTS))  # more than one command carries

    def test_wire_encoding(self):
        payload = tactics.encode(True, {"gun_far": 3.5, "value_conc": 20})
        self.assertEqual(payload[:2], bytes((1, 2)))
        records = [struct.unpack_from("<Bf", payload, 2 + 5 * i) for i in range(2)]
        self.assertEqual(records, [(tactics.INDEX["value_conc"], 20.0), (tactics.INDEX["gun_far"], 3.5)])
        self.assertEqual(tactics.encode(True, {}), bytes((1, 0)))
        # The legacy table has more values off the defaults than one command
        # carries; it is sent as a reset to the legacy column.
        self.assertGreater(len(tactics.PRESETS["legacy"]), tactics.WIRE_PAIRS)
        self.assertEqual(tactics.encode(True, tactics.PRESETS["legacy"]), bytes((2, 0)))
        near = dict(tactics.PRESETS["legacy"], run=1.0)
        self.assertEqual(tactics.encode(True, near), bytes((2, 1)) + struct.pack("<Bf", tactics.INDEX["run"], 1.0))
        with self.assertRaises(ValueError):
            tactics.encode(False, {})

    def test_baseline_file(self):
        text = tactics.render_file({"travel_cost": 0.05, "value_conc": 20, "gun_near": 1e-7})
        self.assertEqual(text, "version=1\nvalue_conc=20\ntravel_cost=0.05\ngun_near=0\n")
        for line in text.splitlines():
            self.assertRegex(line.partition("=")[2], r"\A-?[0-9]+(\.[0-9]+)?\Z")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tactics.cfg"
            self.assertEqual(tactics.main(["write", str(path), "--preset", "dry", "--set", "run=0"]), 0)
            lines = dict(line.split("=") for line in path.read_text().splitlines())
            self.assertEqual(lines, {"version": "1", "water_entry_cost": "12", "dive_min_value": "12",
                                     "dive_seconds": "6", "run": "0"})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(tactics.main(["write", str(path), "--set", "run=7"]), 1)
            self.assertEqual(tactics.main(["write", str(path), "--set", "run"]), 1)
        self.assertEqual(tactics.parse_assignments(["run=0", "gun_far=3"]), {"run": 0.0, "gun_far": 3.0})
        with self.assertRaises(ValueError):
            tactics.parse_assignments(["run=0", "run=1"])

    def test_launcher_passes_the_baseline_file(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            arguments = (base / "engine", base, base, 0, ":0", False)
            self.assertNotIn("JK_BOT_TACTICS_FILE", run.bot_environment(*arguments))
            env = run.bot_environment(*arguments, tactics_file=base / "tactics.cfg")
            self.assertEqual(env["JK_BOT_TACTICS_FILE"], str(base / "tactics.cfg"))


class HubTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.now = 30.
        self.hub = c.Hub(Path(self.tmp.name), ["kyle"], 0, clock=lambda: self.now)
        self.addCleanup(self.hub.close)
        self.child = self.hub.take_socket("kyle")
        self.addCleanup(self.child.close)
        self.cred = json.loads((self.hub.directory / "kyle.json").read_text())
        self.events = 1
        self.child.send(state(self.events))
        self.hub.pump()
        self.fence = dict(run_id=self.hub.run_id, world_epoch=1, life_epoch=1)

    def http(self, route, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.hub.port, timeout=2)
        headers = {"Authorization": "Bearer " + self.cred["token"], "Content-Type": "application/json"}
        try:
            conn.request("GET" if body is None else "POST", "/v1/bots/kyle/" + route,
                         None if body is None else json.dumps(body), headers)
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    def attach(self):
        status, response = self.http("attach", dict(self.fence, controller="Lily"))
        self.assertEqual(status, 200, response)
        return dict(self.fence, lease_id=response["lease_id"])

    def native(self, status=0, reason=0):
        """Receive one command as the engine would and acknowledge it."""
        self.hub.pump()
        data = self.child.recv(513)
        _, _, kind, length, world, life, seq = c.HEADER.unpack_from(data)
        self.child.send(c.frame(c.ACK, world, life, seq, struct.pack("<BBH", status, kind, reason)))
        self.hub.pump()
        return kind, data[c.HEADER.size:]

    def test_description_route(self):
        status, info = self.http("tactics")
        self.assertEqual(status, 200)
        self.assertEqual([row["name"] for row in info["tactics"]], list(tactics.NAMES))
        self.assertEqual(info["commit_seconds"], 8)
        self.assertEqual(set(info["presets"]), set(tactics.PRESETS))
        self.assertEqual(info["applied"], [])

    def test_preset_reaches_the_wire_and_is_recorded_when_applied(self):
        lease = self.attach()
        command = dict(lease, request_id="t1", preset="dry", values={"run": 0})
        status, result = self.http("tactics", command)
        self.assertEqual((status, result["status"]), (202, "pending"))
        kind, payload = self.native()
        self.assertEqual(kind, c.TACTICS)
        deadline = struct.unpack_from("<d", payload)[0]
        self.assertTrue(self.now < deadline <= self.now + 2)
        self.assertEqual(payload[8:10], bytes((1, 4)))
        records = dict(struct.unpack_from("<Bf", payload, 10 + 5 * i) for i in range(4))
        self.assertEqual(records, {tactics.INDEX["water_entry_cost"]: 12.0, tactics.INDEX["dive_min_value"]: 12.0,
                                   tactics.INDEX["dive_seconds"]: 6.0, tactics.INDEX["run"]: 0.0})
        self.assertEqual(self.http("commands/t1")[1]["status"], "applied")
        self.assertEqual(self.http("tactics", command)[1]["status"], "applied")  # same ID, same data
        self.assertEqual(self.http("tactics", dict(command, preset="hunter"))[0], 409)
        applied = self.http("tactics")[1]["applied"]
        self.assertEqual(len(applied), 1)
        self.assertEqual((applied[0]["preset"], applied[0]["reset"], applied[0]["values"]["run"]), ("dry", True, 0.0))

    def test_merge_without_reset_and_engine_refusals(self):
        lease = self.attach()
        self.assertEqual(self.http("tactics", dict(lease, request_id="m1", values={"gun_far": 4}))[0], 202)
        kind, payload = self.native()
        self.assertEqual(payload[8:10], bytes((0, 1)))
        # The engine's commitment window comes back as rate_limited and is not recorded.
        self.assertEqual(self.http("tactics", dict(lease, request_id="m2", values={"gun_far": 5}))[0], 202)
        self.native(status=4, reason=5)
        self.assertEqual(self.http("commands/m2")[1], dict(run_id=self.hub.run_id, request_id="m2", kind="tactics",
                                                           status="rate_limited", reason=5,
                                                           world_epoch=1, life_epoch=1))
        self.assertEqual(self.http("tactics", dict(lease, request_id="m3", reset=True))[0], 202)
        self.assertEqual(self.native()[1][8:10], bytes((1, 0)))
        self.assertEqual([row["reset"] for row in self.http("tactics")[1]["applied"]], [False, True])

    def test_bad_requests_send_nothing(self):
        lease = self.attach()
        for extra in ({}, {"preset": "nope"}, {"values": {"nope": 1}}, {"values": {"run": 2}},
                      {"values": {"run": "1"}}, {"values": []}, {"reset": "yes"}, {"preset": "dry", "mode": "x"},
                      {"values": dict(tactics.DEFAULTS)}):
            status, result = self.http("tactics", dict(lease, request_id="bad", **extra))
            self.assertEqual(status, 400, (extra, result))
        self.assertEqual(self.http("tactics", dict(self.fence, lease_id="x" * 32, request_id="b", preset="dry"))[0], 409)
        self.hub.pump()
        with self.assertRaises(BlockingIOError):
            self.child.recv(513)

    def test_command_line(self):
        credentials = self.hub.directory / "kyle.json"
        self.assertEqual(cli.main(["--credentials", str(credentials), "attach", "Lily"]), 0)
        arguments = cli.parser().parse_args(["--credentials", str(credentials), "tactics", "--preset", "hunter",
                                             "--set", "gun_far=2", "--request-id", "c1", "--wait", "0"])
        self.assertEqual(cli.execute(arguments)["status"], "pending")
        kind, payload = self.native()
        self.assertEqual((kind, payload[8]), (c.TACTICS, 1))
        records = dict(struct.unpack_from("<Bf", payload, 10 + 5 * i) for i in range(payload[9]))
        self.assertEqual(records[tactics.INDEX["gun_far"]], 2.0)
        self.assertEqual(records[tactics.INDEX["pursuit"]], 16.0)
        info = cli.execute(cli.parser().parse_args(["--credentials", str(credentials), "tactics-info"]))
        self.assertEqual(info["applied"][0]["preset"], "hunter")
        for bad in (["tactics"], ["tactics", "--set", "run=9"], ["tactics", "--set", "nope=1"]):
            self.assertEqual(cli.main(["--credentials", str(credentials), *bad]), 1)

    def test_coach_session_holds_each_preset_and_remembers_results(self):
        memory = Path(self.tmp.name) / "coach.json"
        applied, kills = [], [0]

        def world(seconds):
            """The launcher pumps the hub, the engine acknowledges, time passes, the bot scores."""
            self.hub.pump()
            try:
                data = self.child.recv(513)
            except BlockingIOError:
                data = None
            if data:
                _, _, kind, length, world_epoch, life, seq = c.HEADER.unpack_from(data)
                if kind == c.TACTICS:
                    payload = data[c.HEADER.size:]
                    hunting = tactics.INDEX["pursuit"] in {payload[10 + 5 * i] for i in range(payload[9])}
                    applied.append((self.now, "hunter" if hunting else "default"))
                self.child.send(c.frame(c.ACK, world_epoch, life, seq, struct.pack("<BBH", 0, kind, 0)))
            self.now += seconds
            kills[0] += 1 if applied and applied[-1][1] == "hunter" else 0
            self.events += 1
            self.child.send(state(self.events, kills=kills[0], deaths=len(applied)))
            self.hub.pump()

        bandit = coach.Bandit(["default", "hunter"])
        session = coach.Coach(bandit, dwell_seconds=30)
        started = self.now
        coach.session(self.cred, session, memory=memory, label="fixture", seconds=400, poll=5,
                      clock=lambda: self.now, sleep=world, log=lambda line: None)
        self.assertGreaterEqual(len(applied), 2)
        self.assertEqual([name for _, name in applied[:2]], ["default", "hunter"])
        gaps = [later[0] - earlier[0] for earlier, later in zip(applied, applied[1:])]
        self.assertTrue(all(gap >= 30 for gap in gaps), gaps)
        self.assertLess(len(applied), (self.now - started) / 30)
        stored = json.loads(memory.read_text())["fixture"]
        self.assertGreater(stored["hunter"]["plays"], stored["default"]["plays"])
        self.assertIsNone(self.hub.bots["kyle"].lease, "the session releases the bot")
        resumed = coach.Bandit(["default", "hunter"], record=coach.load_memory(memory, "fixture"))
        self.assertEqual(resumed.choose(), "hunter")


class CoachTests(unittest.TestCase):
    def test_bandit_tries_everything_then_prefers_what_works(self):
        bandit = coach.Bandit(["a", "b", "c"])
        order = []
        for reward in (0.0, 2.0, -1.0):
            arm = bandit.choose()
            order.append(arm)
            bandit.record(arm, reward)
        self.assertEqual(order, ["a", "b", "c"])
        picks = []
        for _ in range(40):
            arm = bandit.choose()
            picks.append(arm)
            bandit.record(arm, {"a": 0.0, "b": 2.0, "c": -1.0}[arm])
        self.assertGreater(picks.count("b"), 25)
        self.assertGreater(picks.count("a") + picks.count("c"), 0, "alternatives are still tested")
        restored = coach.Bandit(["a", "b", "c"], record=json.loads(json.dumps(bandit.export())))
        self.assertEqual((restored.plays, restored.total), (bandit.plays, bandit.total))
        ignored = coach.Bandit(["a"], record={"a": {"plays": -1, "total": 1}, "z": {"plays": 3, "total": 1}})
        self.assertEqual(ignored.plays, {"a": 0})
        for bad in ([], ["a", "a"]):
            with self.assertRaises(ValueError):
                coach.Bandit(bad)

    def test_spells_need_time_and_evidence(self):
        with self.assertRaises(ValueError):
            coach.Coach(coach.Bandit(["a"]), dwell_seconds=5)
        bandit = coach.Bandit(["a", "b"])
        session = coach.Coach(bandit, dwell_seconds=60, patience=3)
        score = {"kills": 0, "deaths": 0}
        self.assertEqual(session.step(score, 0), "a")
        session.begin("a", score, 0)
        self.assertIsNone(session.step({"kills": 5, "deaths": 0}, 59), "never before the spell has run")
        self.assertIsNone(session.step(score, 100), "nothing has happened yet")
        self.assertEqual(session.step({"kills": 0, "deaths": 2}, 120), "b")
        self.assertEqual((bandit.plays["a"], bandit.total["a"]), (1, -1.0))
        session.begin("b", {"kills": 0, "deaths": 2}, 125)
        # An uneventful spell ends as a draw after patience x dwell.
        self.assertIsNone(session.step({"kills": 0, "deaths": 2}, 125 + 179))
        self.assertIsNone(session.step({"kills": 0, "deaths": 2}, 125 + 181))
        self.assertEqual((bandit.plays["b"], bandit.total["b"], session.current), (1, 0.0, "b"))
        # A new match resets the score: restart the spell instead of grading it.
        session.begin("b", {"kills": 9, "deaths": 9}, 400)
        self.assertIsNone(session.step({"kills": 0, "deaths": 0}, 500))
        self.assertEqual((session.kills, session.deaths, session.since, bandit.plays["b"]), (0, 0, 500, 1))
        # Rewards are bounded so one lucky minute cannot dominate.
        self.assertIsNone(session.step({"kills": 30, "deaths": 0}, 560))
        self.assertEqual(bandit.total["b"], 4.0)


if __name__ == "__main__":
    unittest.main()

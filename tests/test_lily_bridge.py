"""Bridge admission, idempotence and sustained control on synthetic transports."""
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from bots import companion as c
from bots import companion_cli as cli


def stock_state():
    data = bytearray(144)
    struct.pack_into("<4I", data, 0, 1, 42, 14, 88)
    struct.pack_into("<iII", data, 60, -1, 4, 0xffffffff)
    return data


class LilyBridgeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.now = 31.
        self.hub = c.Hub(Path(temp.name), ("lily", "yun"), 0, experimental_ids=("lily",),
                         clock=lambda: self.now)
        self.addCleanup(self.hub.close)
        self.child = self.hub.take_socket("lily")
        self.addCleanup(self.child.close)
        self.feed(1, 1, stock_state())
        self.fence = dict(run_id=self.hub.run_id, world_epoch=1, life_epoch=1)
        attached = self.call("attach", dict(self.fence, controller="test"))[1]
        self.lease = dict(self.fence, lease_id=attached["lease_id"])

    motor_fields = {"sample_id": 73, "revision": 32, "steps": [{"duration_ms": 100, "forward": .5}]}

    def send_sense(self, seq=2, sample=73):
        payload = struct.pack("<IIIIiBBBBI19fBBBB", sample, 0, 0, 0, -1, 0, 0, 1, 1, 0,
                              0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 16, 0, 0, 0, 0,
                              0, 0, 0, 0)
        self.feed(7, seq, payload)

    def feed(self, kind, seq, data, life=1):
        self.child.send(c.frame(kind, 1, life, seq, data))
        self.hub.pump()

    def call(self, route, body=None, seat="lily"):
        return self.hub.request("GET" if body is None else "POST", seat, route, "",
                                self.hub.bots[seat].token, body)

    def motor(self, index, **extra):
        return dict(self.lease, request_id=f"lily.{index}", **(self.motor_fields | extra))

    def assert_status(self, expected, route, body):
        with self.assertRaises(c.Problem) as error:
            self.call(route, body)
        self.assertEqual(error.exception.status, expected)

    def test_scoped_capability_and_disabled_routes(self):
        self.assertEqual(self.call("capabilities")[1]["lily"]["version"], 1)
        self.assertNotIn("lily", self.call("capabilities", seat="yun")[1])
        self.assertNotIn("lily_request_floor", self.call("capabilities", seat="yun")[1])
        self.assertNotIn("lily", self.call("observation", seat="yun")[1])
        self.assertIsNone(self.call("observation")[1]["lily"]["sense"])
        with self.assertRaises(c.Problem) as error:
            self.call("motor", {}, seat="yun")
        self.assertEqual(error.exception.status, 404)

    def test_duplicate_replay_and_bounded_high_rate(self):
        self.send_sense()
        oldest = self.motor(1)
        for idx in range(1, 310):
            body = self.motor(idx)
            status, result = self.call("motor", body)
            self.assertEqual(status, 202)
            self.hub.pump()
            raw = self.child.recv(513)
            _, _, kind, _, world, life, seq = c.HEADER.unpack_from(raw)
            self.assertEqual((kind, result["action_seq"]), (20, seq))
            self.assertEqual(self.call("motor", body)[1], result)
            self.hub.pump()
            with self.assertRaises(BlockingIOError):
                self.child.recv(513)
            self.feed(2, seq, struct.pack("<BBH", 0, kind, 0))
            self.assertEqual(self.call("motor", body)[1]["status"], "applied")
        self.assert_status(409, "motor", oldest)
        self.assertEqual(self.call("strategy", dict(self.lease, request_id="lily-1", mode="recover"))[0], 202)

    def test_pending_receipt_survives_eviction(self):
        self.send_sense()
        with patch.object(c, "LILY_HISTORY", 2):
            for index in (1, 2):
                self.call("motor", self.motor(index))
            self.hub.pump()
            self.child.recv(513)  # First command remains unacknowledged.
            second = self.child.recv(513)
            self.assert_status(429, "motor", self.motor(3))
            seq = c.HEADER.unpack_from(second)[-1]
            self.feed(2, seq, struct.pack("<BBH", 0, 20, 0))
            self.call("motor", self.motor(3))
            self.assertEqual(self.call("motor", self.motor(1))[1]["status"], "pending")
            self.assert_status(409, "motor", self.motor(2))

    def test_second_lease_cannot_rebind_or_replay_first_controllers_receipt(self):
        self.send_sense()
        first = self.call("motor", self.motor(1))[1]
        self.hub.pump()
        self.child.recv(513)
        self.feed(2, first["action_seq"], struct.pack("<BBH", 0, 20, 0))
        self.call("release", dict(self.lease, request_id="release-first"))
        second_ticket = self.call("attach", dict(self.fence, controller="second"))[1]
        self.lease = dict(self.fence, lease_id=second_ticket["lease_id"])
        self.assert_status(409, "motor", self.motor(1))
        self.assertEqual(second_ticket["lily_request_floor"], "1")
        with patch.object(c, "LILY_HISTORY", 2):
            second = self.call("motor", self.motor(2))[1]
            retained = self.call("commands/lily.1")[1]
            self.assertEqual((retained["action_seq"], retained["status"]), (first["action_seq"], "applied"))
            self.assertNotEqual(first["action_seq"], second["action_seq"])
            self.call("motor", self.motor(3))
            with self.assertRaises(c.Problem) as error:
                self.call("commands/lily.1")
            self.assertEqual(error.exception.status, 404)
            self.assert_status(409, "motor", self.motor(1))
            self.assertEqual(self.call("capabilities")[1]["lily_request_floor"], "3")

    def test_telemetry_freshness_and_offer_supersession(self):
        self.send_sense()
        self.feed(5, 3, struct.pack("<IIBIiBB5f", 73, 12, 1, 7, 3, 0, 0, 1, 2, 3, 4, 5))
        self.feed(7, 4, b"malformed")
        self.now += 1.2
        self.assertEqual(self.call("observation")[1]["lily"]["sense"]["sample_id"], 73)
        self.assert_status(409, "motor", self.motor(1))
        self.send_sense(5, 74)
        old = dict(self.lease, request_id="lily.1", sample_id=74, revision=1, offer_id=12, node=7)
        self.feed(5, 6, struct.pack("<IIBIiBB5f", 74, 13, 1, 7, 3, 0, 0, 1, 2, 3, 4, 5))
        self.assert_status(409, "commit", old)
        self.now += 2.1
        self.send_sense(7, 75)
        self.assert_status(409, "commit", old | {"sample_id": 75, "offer_id": 13})

    def test_stale_fence_or_sample_and_malformed_action(self):
        self.send_sense()
        self.assert_status(400, "motor", self.motor(1, steps=[]))
        self.assert_status(409, "motor", self.motor(1, sample_id=999))
        self.assert_status(409, "motor", self.motor(1) | {"world_epoch": 2})
        self.assert_status(409, "motor", self.motor(1) | {"lease_id": "expired"})
        self.now += 4
        self.assert_status(409, "motor", self.motor(1))
        self.feed(1, 10, stock_state(), life=2)
        self.assertIsNone(self.call("observation")[1]["lily"]["sense"])

    def test_terminal_survives_duplicate_notices_and_successor_in_same_pump(self):
        def send_progress(seq, action, phase):
            progress = struct.pack("<IIIBBBBIi", action, 19, 73, 2, phase, 0, 2 if phase == 4 else 0, 50, -1)
            self.child.send(c.frame(6, 1, 1, seq, progress))
        send_progress(2, 11, 4)
        send_progress(3, 11, 4)
        send_progress(4, 12, 3)
        self.hub.pump()
        telemetry = self.call("observation")[1]["lily"]
        self.assertEqual(telemetry["progress"]["action_seq"], 12)
        self.assertEqual([t["action_seq"] for t in telemetry["terminals"]], [11])
        for n in range(20):
            send_progress(5+n, 12+n, 4)
            self.hub.pump()
        self.assertEqual([t["action_seq"] for t in self.call("observation")[1]["lily"]["terminals"]],
                         list(range(16,32)))
        self.feed(1, 25, stock_state(), life=2)
        self.assertEqual(self.call("observation")[1]["lily"]["terminals"], [])

    def test_offer_commit_and_cli_observation(self):
        self.send_sense()
        offers = struct.pack("<IIBIiBB5f", 73, 12, 1, 7, 3, 0, 0, 1, 2, 3, 4, 5)
        self.feed(5, 3, offers)
        cred = self.hub.directory / "lily.json"
        ticket = cred.with_suffix(".lease.json")
        ticket.write_text(json.dumps(self.lease))
        ticket.chmod(0o600)
        args = cli.parser().parse_args
        def command(*argv):
            return cli.execute(args(["--credentials", str(cred), *argv]))
        self.assertEqual(command("observe")["lily"]["offers"]["choices"][0]["node"], 7)
        fields = {"sample_id": 73, "revision": 19, "offer_id": 12, "node": 7}
        self.assert_status(409, "commit", self.lease | fields | {"request_id": "lily.1", "node": 9})
        path = cred.parent / "route.json"
        path.write_text(json.dumps(fields))
        result = command("commit", str(path), "--request-id", "lily.1", "--wait", "0")
        self.assertEqual(result["status"], "pending")
        self.assertEqual(command("command", "lily.1"), result)
        self.hub.pump()
        raw = self.child.recv(513)
        self.assertEqual(struct.unpack_from("<IIII", raw, 28), (73, 19, 12, 7))
        self.assert_status(409, "motor", self.motor(1))
        self.feed(6, 4, struct.pack("<IIIBBBBIi", result["action_seq"], 19, 73, 1, 4, 0, 1, 20, 7))
        self.assertEqual(command("observe")["lily"]["progress"]["outcome"], "arrived")
        # Even a wall clock behind an operator's previous numeric ID cannot
        # generate an alias for an already accepted request.
        with patch.object(cli.time, "time_ns", return_value=1):
            self.assertEqual(command("commit", str(path), "--wait", "0")["request_id"], "lily.2")

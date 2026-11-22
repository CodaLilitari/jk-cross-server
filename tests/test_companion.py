import http.client
import json
import socket
import time
import struct
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from bots import companion as c
from bots import companion_cli as cli


def state(world=1, life=1, seq=1, flags=4):
    data = bytearray(144)
    struct.pack_into("<4I", data, 0, 1, 42, 14, 88)
    struct.pack_into("<f", data, 32, 100.)
    struct.pack_into("<iII", data, 60, -1, flags, 0xffffffff)
    return c.frame(c.STATE, world, life, seq, data)


class CompanionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.now = 30.
        self.hub = c.Hub(Path(self.tmp.name), ["kyle", "jan"], 0, allow_chat=True, clock=lambda: self.now)
        self.addCleanup(self.hub.close)
        self.child = self.hub.take_socket("kyle")
        self.addCleanup(self.child.close)
        self.cred = json.loads((self.hub.directory / "kyle.json").read_text())
        self.child.send(state())
        self.hub.pump()
        self.fence = dict(run_id=self.hub.run_id, world_epoch=1, life_epoch=1)

    def http(self, route, body=None, override=None, bot="kyle"):
        conn = http.client.HTTPConnection("127.0.0.1", self.hub.port, timeout=2)
        headers = {"Authorization": "Bearer " + self.cred["token"], "Content-Type": "application/json"}
        headers.update(override or {})
        try:
            conn.request("GET" if body is None else "POST", "/v1/bots/" + bot + "/" + route,
                         None if body is None else json.dumps(body), headers)
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    def attach(self):
        status, response = self.http("attach", dict(self.fence, controller="Lily"))
        self.assertEqual(status, 200, response)
        return dict(self.fence, lease_id=response["lease_id"])

    def test_game_socket_and_scoped_http(self):
        self.assertEqual(self.http("observation")[1]["state"]["health"], 100)
        self.assertEqual(self.http("observation", bot="jan")[0], 401)
        self.assertEqual(self.http("observation", override={"Host": "elsewhere.test"})[0], 403)
        self.assertEqual(self.http("observation", override={"Origin": "https://elsewhere.test"})[0], 403)
        self.assertEqual((self.hub.directory / "kyle.json").stat().st_mode & 0o777, 0o600)
        self.assertNotIn(self.cred["token"], str(self.http("capabilities")))
        for bad in (b"short", state() + b"x", state()[:23], b"x"*513):
            self.child.send(bad)
        self.hub.pump()
        self.assertEqual(self.http("observation")[1]["state"]["health"], 100)

    def test_full_payload_idempotency_and_native_ack(self):
        lease = self.attach()
        command = dict(lease, request_id="a", text="Hello")
        self.assertEqual(self.http("say", command)[0], 202)
        self.hub.pump()
        data = self.child.recv(513)
        _, _, kind, length, world, life, seq = c.HEADER.unpack_from(data)
        self.assertEqual((kind, length, data[28:]), (c.SAY, 13, b"Hello"))
        self.assertEqual(self.http("say", command)[1]["status"], "pending")
        self.assertEqual(self.http("say", dict(command, text="different"))[0], 409)
        self.hub.pump()
        with self.assertRaises(BlockingIOError):
            self.child.recv(513)
        self.child.send(c.frame(c.ACK, world, life, seq, struct.pack("<BBH", 0, c.SAY, 0)))
        self.hub.pump()
        self.assertEqual(self.http("commands/a")[1]["status"], "applied")
        self.assertEqual(self.http("say", command)[1]["status"], "applied")
        self.assertEqual(self.http("say", dict(command, request_id="b"))[0], 429)
        self.assertEqual(self.http("say", dict(command, request_id="z", text=" AdMin prove xxx"))[0], 400)

    def test_epoch_fence_and_expiry(self):
        lease = self.attach()
        self.assertEqual(self.http("attach", dict(self.fence, controller="Coda"))[0], 409)
        self.assertEqual(self.http("strategy", dict(lease, request_id="x", mode="recover"))[0], 202)
        self.hub.pump()
        self.assertEqual(c.HEADER.unpack_from(self.child.recv(513))[2], c.STRATEGY)
        self.now += 31
        self.hub.pump()
        self.assertEqual(c.HEADER.unpack_from(self.child.recv(513))[2], c.RELEASE)
        self.assertEqual(self.http("commands/x")[1]["status"], "unconfirmed")
        self.assertEqual(self.http("renew", lease)[0], 409)
        self.child.send(state(seq=2))
        self.hub.pump()
        lease = self.attach()
        self.child.send(state(life=2, seq=3))
        self.hub.pump()
        self.assertEqual(self.http("strategy", dict(lease, request_id="y", mode="pressure"))[0], 409)

    def test_queue_and_event_bounds(self):
        lease = self.attach()
        for i in range(c.MAX_PENDING):
            self.assertEqual(self.http("strategy", dict(lease, request_id=str(i), mode="resource"))[0], 202)
        self.assertEqual(self.http("strategy", dict(lease, request_id="over", mode="recover"))[0], 429)
        for i in range(c.EVENT_HISTORY + 5):
            self.child.send(c.frame(c.CHAT, 1, 1, i+2, struct.pack("<iI", 2, 77) + b"hi"))
            self.hub.pump()
        events = self.http("events?after=0")[1]
        self.assertTrue(events["gap"])
        self.assertLessEqual(len(events["events"]), c.EVENT_HISTORY)

    def test_cli_controller_cycle_and_browser_adapter(self):
        channel = self.hub.open_browser_channel("jan")
        self.addCleanup(channel.close)
        self.assertFalse(channel.enqueue_native_frame(b"x"*513))
        self.assertTrue(channel.enqueue_native_frame(state()))
        self.hub.pump()
        creds = self.hub.directory / "jan.json"

        def command(*args):
            return cli.execute(cli.parser().parse_args(["--credentials", str(creds), *args]))

        self.assertEqual(command("observe")["state"]["net_id"], 42)
        ticket = command("attach", "Coda")
        self.assertNotIn("lease_id", ticket)
        with self.assertRaisesRegex(ValueError, "409"):
            command("attach", "Lily")
        self.assertEqual(command("renew")["expires_in"], 30)
        issued = command("strategy","pressure","--ttl-seconds","7","--range","1.4","--risk","0.7",
                         "--request-id","press","--wait","0")
        self.assertEqual(issued["status"], "pending")
        self.hub.pump()
        frames = channel.outgoing_frames()
        self.assertEqual(len(frames), 1)
        packet = frames[0]
        _, _, kind, _, world, life, seq = c.HEADER.unpack_from(packet)
        deadline, mode, weapon, resource, distance, risk, net, guid = c.STRATEGY_PAYLOAD.unpack_from(packet, 20)
        self.assertEqual((deadline,mode,weapon,resource,net,guid), (self.now+7,1,0,0,0,0))
        self.assertAlmostEqual(distance,1.4)
        self.assertAlmostEqual(risk,.7)
        channel.enqueue_native_frame(c.frame(c.ACK,world,life,seq,struct.pack("<BBH",0,kind,0)))
        self.hub.pump()
        self.assertEqual(command("command","press")["status"], "applied")
        self.assertEqual(command("release","--request-id","end","--wait","0")["status"], "pending")
        self.hub.pump()
        release = channel.outgoing_frames()[0]
        self.assertEqual(c.HEADER.unpack_from(release)[2], c.RELEASE)
        self.assertFalse(Path(ticket["lease_file"]).exists())
        with self.assertRaises(RuntimeError):
            self.hub.take_socket("jan")

    def test_rejected_and_missing_acks(self):
        lease = self.attach()
        body = dict(lease, request_id="a", text="Hi")
        self.assertEqual(self.http("say", body)[0], 202)
        self.hub.pump()
        _, _, kind, _, world, life, seq = c.HEADER.unpack_from(self.child.recv(513))
        for wrong in (c.frame(c.ACK,world,life+1,seq,struct.pack("<BBH",0,kind,0)),
                      c.frame(c.ACK,world,life,seq,struct.pack("<BBH",0,c.STRATEGY,0))):
            self.child.send(wrong)
        self.hub.pump()
        self.assertEqual(self.http("commands/a")[1]["status"], "pending")
        self.child.send(c.frame(c.ACK,world,life,seq,struct.pack("<BBH",4,kind,5)))
        self.hub.pump()
        result = self.http("commands/a")[1]
        self.assertEqual((result["status"],result["reason"]),("rate_limited",5))
        self.assertEqual(self.http("strategy",dict(lease,request_id="b",mode="resource",ttl_seconds=.1))[0],202)
        self.hub.pump()
        self.now += 1
        self.hub.pump()
        self.assertEqual(self.http("commands/b")[1]["status"],"unconfirmed")

    def test_invalid_parameters_and_untrusted_observations(self):
        lease = self.attach()
        base = dict(lease,request_id="a",mode="recover")
        for more in ({"risk":True},{"range":.1},{"ttl_seconds":31},{"resource":65536},
                     {"focus_guid":1},{"mode":"console"},{"bogus":False}):
            self.assertGreaterEqual(self.http("strategy",dict(base,**more))[0],400)
        self.hub.allow_chat = False
        self.assertEqual(self.http("say",dict(lease,request_id="say",text="Hello"))[0],403)
        for i, raw in enumerate((b"admin prove xxx",b"newline\n",b"bad\xff")):
            self.child.send(c.frame(c.CHAT,1,1,i+2,struct.pack("<iI",2,66)+raw))
        self.child.send(c.frame(c.SOUND,1,1,6,struct.pack("<I5f",1,2.,3.,4.,.8,.5)))
        self.hub.pump()
        result = self.http("events")[1]
        self.assertEqual([e["kind"] for e in result["events"]],["sound"])
        self.assertEqual(result["wire_dropped"],4)
        self.assertNotIn("net_id",result["events"][0])
        self.assertEqual(self.http("observation",override={"Authorization":"Bearer "})[0],401)

    def test_idle_http_connection_does_not_block_shutdown_or_observation(self):
        idle = socket.create_connection(("127.0.0.1", self.hub.port))
        self.addCleanup(idle.close)
        idle.sendall(b"POST /v1/")
        self.assertEqual(self.http("observation")[0],200)
        start = time.monotonic()
        self.hub.close()
        self.assertLess(time.monotonic()-start,1.0)

    def test_receipt_cache_cannot_grow_with_full_repeated_leases(self):
        with patch.object(c, "COMMAND_HISTORY", 3):
            for round_no in range(4):
                lease = self.attach()
                for i in range(3):
                    req = dict(lease,request_id=f"r{round_no}-{i}",mode="pressure")
                    self.assertEqual(self.http("strategy",req)[0],202)
                self.assertEqual(self.http("strategy",dict(lease,request_id="over",mode="resource"))[0],429)
                self.assertEqual(self.http("release",dict(lease,request_id=f"end-{round_no}"))[0],202)
                self.hub.pump()
                packet = self.child.recv(513)
                _,_,kind,_,world,life,seq = c.HEADER.unpack_from(packet)
                self.child.send(c.frame(c.ACK,world,life,seq,struct.pack("<BBH",0,kind,0)))
                self.hub.pump()
                self.assertLessEqual(len(self.hub.bots["kyle"].commands),4)

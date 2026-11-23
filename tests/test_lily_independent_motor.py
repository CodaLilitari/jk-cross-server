import csv
import json
import os
import socket
import subprocess
import time
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1] / "native/tests/stock_water_replay"
sys.path.insert(0, str(HERE))
import evaluate_motor as motor


class IndependentMotorTests(unittest.TestCase):
    def test_holds_whole_original_ticks(self):
        self.assertEqual([motor.hold_ticks(a, .041) for a in motor.ARMS], [1, 14, 3, 1])
        self.assertEqual(motor.hold_ticks("hold550", .026), 22)
        self.assertEqual(motor.hold_ticks("hold100", .05), 2)

    def test_quantization_and_guarded_actions(self):
        def act(**step):
            return {"action":"motor", "steps":[dict(duration_ms=41, **step)]}
        self.assertEqual(motor.quantized(act(forward=.425, turn=-.996, buttons=3), 41), [42,0,-100,0,3])
        self.assertEqual(motor.quantized({"action":"wait"}, 41), [0]*5)
        for invalid in [act(forward=float("nan")), act(turn=2), act(buttons=4), act(force=21),
                        act(weapon=1), {"action":"baseline"}, act(forward=0) | {"steps":[]}]:
            with self.assertRaises(ValueError):
                motor.quantized(invalid, 41)

    def test_missing_build_keeps_every_assignment(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/"out"
            args = ["--source",tmp,"--build",tmp,"--map",tmp,"--output",str(out)]
            self.assertEqual(motor.main(args), 1)
            receipt = json.loads((out/"receipt.json").read_bytes())
            self.assertEqual(len(receipt["episodes"]), 108)
            self.assertTrue(all(row["physical_success"] is None for row in receipt["episodes"]))

    def test_pair_mismatch_censors_credit(self):
        group = [dict(episode_id="pose", owner="model", initial_observation_sha256="same", seed=1,
                      initial_quantized=[q,0,0,0,0], ownership_complete=True) for q in (1,2)]
        motor.validate_pairs(group)
        self.assertTrue(all(r["physical_success"] is None for r in group))


NATIVE = ("LILY_TEST_SOURCE","LILY_TEST_BUILD","LILY_TEST_MAP")


@unittest.skipUnless(all(os.environ.get(k) for k in NATIVE),"supply stock replay source, build and owned map")
class NativeInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.base = Path(cls.directory.name)
        cls.exe, cls.geometry, _ = motor.build_replay(*(Path(os.environ[k]) for k in NATIVE),cls.base,
                                                       independent_motor=True)
        with motor.CASES.open() as stream:
            cls.row = next(csv.DictReader(stream,delimiter="\t"))

    def fixture(self, root, hold=1):
        native, peer = socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
        self.addCleanup(peer.close)
        with native, (root/"log").open("wb") as log:
            row = self.row
            env = motor.case_environment(row,0)
            env.update(LILY_MODEL_FD=str(native.fileno()), LILY_HOLD_TICKS=str(hold),
                       LILY_BANK_TRACE=str(root/"native.jsonl"), LILY_INDEPENDENT_TRACE=str(root/"motor.jsonl"),
                       LILY_INDEPENDENT_ORIGIN=str(root/"start.json"))
            args = [self.exe,self.geometry,*[row[k] for k in ("origin","wet","dry","start_sector","control_dt")]]
            child = subprocess.Popen(args,env=env,stdout=log,stderr=log,pass_fds=(native.fileno(),))
        def stop():
            if child.poll() is None:
                child.kill()
            child.wait()
        self.addCleanup(stop)
        peer.settimeout(3)
        return child,peer

    def test_stack_rejects_bad_eof_and_stalled_packets(self):
        for name, packet in [
            ("wrong_reply_tick",motor.REPLY.pack(1,0,0,0,0,0)),
            ("invalid_axis",motor.REPLY.pack(0,101,0,0,0,0)),
            ("invalid_buttons",motor.REPLY.pack(0,0,0,0,0,4)),
            ("invalid_reply_size",b"a"), ("invalid_reply_size",b"x"*10),
            ("ipc_closed",None), ("ipc_timeout","stall")]:
            with self.subTest(reason=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                child,peer = self.fixture(root)
                first = json.loads(peer.recv(2048))
                self.assertEqual((first["tick"],first["step"],first["sense"]["buttons"]),(0,0,0))
                before = time.monotonic()
                if packet is None:
                    peer.close()
                elif packet != "stall":
                    peer.sendall(packet)
                self.assertEqual(child.wait(timeout=2),3)
                self.assertIn("INDEPENDENT_ERROR "+name,(root/"log").read_text())
                self.assertFalse(any(json.loads(line)["event"] in ("terminal","control")
                                     for line in (root/"native.jsonl").read_bytes().splitlines()))
                if packet == "stall":
                    self.assertLess(time.monotonic()-before,1.7)

    def test_held_jump_edges_and_repress_match_applied_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            child,peer = self.fixture(root,hold=2)
            for tick,mask in [(0,1),(2,0),(4,1)]:
                obs = json.loads(peer.recv(2048))
                self.assertEqual(obs["tick"],tick)
                peer.sendall(motor.REPLY.pack(tick,0,0,0,0,mask))
            self.assertEqual(json.loads(peer.recv(2048))["tick"],6)
            peer.close()
            self.assertEqual(child.wait(timeout=2),3)
            records = [json.loads(line) for line in (root/"motor.jsonl").read_bytes().splitlines()]
            inputs = [r for r in records if r["event"]=="input"]
            self.assertEqual([r["buttons"] for r in inputs],[1,1,0,0,1,1])
            self.assertEqual([r["presses"] for r in inputs],[1,0,0,0,1,0])
            self.assertEqual([r["source_tick"] for r in inputs],[0,0,2,2,4,4])
            self.assertEqual([r["sense"]["buttons"] for r in records if r["event"]=="observation"],
                             [0,1,1,0,0,1,1])

    def test_evidence_joins_detect_changed_observation_missing_tick_and_foreign_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job = next(j for j in motor.make_jobs([self.row],["every_tick"],True) if j["yaw_deg"]==0)
            result = motor.run_trial(job,self.row,self.exe,self.geometry,root,motor.POLICY,motor.MODEL)
            self.assertTrue(result["ownership_complete"])
            path = root/(job["episode_id"]+"-every_tick")
            raw = (path/"motor.jsonl").read_bytes().splitlines(keepends=True)
            with self.assertRaisesRegex(ValueError,"incorrect_initial_actor"):
                motor.assess(job,path,0 if result["physical_success"] else 1,dict(self.row,x=3.1))
            with self.assertRaisesRegex(ValueError,"incorrect_initial_heading"):
                motor.assess(dict(job,yaw_deg=90),path,0 if result["physical_success"] else 1,self.row)
            for damaged in [
                [raw[0],json.dumps(json.loads(raw[1])|{"owner":"baseline"}).encode()+b"\n",*raw[2:]],
                [*raw[:2],*raw[4:]],
                [*raw[:2], raw[2].replace(b'"state":', b'"state": '),*raw[3:]],
                [*raw[:3],json.dumps(json.loads(raw[3])|{"source_tick":0}).encode()+b"\n",*raw[4:]],
            ]:
                (path/"motor.jsonl").write_bytes(b"".join(damaged))
                with self.assertRaises(ValueError):
                    motor.assess(job,path,0 if result["physical_success"] else 1,self.row)


if __name__ == "__main__":
    unittest.main()

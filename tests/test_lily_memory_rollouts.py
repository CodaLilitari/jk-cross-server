"""State journals must prove both sequential inference and actual physical controls."""
import copy
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile
import unittest

from bots.lily import motor_memory
if importlib.util.find_spec("numpy"):
    from bots.lily import memory_search
from test_lily_contact_motor import observation
from test_lily_memory_motor import g4_model
from test_lily_recovery_evaluation import one_loss, write_rows


@unittest.skipUnless(importlib.util.find_spec("numpy"),"memory search uses optional NumPy")
class MemoryRolloutTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("scripts.bot_development.analysis.memory_rollouts"),
                             "explicit-state replay is not implemented")
        self.r = importlib.import_module("scripts.bot_development.analysis.memory_rollouts")
        self.values = memory_search.initial_model(g4_model(),"carried")
        self.values["residual"]["o"] = [[1.,-.5,.2,0.] for _ in range(6)]
        self.source = motor_memory.policy_source(self.values).encode()

    def test_session_carries_state_and_rejects_duplicate_tick(self):
        session = self.r.Session(self.source,40)
        entries = []
        for tick in range(3):
            raw = (json.dumps(observation(tick,0))+"\n").encode()
            entry = session.advance(raw)
            self.assertEqual(entry["observation_sha256"],hashlib.sha256(raw).hexdigest())
            entries.append(entry)
        self.assertEqual(entries[1]["state_before_sha256"],entries[0]["state_after_sha256"])
        self.assertNotEqual(entries[2]["state_after_sha256"],entries[0]["state_after_sha256"])
        with self.assertRaisesRegex(ValueError,"tick"):
            session.advance(raw)
        fresh = self.r.Session(self.source,40)
        self.assertEqual(fresh.advance((json.dumps(observation(0,0))+"\n").encode()),entries[0])

    def fixture(self,base):
        work = base/"attempt"
        work.mkdir()
        job,case,_ = one_loss(work)
        policy,model = base/"policy.py",base/"model.json"
        policy.write_bytes(self.source)
        model.write_bytes(motor_memory.canonical(self.values)+b"\n")
        frames = [json.loads(line) for line in (work/"motor.jsonl").read_bytes().splitlines()]
        raw = (json.dumps(frames[0])+"\n").encode()
        journal = self.r.Session(self.source,40).advance(raw)
        q = journal["quantized"]
        frames[1].update(axes=[x/100 for x in q[:4]],buttons=q[4],presses=q[4])
        native = [json.loads(line) for line in (work/"native.jsonl").read_bytes().splitlines()]
        native[1].update(axes=frames[1]["axes"],buttons=q[4])
        write_rows(work/"motor.jsonl",frames)
        write_rows(work/"native.jsonl",native)
        write_rows(work/"decisions.jsonl",[journal])
        assignment = dict(role="train",candidate_id="r-g01-c00",job=job,
                          model=self.r.model_identity(policy,model),fixture_source_sha256=self.r.motor.digest(Path(self.r.motor.__file__)))
        self.r.write(work/"assignment.json",assignment)
        status = dict(schema=1,started_at_utc=self.r.old.now(),ended_at_utc=self.r.old.now(),elapsed_seconds=.01,
                      engine_returncode=1,worker_returncode=0,timed_out=None,error=None)
        self.r.write(work/"process.json",status)
        return assignment,work,case,policy,model,status

    def test_clean_and_late_failure_reinfer_without_state_contamination(self):
        with tempfile.TemporaryDirectory() as temp:
            a,work,case,policy,model,status = self.fixture(Path(temp))
            result = self.r.audit_attempt(a,work,case,policy,model)
            self.assertEqual(result["status"],"complete")
            self.assertFalse(result["row"]["physical_success"])
            self.assertEqual(result["reinferred_decisions"],1)
            status["worker_returncode"] = 7
            (work/"process.json").write_text(json.dumps(status))
            result = self.r.audit_attempt(a,work,case,policy,model)
            self.assertEqual(result["status"],"censored")
            self.assertEqual(result["reinferred_decisions"],1)
            self.assertEqual(result["observed_native_terminal"]["terminal"],"died")
            for key in ("state_before_sha256","state_after_sha256","observation_sha256"):
                rows = [json.loads(line) for line in (work/"decisions.jsonl").read_bytes().splitlines()]
                rows[0][key] = "00"*32
                write_rows(work/"decisions.jsonl",rows)
                with self.subTest(key=key), self.assertRaises(ValueError):
                    self.r.audit_attempt(a,work,case,policy,model)
                raw = (work/"motor.jsonl").read_bytes().splitlines(keepends=True)[0]
                write_rows(work/"decisions.jsonl",[self.r.Session(self.source,40).advance(raw)])

    def test_censored_controls_are_checked_without_journal_or_terminal(self):
        with tempfile.TemporaryDirectory() as temp:
            a,work,case,policy,model,status = self.fixture(Path(temp))
            (work/"process.json").unlink()
            (work/"decisions.jsonl").write_bytes(b"")
            events = [json.loads(line) for line in (work/"native.jsonl").read_bytes().splitlines()]
            write_rows(work/"native.jsonl",events[:-1])
            (work/"engine.log").write_bytes(b"")
            result = self.r.audit_attempt(a,work,case,policy,model)
            self.assertEqual(result["status"],"censored")
            self.assertEqual(result["verified_controls"],1)
            events[1]["axes"][0] = .03 if events[1]["axes"][0] != .03 else .04
            write_rows(work/"native.jsonl",events[:-1])
            with self.assertRaisesRegex(ValueError,"action_does_not_match_decision"):
                self.r.audit_attempt(a,work,case,policy,model)

    def test_journal_tail_still_rejects_broken_hash_chain_without_observations(self):
        with tempfile.TemporaryDirectory() as temp:
            a,work,case,policy,model,status = self.fixture(Path(temp))
            (work/"process.json").unlink()
            (work/"native.jsonl").unlink()
            (work/"motor.jsonl").unlink()
            (work/"engine.log").write_bytes(b"")
            first = json.loads((work/"decisions.jsonl").read_text())
            second = dict(first,tick=1,state_before_sha256="ab"*32)
            write_rows(work/"decisions.jsonl",[first,second])
            with self.assertRaisesRegex(ValueError,"state chain"):
                self.r.audit_attempt(a,work,case,policy,model)
            second["state_before_sha256"] = first["state_after_sha256"]
            write_rows(work/"decisions.jsonl",[first,second])
            result = self.r.audit_attempt(a,work,case,policy,model)
            self.assertEqual(result["reinferred_decisions"],0)
            self.assertEqual(result["unverifiable_journal"],2)

    def test_late_worker_failure_does_not_hide_conflicting_engine_terminal(self):
        with tempfile.TemporaryDirectory() as temp:
            a,work,case,policy,model,status=self.fixture(Path(temp))
            status.update(engine_returncode=0,worker_returncode=7)
            (work/"process.json").write_text(json.dumps(status))
            (work/"engine.log").write_bytes(b"")
            with self.assertRaisesRegex(ValueError,"terminal"):
                self.r.audit_attempt(a,work,case,policy,model)

    def test_incomplete_assigned_record_is_invalid_even_without_observations(self):
        with tempfile.TemporaryDirectory() as temp:
            a,work,case,policy,model,status=self.fixture(Path(temp))
            for name in ("process.json","motor.jsonl","decisions.jsonl","start.json"):
                (work/name).unlink()
            (work/"engine.log").write_bytes(b"")
            write_rows(work/"native.jsonl",[dict(event="assigned",sector=10)])
            with self.assertRaisesRegex(ValueError,"assigned"):
                self.r.audit_attempt(a,work,case,policy,model)

    def test_legacy_control_mismatch_without_journal_or_terminal_is_invalid(self):
        from test_lily_outcome_rollouts import RolloutTests
        with tempfile.TemporaryDirectory() as temp:
            a,work,case,policy,model,status=RolloutTests().fixture(Path(temp))
            (work/"process.json").unlink()
            (work/"decisions.jsonl").write_bytes(b"")
            (work/"engine.log").write_bytes(b"")
            native=[json.loads(x) for x in (work/"native.jsonl").read_bytes().splitlines()]
            native[1]["axes"][0]=.05
            write_rows(work/"native.jsonl",native[:-1])
            with self.assertRaisesRegex(ValueError,"action_does_not_match_decision|mismatch"):
                self.r.audit_attempt(a,work,case,policy,model)

    @unittest.skipUnless(hasattr(socket,"SOCK_SEQPACKET"),"Unix synchronous replay transport")
    def test_real_worker_emits_nine_byte_controls_and_state_journal(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            policy,model,journal = root/"policy.py",root/"model.json",root/"journal.jsonl"
            policy.write_bytes(self.source)
            model.write_bytes(motor_memory.canonical(self.values))
            first,second = socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
            with first,second:
                with subprocess.Popen([sys.executable,"-m","scripts.bot_development.analysis.memory_rollouts","worker",
                                       str(second.fileno()),str(policy),str(model),str(journal),"40"],pass_fds=(second.fileno(),),
                                      stdout=subprocess.PIPE,stderr=subprocess.PIPE) as process:
                    second.close()
                    first.settimeout(5)
                    for tick in range(2):
                        first.send((json.dumps(observation(tick,0))+"\n").encode())
                        reply = first.recv(100)
                        self.assertEqual(len(reply),9)
                        self.assertEqual(struct.unpack("<I4bB",reply)[0],tick)
                    first.close()
                    _,error = process.communicate(timeout=5)
                    self.assertEqual(process.returncode,0,error.decode())
            rows = [json.loads(line) for line in journal.read_bytes().splitlines()]
            self.assertEqual(rows[0]["state_after_sha256"],rows[1]["state_before_sha256"])


if __name__ == "__main__":
    unittest.main()

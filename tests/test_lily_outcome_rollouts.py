"""Process, raw-stream and start witnesses for autonomous outcome trials."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

from test_lily_recovery_evaluation import one_loss
from scripts.bot_development.analysis import outcome_rollouts as r


class RolloutTests(unittest.TestCase):
    def test_native_timeout_keeps_real_killed_wait_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            status = {}
            with open(Path(tmp)/"log", "wb") as log:
                r.wait_native([sys.executable, "-c", "import time; time.sleep(10)"], {}, log, status, timeout=.08)
            self.assertEqual(status["timed_out"], "engine")
            self.assertLess(status["engine_returncode"], 0)

    def fixture(self, base):
        work = base/"attempt"
        work.mkdir()
        job, case, row = one_loss(work)
        model = json.loads((r.ROOT/"bots/lily/models/water_recovery_v3.json").read_bytes())
        model.update(w2=[[0.]*32 for _ in range(6)], b2=[0., 0., 0., 0., -20., -20.])
        weights, policy = base/"model.json", base/"policy.py"
        weights.write_bytes(r.contact.canonical(model))
        policy.write_text(r.contact.policy_source(model))
        assignment = dict(role="train", candidate_id="g01-c00", job=job,
                          model=r.model_identity(policy, weights), fixture_source_sha256=r.motor.digest(Path(r.motor.__file__)))
        r.write(work/"assignment.json", assignment)
        status = dict(schema=1, started_at_utc=r.now(), ended_at_utc=r.now(), elapsed_seconds=.01,
                      engine_returncode=1, worker_returncode=0, timed_out=None, error=None)
        r.write(work/"process.json", status)
        return assignment, work, case, policy, weights, status

    def test_raw_loss_then_late_worker_failure_and_changed_journal(self):
        with tempfile.TemporaryDirectory() as tmp:
            assignment, work, case, policy, weights, status = self.fixture(Path(tmp))
            args = assignment, work, case, policy, weights
            audit = r.audit_attempt(*args)
            self.assertIs(audit["row"]["physical_success"], False)
            self.assertEqual(audit["reinferred_decisions"], 1)
            self.assertEqual(audit["raw"]["worker.log"]["bytes"], 0)
            status.update(worker_returncode=7, error={"type":"ValueError", "message":"worker_failed"})
            (work/"process.json").write_text(json.dumps(status))
            audit = r.audit_attempt(*args)
            self.assertEqual(audit["status"], "censored")
            self.assertIsNone(audit["row"])
            self.assertEqual(audit["observed_native_terminal"]["terminal"], "died")
            data = json.loads((work/"decisions.jsonl").read_text())
            data["quantized"][0] = 91
            (work/"decisions.jsonl").write_text(json.dumps(data)+"\n")
            with self.assertRaisesRegex(ValueError, "frozen decision"):
                r.audit_attempt(*args)

    def test_source_claim_job_and_clean_marker_cannot_disagree(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, w, c, p, m, _ = self.fixture(Path(tmp))
            with self.assertRaises(ValueError):
                r.audit_attempt(dict(a, candidate_id="other"), w, c, p, m)
            with self.assertRaises(ValueError):
                r.audit_attempt(a, w, dict(c, dry="41"), p, m)
            (w/"engine.log").write_text("STOCK FULL TICK landed=1\n")
            with self.assertRaises(ValueError):
                r.audit_attempt(a, w, c, p, m)
            p.write_text("raise RuntimeError()")
            with self.assertRaises(ValueError):
                r.audit_attempt(a, w, c, p, m)

    def test_pair_start_allows_different_first_actions_and_checks_stock_edge(self):
        row = dict(episode_id="e", target_sector=10, seed=1, origin_sha256="origin", target_position=[1,2,3],
                   initial_observation_sha256="first", initial_quantized=[0]*5)
        arms = {"a":[row], "b":[dict(row, initial_quantized=[1]*5)]}
        edges = {10:[1,"origin",[1,2,3]]}
        r.match_starts(arms, ["e"], edges)
        with self.assertRaises(ValueError):
            r.match_starts(arms, ["e"], {10:[2,"origin",[1,2,3]]})
        arms["b"][0]["initial_observation_sha256"] = "different"
        with self.assertRaises(ValueError):
            r.match_starts(arms, ["e"], edges)

    def test_missing_exit_witness_and_forged_clean_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, w, c, p, m, s = self.fixture(Path(tmp))
            old = w/"process.json"
            old.unlink()
            result = r.audit_attempt(a, w, c, p, m)
            self.assertEqual((result["status"], result["process"], result["row"]), ("censored", None, None))
            s["error"] = dict(type="ValueError", message="invented failure")
            r.write(old, s)
            with self.assertRaisesRegex(ValueError, "unexplained error"):
                r.audit_attempt(a, w, c, p, m)

    def test_model_launcher_keeps_real_exit_three_and_reaped_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            a, _, c, policy, model, _ = self.fixture(base)
            work = base/"launcher"
            work.mkdir()
            r.write(work/"assignment.json", a)
            engine = base/"engine"
            engine.write_text("#!/bin/sh\nprintf 'INDEPENDENT_ERROR synthetic_exchange\\n'\nexit 3\n")
            engine.chmod(0o700)
            r.execute(a, work, c, engine, base/"no-map-needed", policy, model)
            status = r.read(work/"process.json")
            self.assertEqual(status["engine_returncode"], 3)
            self.assertIs(type(status["worker_returncode"]), int)
            self.assertEqual(status["error"], dict(type="ValueError",message="synthetic_exchange"))
            outcome = r.audit_attempt(a, work, c, policy, model)
            self.assertEqual(outcome["status"], "censored")
            self.assertIsNone(outcome["row"])

    def test_late_worker_retains_engine_terminal_with_short_or_torn_journal(self):
        with tempfile.TemporaryDirectory() as tmp:
            a,w,c,p,m,s = self.fixture(Path(tmp))
            args = (a,w,c,p,m)
            s.update(worker_returncode=7,error={"type":"ValueError","message":"worker_failed"})
            (w/"process.json").write_text(json.dumps(s))
            # Three actual engine control ticks; the independent journal can lose
            # zero, some or all records that were still buffered when the worker died.
            frames = list(map(json.loads,(w/"motor.jsonl").read_bytes().splitlines()))
            start, control, end = map(json.loads,(w/"native.jsonl").read_bytes().splitlines())
            journal, motor, native = [],[],[start]
            for tick,step in enumerate((0,6,12)):
                obs = dict(frames[0],tick=tick,step=step)
                motor.extend([obs,dict(frames[1],tick=tick,step=step,source_tick=tick)])
                native.append(dict(control,tick=tick,step=step))
                journal.append((json.dumps(dict(tick=tick,observation_sha256=r.prior.sha((json.dumps(obs)+"\n").encode()),
                                                quantized=[0]*5))+"\n").encode())
            native.append(dict(end,ticks=3,step=13))
            from test_lily_recovery_evaluation import write_rows
            write_rows(w/"native.jsonl",native)
            write_rows(w/"motor.jsonl",motor)
            for recorded, count in ((b"".join(journal),3),(journal[0],1),(b"",0),(journal[0]+journal[1][:8],1)):
                with self.subTest(count=count,length=len(recorded)):
                    (w/"decisions.jsonl").write_bytes(recorded)
                    evidence = r.audit_attempt(*args)
                    self.assertEqual((evidence["status"],evidence["row"],evidence["reinferred_decisions"]),
                                     ("censored",None,count))
                    self.assertEqual(evidence["observed_native_terminal"]["ticks"],3)
            (w/"decisions.jsonl").write_bytes(b"")
            native[2]["axes"]=[1,0,0,0]
            write_rows(w/"native.jsonl",native)
            with self.assertRaises(ValueError):
                r.audit_attempt(*args)

    def test_worker_death_does_not_mask_corrupt_terminal_or_engine_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            a,w,c,p,m,s = self.fixture(Path(tmp))
            s.update(worker_returncode=7,error={"type":"ValueError","message":"worker_failed"})
            (w/"process.json").write_text(json.dumps(s))
            trace = w/"native.jsonl"
            lines = trace.read_bytes().splitlines(keepends=True)
            terminal = json.loads(lines[-1])
            for changed in (dict(terminal,health=50),dict(terminal,ticks=2),dict(terminal,step=8)):
                with self.subTest(changed=changed):
                    trace.write_bytes(b"".join(lines[:-1])+(json.dumps(changed)+"\n").encode())
                    with self.assertRaises(ValueError):
                        r.audit_attempt(a,w,c,p,m)
            trace.write_bytes(b"".join(lines[:-1])+b'{"event":"ter')
            self.assertIsNone(r.audit_attempt(a,w,c,p,m)["observed_native_terminal"])
            trace.write_bytes(b"".join(lines))
            (w/"engine.log").write_bytes(b"STOCK FULL TICK landed=1\n")
            with self.assertRaisesRegex(ValueError, "censored engine marker"):
                r.audit_attempt(a,w,c,p,m)

import json
import os
from pathlib import Path
import tempfile
import time
import unittest

from bots.lily.memory import ExperienceStore
from bots.lily.runtime import Supervisor


def policy(turn=1, extra=""):
    return ("ABI_VERSION=1\n" + extra + "\ndef decide(observation,context):\n"
            " return {'action':'motor','skill':'test','steps':[{'duration_ms':200,'turn':"
            + str(turn) + "}]}\n")


def observation():
    return {"run_id": "test", "world_epoch": 1, "life_epoch": 1, "native_active": True,
            "state": {"health": 100, "shields": 20, "ammo": {}}, "lily": {
                "age_seconds": {"sense": 0, "offers": 0, "progress": 0}, "offers": None, "progress": None,
                "sense": {"sample_id": 1, "revision": 0, "action_seq": 0, "owner_sample_id": 0,
                         "owner": "baseline", "phase": "idle", "safe_handover": True,
                         "position": [0, 0, 0], "facing": [0, 1, 0], "medium": "air", "supported": True,
                         "axes": [0] * 4, "buttons": 0, "peers": []}}}


class Link:
    def __init__(self):
        self.actions = []
        self.seq = 0
        self.receipts = {}

    def __call__(self, op, body=None):
        if op == "attach":
            return {"lease_id": "only-owner", "expires_in": 30}
        if op == "renew":
            return {"expires_in": 30}
        if op.startswith("commands/"):
            return self.receipts[op.split("/", 1)[1]]
        self.seq += 1
        self.actions.append((op, body))
        receipt = dict(status="applied", action_seq=self.seq, kind=op, request_id=body["request_id"],
                       **{k: body[k] for k in ("run_id", "world_epoch", "life_epoch")})
        self.receipts[body["request_id"]] = receipt
        return receipt


class SupervisorTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.policy = Path(temp.name) / "policy.py"
        self.policy.write_text(policy())
        self.memory = ExperienceStore(Path(temp.name) / "db")
        self.addCleanup(self.memory.close)
        self.link = Link()
        self.obs = observation()
        self.log = []
        self.sup = Supervisor(self.policy, self.memory, "level", self.link, trace=self.log.append,
                              startup_timeout=1, decision_timeout=.20, stage_interval=.01)
        self.addCleanup(self.sup.close)

    def until(self, predicate, limit=3):
        end = time.monotonic() + limit
        while time.monotonic() < end:
            self.obs["lily"]["sense"]["sample_id"] += 1
            self.sup.step(self.obs)
            if predicate():
                return
            time.sleep(.007)
        self.fail(str([r["event"] for r in self.log][-18:]))

    def motors(self):
        return [body for kind, body in self.link.actions if kind == "motor"]

    def start(self):
        self.until(lambda:len(self.motors()) == 1)
        self.original = self.sup.active.digest

    def finish(self):
        sense = self.obs["lily"]["sense"]
        cmd = self.motors()[-1]
        self.obs["lily"]["progress"] = dict(action_seq=self.link.seq, revision=cmd["revision"],
            sample_id=cmd["sample_id"], owner="motor", phase="completed", reason="none", outcome="playback",
            applied_ms=202, node=-1)
        sense["sample_id"] += 1

    def bank_order(self, order_id="escape-one", *, position=None, budget=60):
        self.sup.directive_file = self.policy.with_suffix(".json")
        self.sup.directive_file.write_text(json.dumps(dict(id=order_id, goal="escape-bank", provenance="operator",
            parameters=dict(position=position or [0., 1., 0.], sector=41, budget_seconds=budget),
            run_id="test", world_epoch=1, life_epoch=1, expires_at=time.time()+30)))

    def bank_setup(self, budget=60):
        self.obs["lily"]["sense"].update(medium="water", supported=False)
        self.obs["age_seconds"] = 0.
        self.obs["state"]["game_time"] = 1.
        self.policy.write_text(
            "ABI_VERSION=1\ndef decide(o,c):\n"
            " task=c['bank_task']\n"
            " if not task or task['status']!='active': return {'action':'baseline'}\n"
            " return {'action':'motor','skill':'bank','task_id':task['task_id'],"
            "'steps':[{'duration_ms':200,'turn':1}]}\n")
        self.bank_order(budget=budget)

    def bank_outcomes(self):
        return [r for r in self.log if r["event"] == "bank_outcome"]

    def test_bank_motor_without_local_goal_records_the_committed_endpoint(self):
        self.bank_setup()
        self.start()
        self.assertEqual(self.sup.undertaking["goal"]["position"], [0., 1., 0.])

    def test_bank_motor_cannot_relabel_an_unrelated_endpoint(self):
        self.bank_setup()
        source = self.policy.read_text().replace("'steps':", "'goal':{'direction':[1,0,0],'distance':9},'steps':")
        self.policy.write_text(source)
        self.until(lambda:bool(self.bank_outcomes()) or bool(self.motors()))
        self.assertEqual(self.motors(), [])
        self.assertEqual(self.bank_outcomes()[0]["reason"], "bank_goal_mismatch")
        self.assertIsNone(self.sup.lease)

    def test_already_at_bank_endpoint_does_not_award_a_displacement_win(self):
        self.bank_setup()
        self.obs["lily"]["sense"]["position"] = [0., 1., 0.]
        self.start()
        u = self.sup.undertaking
        self.obs["lily"]["sense"].update(owner="motor", phase="running", revision=u["revision"],
            action_seq=u["action_seq"], owner_sample_id=u["sample_id"], safe_handover=False)
        self.until(lambda:self.sup.undertaking["max_projection"] == 0.)
        self.finish()
        self.until(lambda:any(row["event"] == "outcome" for row in self.log))
        outcome, = [row for row in self.log if row["event"] == "outcome"]
        self.assertEqual(outcome["status"], "playback")
        self.assertIsNone(outcome["physical_success"])

    def restart_pending_bank(self, *, final_status="applied", changed_seq=False):
        self.bank_setup()
        def pending(op, body=None):
            response = self.link(op, body)
            if op == "motor":
                response["status"] = "pending"
            return response
        self.sup.call = pending
        self.start()
        original = dict(self.sup.undertaking)
        self.assertIsNone(self.memory.db.execute("SELECT episode FROM bank_children").fetchone())
        old = self.sup
        old.retire(old.active)
        old.active = None
        old.bank = old.undertaking = old.lease = None
        old.close()
        receipt = self.link.receipts[original["request_id"]]
        receipt["status"] = final_status
        if changed_seq:
            receipt["action_seq"] += 1
        self.sup = Supervisor(self.policy, self.memory, "level", self.link, trace=self.log.append,
                              directive_file=old.directive_file)
        self.addCleanup(self.sup.close)
        self.until(lambda:self.sup.bank and self.sup.bank.outcome)
        self.assertEqual(len(self.motors()), 1)
        self.assertEqual(self.sup.bank.outcome["terminal"], "restarted")
        self.assertIsNone(self.sup.bank.outcome["physical_success"])
        outcome = json.loads(self.memory.db.execute("SELECT outcome FROM attempts WHERE episode=?",
                                                   (original["episode_id"],)).fetchone()[0])
        self.assertEqual((outcome["status"], outcome["physical_success"]), ("owner_lost", None))
        return original

    def test_restart_recovers_late_admission_without_replaying_the_child(self):
        original = self.restart_pending_bank()
        self.assertEqual(self.memory.db.execute("SELECT admitted FROM submissions WHERE request=?",
                                               (original["request_id"],)).fetchone(), (1,))
        self.assertEqual(self.memory.db.execute("SELECT episode,task_id FROM bank_children").fetchall(),
                         [(original["episode_id"], original["task_id"])])

    def test_restart_does_not_credit_a_changed_native_sequence(self):
        original = self.restart_pending_bank(changed_seq=True)
        self.assertEqual(self.memory.db.execute("SELECT admitted FROM submissions WHERE request=?",
                                               (original["request_id"],)).fetchone(), (0,))
        self.assertEqual(self.memory.db.execute("SELECT episode FROM bank_children").fetchall(), [])

    def test_restart_does_not_credit_a_still_pending_child(self):
        original = self.restart_pending_bank(final_status="pending")
        self.assertEqual(self.memory.db.execute("SELECT admitted FROM submissions WHERE request=?",
                                               (original["request_id"],)).fetchone(), (0,))
        self.assertEqual(self.memory.db.execute("SELECT episode FROM bank_children").fetchall(), [])

    def test_bank_commits_across_chunks_then_activates_replacement(self):
        self.bank_setup(budget=5)
        self.start()
        self.obs["state"]["game_time"] = 1.125  # First clock published after assignment.
        self.obs["lily"]["sense"]["sample_id"] += 1
        self.sup.step(self.obs)
        task_id = self.sup.bank.record["task_id"]
        source = self.policy.read_text()
        self.policy.write_text(source.replace("'turn':1", "'turn':0"))
        self.until(lambda:self.sup.candidate_ready)
        self.bank_order(position=[3,2,1], budget=55)
        self.finish()
        self.until(lambda:len(self.motors()) == 2)
        self.assertEqual(self.sup.active.digest, self.original)
        self.assertEqual(self.sup.bank.context(), dict(task_id=task_id, status="active", sector=41,
                                                        position=[0., 1., 0.], budget_seconds=5))
        self.assertTrue(all("task_id" not in body for body in self.motors()))
        self.assertEqual(self.memory.db.execute("SELECT task_id FROM bank_children").fetchall(),
                         [(task_id,), (task_id,)])
        self.obs["state"]["game_time"] = 6.125
        self.until(lambda:self.sup.active.digest != self.original)
        outcome, = self.bank_outcomes()
        self.assertEqual((outcome["terminal"], outcome["physical_success"], outcome["controller_success"]),
                         ("budget_elapsed", None, None))
        self.assertIsNone(self.sup.lease)
        self.assertEqual(len(self.motors()), 2)
        self.bank_order("new-at-same-destination", budget=5)
        self.until(lambda:len(self.motors()) == 3)
        self.assertNotEqual(task_id, self.sup.bank.record["task_id"])

    def test_bank_reject_never_links_and_worker_fault_releases(self):
        self.bank_setup()
        def reject(op, body=None):
            receipt = self.link(op, body)
            if op == "motor":
                receipt["status"] = "rejected"
            return receipt
        self.sup.call = reject
        self.start()
        self.assertIsNone(self.memory.db.execute("SELECT episode FROM bank_children").fetchone())
        self.sup.active.process.kill()
        self.until(lambda:bool(self.bank_outcomes()))
        self.assertIsNone(self.sup.lease)
        outcome, = self.bank_outcomes()
        self.assertEqual(outcome["terminal"], "control_lost")
        self.assertIsNone(outcome["physical_success"])

    def test_bank_restart_censors_open_record_once_without_replaying_order(self):
        self.bank_setup()
        self.start()
        old = self.sup
        # Simulate abrupt worker/process loss, bypassing graceful supervisor.close().
        old.retire(old.active)
        old.active = None
        old.bank = old.undertaking = old.lease = None
        old.close()
        self.sup = Supervisor(self.policy, self.memory, "level", self.link, trace=self.log.append,
                              directive_file=old.directive_file)
        self.addCleanup(self.sup.close)
        self.until(lambda:self.sup.bank and self.sup.bank.outcome)
        self.assertEqual([r["terminal"] for r in self.bank_outcomes()], ["restarted"])
        self.assertEqual(len(self.motors()), 1)
        self.bank_order(position=[3, 2, 1])
        self.until(lambda:self.sup.lease is None)
        self.assertEqual(self.sup.bank.context()["position"], [0., 1., 0.])
        self.assertEqual(len(self.motors()), 1)

    def test_live_sampled_landing_requires_supported_near_target_and_is_censored(self):
        self.bank_setup()
        self.start()
        sense = self.obs["lily"]["sense"]
        u = self.sup.undertaking
        sense.update(owner="motor", phase="running", revision=u["revision"], action_seq=u["action_seq"],
                     owner_sample_id=u["sample_id"], safe_handover=False)
        self.until(lambda:self.sup.bank.wet_takeover)
        sense.update(medium="air", supported=True, position=[0., 1., 0.])
        for age in (1.125, 1.25, 1.375, 1.5):
            self.obs["state"]["game_time"] = age
            sense["sample_id"] += 1
            self.sup.step(self.obs)
        row, = self.bank_outcomes()
        self.assertEqual((row["terminal"],row["physical_success"],row["attribution"]), ("sampled_dry",None,"unknown"))
        self.assertTrue(row["observed_wet_takeover"])
        self.assertIsNone(self.sup.lease)
        # Removing and re-adding the same ID in this life still leaves the task closed.
        self.sup.directive_file.unlink()
        self.sup.step(self.obs)
        self.bank_order()
        sense.update(medium="water", safe_handover=True, phase="idle", owner="baseline")
        self.until(lambda:self.sup.bank and self.sup.bank.outcome)
        self.assertEqual(len(self.motors()), 1)

    def test_replacing_bank_directive_preempts_and_fence_censors_exactly_once(self):
        self.bank_setup()
        self.start()
        self.bank_order("second")
        self.until(lambda:len(self.motors()) == 2)
        self.assertEqual([r["terminal"] for r in self.bank_outcomes()], ["directive_ended"])
        self.obs["life_epoch"] += 1
        self.obs["native_active"] = False
        self.sup.step(self.obs)
        self.assertEqual([(r["life_epoch"], r["terminal"],r["physical_success"]) for r in self.bank_outcomes()],
                         [(1,"directive_ended",None),(1,"fence_changed",None)])

    def test_unrelated_or_dry_policy_cannot_submit_a_bank_motor(self):
        self.bank_setup()
        self.policy.write_text(policy())
        self.until(lambda:bool(self.bank_outcomes()))
        self.assertEqual((self.bank_outcomes()[0]["terminal"], len(self.motors())), ("unavailable", 0))
        self.obs["lily"]["sense"]["medium"] = "air"
        self.bank_order("dry")
        self.until(lambda:len(self.bank_outcomes()) == 2)
        self.assertEqual(self.bank_outcomes()[-1]["reason"], "requires_wet_start")
        self.assertIsNone(self.sup.lease)

    def test_equal_length_hot_swap_at_physical_boundary(self):
        self.start()
        stat = self.policy.stat()
        self.policy.write_text(policy(0))
        os.utime(self.policy, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        self.until(lambda:any(r["event"] == "candidate_ready" and r["policy_hash"] != self.original for r in self.log))
        self.assertEqual(self.original, self.sup.active.digest)
        self.obs["lily"]["sense"]["safe_handover"] = False
        self.finish()
        self.until(lambda:any(r["event"] == "outcome" for r in self.log))
        self.assertEqual(self.original, self.sup.active.digest)
        self.obs["lily"]["sense"]["safe_handover"] = True
        self.until(lambda:len(self.motors()) == 2)
        self.assertEqual(self.motors()[-1]["steps"][0]["turn"], 0)
        self.assertNotEqual(self.original, self.sup.active.digest)

    def test_bad_candidate_keeps_live_controller(self):
        self.start()
        for source in (policy(extra="import time; time.sleep(20)"),
                       "ABI_VERSION=1\ndef decide(o,c):\n while True: pass",
                       "ABI_VERSION=1\ndef decide(o,c): return {'action':'wait','state':{'x':float('nan')}}",
                       "ABI_VERSION=1\ndef decide(o,c): return {'action':'motor','skill':'x','steps':[]}",
                       "raise RuntimeError('unusable')"):
            count = sum(r["event"] == "rejected" for r in self.log)
            self.policy.write_text(source)
            self.until(lambda:sum(r["event"] == "rejected" for r in self.log) > count)
            self.assertEqual(self.original, self.sup.active.digest)
            self.finish()
            n = len(self.motors())
            self.until(lambda:len(self.motors()) > n)
        self.assertTrue(all(x["steps"][0]["turn"] == 1 for x in self.motors()))

    def test_worker_death_and_stale_fence(self):
        self.start()
        self.sup.active.process.kill()
        self.until(lambda:any(r["event"] == "fallback" for r in self.log))
        self.assertTrue(any(k == "release" for k, _ in self.link.actions))
        self.assertIsNone(next(r["physical_success"] for r in self.log if r["event"] == "outcome"))
        self.obs["life_epoch"] = 2
        self.obs["native_active"] = False
        self.until(lambda:self.sup.undertaking is None)
        self.assertEqual(len(self.motors()), 1)

    def test_active_keeps_playing_during_hung_import(self):
        self.start()
        self.policy.write_text(policy(extra="import time; time.sleep(30)"))
        self.until(lambda:self.sup.candidate is not None)
        self.finish()
        self.until(lambda:len(self.motors()) == 2)
        self.assertTrue(self.sup.candidate and self.sup.candidate.process.poll() is None)
        self.assertEqual(self.sup.active.digest, self.original)

    def test_roll_back_to_known_good_after_active_crash(self):
        self.start()
        self.policy.write_text(policy(0))
        self.until(lambda:self.sup.candidate_ready)
        self.finish()
        self.until(lambda:len(self.motors()) == 2)
        self.sup.active.process.kill()
        self.until(lambda:any(r["event"] == "fallback" for r in self.log))
        self.obs["lily"]["sense"]["sample_id"] += 1
        self.until(lambda:len(self.motors()) == 3)
        self.assertEqual(self.original, self.sup.active.digest)
        self.assertEqual(self.motors()[-1]["steps"][0]["turn"], 1)

    def test_directive_renewal_preserves_action_fence_change_censors(self):
        import json
        directive = dict(id="order-one", goal="motor", provenance="operator", parameters={"skill": "sidestep"},
                       run_id="test", world_epoch=1, life_epoch=1, expires_at=time.time() + 20)
        self.sup.directive_file = self.policy.with_suffix(".json")
        self.sup.directive_file.write_text(json.dumps(directive))
        self.start()
        episode = self.sup.undertaking["episode_id"]
        directive["expires_at"] += 40
        self.sup.directive_file.write_text(json.dumps(directive))
        self.sup.step(self.obs)
        self.assertEqual(episode, self.sup.undertaking["episode_id"])
        self.assertEqual(1, len(self.motors()))
        self.obs["life_epoch"] += 1
        self.obs["native_active"] = False
        self.sup.step(self.obs)
        self.assertIsNone(self.sup.directive)
        self.assertIsNone(self.sup.undertaking)
        terminal = next(r for r in self.log if r["event"] == "outcome")
        self.assertIsNone(terminal["physical_success"])
        self.assertEqual((terminal["life_epoch"], terminal["status"]), (1, "fence_changed"))

    def test_only_matching_applied_pose_displacement_counts(self):
        source = policy().replace("'skill':'test'", "'skill':'test','goal':{'distance':.1,'direction':[1,0,0]}")
        self.policy.write_text(source)
        self.start()
        sense = self.obs["lily"]["sense"]
        cmd = self.motors()[0]
        sense.update(sample_id=2, action_seq=99, revision=cmd["revision"], owner_sample_id=cmd["sample_id"],
                     owner="motor", phase="running", safe_handover=False, position=[10, 0, 0])
        self.sup.step(self.obs)
        sense.update(sample_id=3, action_seq=1, position=[20, 0, 0])
        self.sup.step(self.obs)
        self.assertEqual(self.sup.undertaking["max_projection"], 0)
        row = next(r for r in reversed(self.log) if r["event"] == "observation")
        self.assertEqual(row["goal"]["position"], [.1, 0., 0.])
        self.assertAlmostEqual(row["goal"]["distance"], 19.9)
        self.assertEqual(row["goal"]["direction"], [-1., 0., 0.])
        sense.update(sample_id=4, position=[20.3, 0, 0])
        self.sup.step(self.obs)
        self.finish()
        terminal = self.obs["lily"]["progress"]
        self.obs["lily"]["terminals"] = [terminal]
        self.obs["lily"]["progress"] = dict(terminal, action_seq=99, phase="running", outcome="none")
        self.sup.step(self.obs)
        self.sup.step(self.obs)
        outcomes = [r for r in self.log if r["event"] == "outcome"]
        self.assertEqual([(r["physical_success"], r["status"]) for r in outcomes], [(True, "motor_goal_reached")])
        self.assertEqual(1, self.memory.estimate(next(r["key"] for r in self.log if r["event"] == "attempt"))["wins"])

    def stateful_policy(self):
        self.policy.write_text(policy().replace("'skill':'test'", "'state':{'advanced':True},'skill':'test'"))

    def test_post_lost_reply_reconciles_exact_durable_identity(self):
        self.stateful_policy()
        def dropped(op, body=None):
            if op == "motor":
                journal = self.memory.unresolved("test")
                self.assertEqual([r["request_id"] for r in journal], [body["request_id"]])
                self.assertEqual(journal[0]["command"]["steps"], body["steps"])
                self.assertNotIn("lease_id", str(journal))
                self.link(op, body)
                raise OSError("reply lost")
            return self.link(op, body)
        self.sup.call = dropped
        self.until(lambda:self.sup.undertaking is not None)
        self.assertEqual(len(self.motors()), 1)
        self.assertEqual(self.sup.state, {"advanced": True})

    def test_rejected_receipt_never_advances_policy_state(self):
        self.stateful_policy()
        def rejected(op, body=None):
            receipt = self.link(op, body)
            if op == "motor":
                receipt["status"] = "rejected"
            return receipt
        self.sup.call = rejected
        self.until(lambda:any(r["event"] == "outcome" for r in self.log))
        self.assertEqual(self.sup.state, {})
        key = next(r["key"] for r in self.log if r["event"] == "attempt")
        self.assertEqual(self.memory.estimate(key)["attempts"], 0)

    def test_pending_then_rejected_does_not_install_decision_state(self):
        self.stateful_policy()
        def pending(op, body=None):
            response = self.link(op, body)
            if op == "motor":
                response["status"] = "pending"
            elif op.startswith("commands/"):
                response["status"] = "stale"
            return response
        self.sup.call = pending
        self.until(lambda:self.sup.undertaking is not None)
        self.assertEqual(self.sup.state, {})
        self.until(lambda:any(r["event"] == "outcome" for r in self.log))
        self.assertEqual(self.sup.state, {})

    def test_expiration_during_attach_blocks_dispatch_and_same_id_can_change(self):
        import json
        from unittest.mock import patch
        path = self.policy.with_suffix(".json")
        self.sup.directive_file = path
        clock = [time.time()]
        order = dict(id="A", provenance="operator", goal="motor", parameters={"skill": "sidestep"},
                     run_id="test", world_epoch=1, life_epoch=1, expires_at=clock[0] + 1)
        path.write_text(json.dumps(order))

        def attach(op, body=None):
            if op == "attach":
                clock[0] += 2
                order.update(parameters={"skill": "forward-probe"}, expires_at=clock[0] + 60)
                path.write_text(json.dumps(order))
            return self.link(op, body)

        self.sup.call = attach
        with patch("bots.lily.runtime.time.time", side_effect=lambda:clock[0]):
            self.until(lambda:self.sup.lease is not None)
        self.assertFalse(self.motors())
        self.assertEqual(self.sup.directive["parameters"], {"skill": "forward-probe"})

    def test_directive_expires_while_committing_journal(self):
        import json
        from unittest.mock import patch
        clock = [time.time()]
        path = self.policy.with_suffix(".json")
        self.sup.directive_file = path
        order = dict(id="A", provenance="operator", goal="motor", parameters={},
                     run_id="test", world_epoch=1, life_epoch=1, expires_at=clock[0] + 1)
        path.write_text(json.dumps(order))
        prepare = self.memory.prepare
        def delayed(intent):
            prepare(intent)
            clock[0] += 2
        with patch("bots.lily.runtime.time.time", side_effect=lambda:clock[0]), patch.object(
                self.memory, "prepare", side_effect=delayed):
            self.until(lambda:any(r["event"] == "submission" for r in self.log))
        self.assertFalse(self.motors())
        self.assertIsNone(self.sup.directive)
        self.assertEqual(self.memory.db.execute("SELECT disposition FROM submissions").fetchone(), ("not_sent",))

    def test_slow_attach_invalidates_source_sample(self):
        def slow(op, body=None):
            if op == "attach":
                time.sleep(1.)
            return self.link(op, body)
        self.sup.call = slow
        self.until(lambda:self.sup.lease is not None)
        self.assertFalse(self.motors())

    def test_crash_after_accept_recovers_without_reissuing_original_identity(self):
        from unittest.mock import patch
        class AbruptExit(BaseException):
            pass
        with patch.object(self.memory, "bind", side_effect=AbruptExit):
            with self.assertRaises(AbruptExit):
                self.until(lambda:bool(self.motors()))
        original = self.motors()[0]["request_id"]
        self.assertEqual(self.memory.unresolved("test")[0]["request_id"], original)
        self.sup.close()
        reopened = ExperienceStore(self.policy.parent / "db")
        self.addCleanup(reopened.close)
        self.sup = Supervisor(self.policy, reopened, "level", self.link, trace=self.log.append)
        self.addCleanup(self.sup.close)
        self.until(lambda:any(r["event"] == "recovered_attempt" for r in self.log))
        self.assertEqual(sum(a["request_id"] == original for a in self.motors()), 1)
        self.assertEqual(reopened.unresolved("test"), [])
        receipt = next(r for r in self.log if r["event"] == "submission_reconciled")
        self.assertEqual((receipt["request_id"], receipt["episode_id"], receipt["status"]),
                         (original, "test/1/1/1", "applied"))

    def test_unmatched_receipt_stays_censored_and_new_lease_uses_global_floor(self):
        self.stateful_policy()
        ids = []
        def unknown(op, body=None):
            if op == "attach":
                return {"lease_id": "active", "expires_in": 30, "lily_request_floor": "9500000000000000000"}
            if op == "motor":
                ids.append(body["request_id"])
                raise OSError("ambiguous dispatch")
            if op.startswith("commands/"):
                return dict(status="applied", action_seq=1, kind="motor", request_id=op[9:],
                            run_id="test", world_epoch=9, life_epoch=7)
            return self.link(op, body)
        self.sup.call = unknown
        self.until(lambda:bool(ids))
        self.assertEqual(ids, ["lily.9500000000000000001"])
        self.assertEqual(self.sup.state, {})
        self.assertFalse(any(r["event"] == "attempt" for r in self.log))
        self.assertEqual([r["request_id"] for r in self.memory.unresolved("test")], ids)
        self.until(lambda:len(ids) == 2)
        row = self.memory.db.execute("SELECT disposition,episode FROM submissions WHERE request=?", (ids[0],)).fetchone()
        self.assertEqual(row, ("censored_unresolved", None))
        self.assertEqual(self.sup.state, {})

    def test_ack_unconfirmed_does_not_end_physical_action(self):
        def ambiguous(op, body=None):
            receipt = self.link(op, body)
            if op == "motor" or op.startswith("commands/"):
                receipt["status"] = "unconfirmed"
            return receipt
        self.sup.call = ambiguous
        self.start()
        self.assertIsNotNone(self.sup.undertaking)
        self.finish()
        self.until(lambda:any(r["event"] == "outcome" for r in self.log))
        self.assertEqual(next(r["status"] for r in self.log if r["event"] == "outcome"), "playback")


class LocalCompanionTest(unittest.TestCase):
    def test_fenced_native_receipt_and_persistent_policy_choice_across_runs(self):
        """Real HTTP auth, codec, pipes and sqlite. Native progress is a synthetic fixture."""
        import json
        import struct
        from bots import companion
        from bots.companion_cli import call
        from bots.lily import protocol
        from bots.lily.policies import adaptive

        def run(tmp, tag, nodes, learn):
            directory = tmp / tag
            directory.mkdir()
            hub = companion.Hub(directory, ["lily"], 0, experimental_ids=["lily"])
            sock = hub.take_socket("lily")
            credential = json.loads((hub.directory / "lily.json").read_text())
            db = ExperienceStore(tmp / "persistent.db")
            log = []
            supervisor = Supervisor(Path(adaptive.__file__), db, "one-level", lambda r, b=None:call(credential, r, b),
                                    trace=log.append)

            def feed(kind, seq, payload):
                sock.send(companion.frame(kind, 1, 1, seq, payload))
                hub.pump()

            def sense(sid, safe):
                return protocol.SENSE_HEADER.pack(sid, 0, 0, 0, -1, 0, 0, safe, 1, 0,
                    0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 16, 0, 0, 0, 0, 0, 0, 0, 0)

            try:
                stock = bytearray(144)
                struct.pack_into("<4I", stock, 0, 1, 42, 14, 88)
                struct.pack_into("<iII", stock, 60, -1, 4, 0xffffffff)
                feed(companion.STATE, 1, stock)
                feed(protocol.SENSE, 2, sense(73, 1))
                offers = protocol.OFFERS_HEADER.pack(73, 12, 2)
                for idx, node in enumerate(nodes):
                    offers += protocol.CHOICE.pack(node, 3, 0, 0, 1 + 3 * idx, 2, 0, 1, 1 + .1 * idx)
                feed(protocol.OFFERS, 3, offers)
                end = time.monotonic() + 2.
                packet = None
                while time.monotonic() < end:
                    supervisor.step(call(credential, "observation"))
                    hub.pump()
                    try:
                        packet = sock.recv(513)
                        break
                    except BlockingIOError:
                        time.sleep(.005)
                self.assertIsNotNone(packet)
                _, _, kind, _, _, _, seq = companion.HEADER.unpack_from(packet)
                self.assertEqual(kind, protocol.COMMIT)
                _, sample, revision, offer, node = protocol.COMMIT_HEADER.unpack_from(packet, companion.HEADER.size)
                self.assertEqual((sample, offer), (73, 12))
                if learn:
                    feed(companion.ACK, seq, struct.pack("<BBH", 0, kind, 0))
                    feed(protocol.SENSE, 4, sense(74, 0))
                    progress = protocol.ACTION.pack(seq, revision, sample, 1, 6, 5, 0, 410, node)
                    feed(protocol.PROGRESS, 5, progress)
                    supervisor.step(call(credential, "observation"))
                    feed(protocol.PROGRESS, 6, progress)
                    supervisor.step(call(credential, "observation"))
                    self.assertEqual([row["physical_success"] for row in log if row["event"] == "outcome"], [False])
                return node
            finally:
                supervisor.close()
                db.close()
                sock.close()
                hub.close()
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(run(Path(tmp), "first", (10, 20), True), 20)
            self.assertEqual(run(Path(tmp), "second", (123, 234), False), 123)

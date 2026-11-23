import csv
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1] / "native/tests/stock_water_replay"
sys.path.insert(0, str(HERE))
import collect_recovery as recovery


class RecoveryEvidenceTests(unittest.TestCase):
    def test_passive_water_interval_uses_post_advance_clock(self):
        observations = [
            {"sense":{"medium":medium, "breath_used_ms":debt}, "state":{"health":health}}
            for medium, debt, health in [
                ("water", 50, 20), ("air", 0, 18), ("water", 0, 19), ("water", 3, 17)]
        ]
        clock, water, health, debt = recovery.passive_state(observations, .125)
        self.assertEqual((clock, water, health, debt), (80.5, 80.375, 17, True))

    def test_continuous_held_buttons_include_native_nonmovement_bits(self):
        applied = dict(owner="baseline", source_tick=25, buttons=17, presses=16, axes=[1,0,0,0])
        actual = dict(owner="baseline", buttons=17, axes=[1,0,0,0])
        recovery.check_controls(applied, actual, 25, "baseline", 1)
        with self.assertRaisesRegex(ValueError, "applied_input"):
            recovery.check_controls(dict(applied, presses=17), actual, 25, "baseline", 1)


def write_records(path, records):
    path.write_text("".join(json.dumps(record)+"\n" for record in records))


class TimelineTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.work, self.ref = [Path(tmp.name)/name for name in ("recovery", "reference")]
        for folder in (self.work,self.ref):
            folder.mkdir()
            (folder/"start.json").write_text('{"wet_sector":42,"wet_position":[0,0,0]}\n')
            (folder/"engine.log").write_text("BOT_NAV_READY nodes=3 directed_edges=5 name=probe\n")
            (folder/"worker.log").touch()
        self.status = dict(schema=1, engine_returncode=1, worker_returncode=0, timed_out=None, error=None)
        (self.work/"process.json").write_text(json.dumps(self.status))
        self.job = dict(episode_id="test", work_dir="recovery", controller="recovery", target_sector=10, control_dt=.04,
                        handoff_tick=1, handoff_step=6)
        self.start = dict(event="assigned", seed=7, sector=10, position=[1,0,0])
        self.end = dict(event="terminal", terminal="died", health=0, ticks=3, step=17,
                        dry_steps=0, first_breath_step=None, sector=42)
        obs, applied, controls = [], [], []
        for tick in range(3):
            owner = "model" if tick == 0 else "baseline"
            state = dict(position=[tick,0,0], velocity=[0,0,0], up=[0,0,1], facing=[1,0,0],
                         medium="water", breath_used_ms=3, supported=False, on_water_surface=False,
                         buttons=[0,1,17][tick], tick_ms=40, head_pitch=0)
            obs.append(dict(event="observation", tick=tick, step=6*tick, goal=dict(position=[1,0,0], sector=10),
                            state=dict(health=20, shields=0, mana=0), sense=state, physics_flags=0, sector=42))
            shared = dict(owner=owner, tick=tick, step=6*tick, axes=[0,0,0,0], buttons=[1,17,0][tick])
            applied.append(dict(shared, event="input", presses=[1,16,0][tick], source_tick=tick))
            controls.append(dict(shared, event="control", world_epoch=0, life_epoch=0, revision=0,
                                 sample_id=0, action_seq=0, wet=True))
        frames = [v for pair in zip(obs, applied) for v in pair]
        clock = recovery.f32(80+recovery.f32(.04))
        before = dict(progress_position=[0,0,0], stuck_at=80, water_since=60, previous_health=0, had_breath_debt=0)
        self.handoff = dict(schema=1, assigned_tick=1, reached=True, clock=clock, step=6, held_buttons=1,
                            rng=7, graph_nodes=3, graph_edges=5, pristine_planner=True,
                            goal=-1, objective=0, objective_route_node=-1, route_count=0, route_pos=0,
                            water_exit_phase=0, before=before,
                            after=dict(before, progress_position=[1,0,0], stuck_at=clock,
                                       previous_health=20, had_breath_debt=1))
        (self.work/"handoff.json").write_text(json.dumps(self.handoff))
        self.trace = frames
        self.controls = controls
        self.journal = [dict(tick=0, quantized=[0,0,0,0,1],
                             observation_sha256=hashlib.sha256((json.dumps(obs[0])+"\n").encode()).hexdigest())]
        for folder in (self.work, self.ref):
            write_records(folder/"motor.jsonl", frames)
            write_records(folder/"native.jsonl", [self.start, *controls, self.end])
            write_records(folder/"decisions.jsonl", self.journal)

    def audit(self, **changes):
        return recovery.audit_trial(dict(self.job, **changes), self.work, self.ref, 1)

    def test_physical_loss_counts_full_suffix_but_confers_no_success(self):
        row = self.audit()
        self.assertIs(row["physical_success"], False)
        self.assertEqual((row["teacher_start_tick"],row["teacher_ticks"],row["suffix_physics_steps"]), (1,2,11))
        self.assertTrue(row["ownership_complete"] and row["baseline_assisted"])

    def public_audit_fixture(self):
        # Only the matrix size/reference preparation are mocked. The public entry
        # point still verifies checkout/binary identities, status and raw timeline.
        root = self.work.parent
        self.ref = self.ref.rename(root/"test-every_tick")
        declaration = root/"declaration.json"
        decl = dict(reference_receipt_sha256="r", v2_policy_sha256="p", v2_model_sha256="m")
        declaration.write_text(json.dumps(decl))
        engine = dict.fromkeys(recovery.ENGINE_IDENTITIES, "test-engine")
        binary = root/recovery.RETAINED_EXECUTABLE
        binary.write_bytes(b"original executable bytes")
        provenance = dict(engine, fixture_source_sha256=recovery.fixture_manifest(),
                          executable_sha256=recovery.digest(binary), model_sha256="m", candidate_sha256="p")
        row = recovery.classify_trial(self.job, self.work, self.ref)
        receipt = dict(schema=1, evaluation=recovery.EVALUATION, physics_hz=recovery.HZ,
                       budget_physics_steps=recovery.MAX_STEPS, declaration_sha256=recovery.digest(declaration),
                       reference_receipt_sha256="r", complete=True, episodes=[row], summary=recovery.summary([row]),
                       provenance=provenance)
        ctx = patch.object(recovery, "assignments", return_value=([self.job], {}))
        ctx.start()
        self.addCleanup(ctx.stop)
        ctx = patch.object(recovery, "validate_reference", return_value=engine)
        ctx.start()
        self.addCleanup(ctx.stop)

        def assess():
            (root/"receipt.json").write_text(json.dumps(receipt))
            return recovery.assess_recovery(root, root, declaration)

        return receipt, binary, assess

    def test_assessor_rejects_missing_replaced_source_and_binary_identity(self):
        receipt, binary, assess = self.public_audit_fixture()
        self.assertEqual(assess(), receipt["episodes"])
        original = receipt["provenance"].copy()
        for key, forged, error in [("fixture_source_sha256", {}, "fixture_source_mismatch"),
                                   ("executable_sha256", "0"*64, "retained_executable_mismatch")]:
            for altered in [dict(original, **{key:forged}), {k:v for k,v in original.items() if k != key}]:
                with self.subTest(key=key), self.assertRaisesRegex(ValueError,error):
                    receipt["provenance"] = altered
                    assess()
        receipt["provenance"] = original
        manifest = original["fixture_source_sha256"].copy()
        manifest["native/tests/stock_water_replay/recovery.inc"] = "0"*64
        receipt["provenance"] = dict(original, fixture_source_sha256=manifest)
        with self.assertRaisesRegex(ValueError,"fixture_source_mismatch"):
            assess()
        receipt["provenance"] = original
        binary.write_bytes(b"changed executable")
        with self.assertRaisesRegex(ValueError,"retained_executable_mismatch"):
            assess()
        binary.unlink()
        with self.assertRaisesRegex(ValueError,"retained_executable_mismatch"):
            assess()

    def test_late_engine_worker_failure_keeps_terminal_and_survives_archival_audit(self):
        receipt, _, assess = self.public_audit_fixture()
        for changed, reason in [(dict(engine_returncode=-9), "engine_abnormal_exit"),
                                (dict(worker_returncode=17, error="worker_failed"), "worker_failed"),
                                (dict(worker_returncode=-9, error="TimeoutExpired", timed_out="worker"), "worker_timeout")]:
            status = dict(self.status, **changed)
            (self.work/"process.json").write_text(json.dumps(status))
            row = recovery.classify_trial(self.job, self.work, self.ref)
            self.assertIsNone(row["physical_success"])
            self.assertFalse(row["ownership_complete"])
            self.assertEqual(row["observed_native_terminal"], self.end)
            self.assertEqual(row["returncode"], status["engine_returncode"])
            self.assertEqual(row["worker_returncode"], status["worker_returncode"])
            self.assertEqual(row["reason"], reason)
            receipt.update(episodes=[row], summary=recovery.summary([row]))
            self.assertEqual(assess(), [row])

    def test_archival_audit_rejects_clean_physical_result_relabeled_censored(self):
        receipt, _, assess = self.public_audit_fixture()
        fake = recovery.censored(self.job, "worker_failed", self.work, self.status)
        receipt.update(episodes=[fake], summary=recovery.summary([fake]))
        with self.assertRaisesRegex(ValueError,"recovery_receipt_disagrees_with_evidence"):
            assess()

    def test_forged_handoff_and_passive_state(self):
        for override in (dict(step=7), dict(held_buttons=0), dict(reached=False), dict(rng=8),
                         dict(graph_edges=4), dict(pristine_planner=False), dict(objective_route_node=0),
                         dict(after=dict(self.handoff["after"], had_breath_debt=0))):
            with self.subTest(override=override), self.assertRaises(ValueError):
                (self.work/"handoff.json").write_text(json.dumps(dict(self.handoff, **override)))
                self.audit()

    def test_changed_prefix_control_or_boundary_observation(self):
        for index in (0, 1, 2):
            with self.subTest(index=index), self.assertRaisesRegex(ValueError,"prefix_or_boundary"):
                frames = list(self.trace)
                frames[index] = dict(frames[index], amended=True)
                write_records(self.work/"motor.jsonl", frames)
                self.audit()

    def test_post_handoff_changed_goal_and_false_rising_edge(self):
        for index, override in [(4, dict(goal={"sector":10,"position":[1,1,0]})), (3, dict(presses=17))]:
            with self.subTest(index=index), self.assertRaises(ValueError):
                frames = list(self.trace)
                frames[index] = dict(frames[index], **override)
                write_records(self.work/"motor.jsonl", frames)
                self.audit()

    def test_extra_decision_and_moved_handoff(self):
        with self.assertRaises(ValueError):
            self.audit(handoff_tick=2, handoff_step=12)
        write_records(self.work/"decisions.jsonl", self.journal*2)
        with self.assertRaisesRegex(ValueError,"incomplete_timeline"):
            self.audit()

    def test_early_terminal_exactly_matches_model_reference(self):
        (self.work/"handoff.json").write_text(json.dumps(dict(schema=1, assigned_tick=1, reached=False)))
        early = dict(self.end, ticks=1, step=4)
        for folder in (self.work,self.ref):
            write_records(folder/"motor.jsonl", self.trace[:2])
            write_records(folder/"native.jsonl", [self.start,self.controls[0],early])
        row = self.audit()
        self.assertIsNone(row["teacher_start_tick"])
        self.assertEqual((row["model_ticks"],row["teacher_ticks"],row["suffix_physics_steps"]),(1,0,0))
        write_records(self.work/"native.jsonl", [self.start,self.controls[0],dict(early,step=5)])
        with self.assertRaisesRegex(ValueError,"early_terminal"):
            self.audit()


class AssignmentTests(unittest.TestCase):
    def setUp(self):
        self.declaration = recovery.ROOT/"qa/lily-recovery-declaration.json"

    def test_declared_assignments_are_complete_and_unique(self):
        data = recovery.read(self.declaration)
        entries = data["recovery_jobs"]
        jobs, _ = recovery.assignments(data)
        self.assertEqual(len({r["work_dir"] for r in jobs}), 8)
        for changed in (entries[:-1], entries+[entries[0]], [dict(entries[0],handoff_step=151),*entries[1:]],
                        [dict(entries[0],episode_id="pool-100-yaw0"),*entries[1:]]):
            with self.assertRaises(ValueError):
                recovery.assignments(dict(data,recovery_jobs=changed))

    def test_missing_inputs_retain_eight_censored_assignments(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/"result"
            self.assertEqual(recovery.main(["--source",tmp,"--build",tmp,"--map",tmp,"--reference",tmp,
                                            "--declaration",str(self.declaration),"--output",str(out)]), 1)
            receipt = recovery.read(out/"receipt.json")
            self.assertTrue(receipt["complete"])
            self.assertEqual(receipt["summary"], dict(assigned=8, assisted_landings=0,
                             physical_losses=0, censored=8, terminals={"unavailable":8}))
            self.assertEqual(len(receipt["episodes"]),8)
            self.assertTrue(all(r["controller"] == "recovery" and r["baseline_assisted"]
                                and r["physical_success"] is None for r in receipt["episodes"]))
            from bots.lily.train_contact_motor import training_rows
            with self.assertRaisesRegex(ValueError, "Incomplete original training"):
                training_rows(out)


NATIVE = ("LILY_TEST_SOURCE", "LILY_TEST_BUILD", "LILY_TEST_MAP")


@unittest.skipUnless(all(os.environ.get(k) for k in NATIVE), "supply stock replay source, build and owned map")
class StockHandoffTests(unittest.TestCase):
    def test_first_native_tick_keeps_model_jump_held(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe, geometry, _ = recovery.build_replay(*(Path(os.environ[k]) for k in NATIVE), root,
                                                     independent_motor=True)
            with recovery.CASES.open() as stream:
                row = next(r for r in csv.DictReader(stream, delimiter="\t") if r["case"] == "pool-90")
            original = recovery.make_jobs([row], ["every_tick"], True)[0]
            ref = root/"original"
            recovery.execute_trial(original, row, exe, geometry, ref, recovery.POLICY, recovery.MODEL)
            work = root/"synthetic-k1"
            job = dict(original, controller="recovery", handoff_tick=1, handoff_step=6)
            code = recovery.execute_trial(job, row, exe, geometry, work, recovery.POLICY, recovery.MODEL,
                                          recovery_tick=1)
            result = recovery.audit_trial(job, work, ref, code)
            self.assertEqual(result["handoff"]["held_buttons"], 1)
            self.assertEqual(result["decisions"], 1)
            native_input = json.loads(recovery.lines(work/"motor.jsonl")[3])
            self.assertEqual(native_input["buttons"] & 1, 1)
            self.assertEqual(native_input["presses"] & 1, 0)
            self.assertEqual(native_input["owner"], "baseline")


if __name__ == "__main__":
    unittest.main()

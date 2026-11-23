"""The recovery refit consumes audited native corrections and the exact original corpus."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bots.lily import motor_contact, train_recovery_motor as trainer


def write_trace(path, rows):
    data = b"".join((json.dumps(row) + "\n").encode() for row in rows)
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def successful_job(root, case="pool-90", k=2, suffix=131, marker=.25):
    directory = root / f"{case}-yaw0-k{k}-recovery"
    directory.mkdir()
    frames, native = [], [{"position": [1, 0, 0]}]
    count = k + suffix
    previous = 0
    for tick in range(count):
        sense = dict(position=[int(tick == k+1), 0, 0], velocity=[0, 0, 0], facing=[1, 0, 0],
                     up=[0, 0, 1], medium="water", on_water_surface=True, head_pitch=0,
                     supported=False, buttons=previous, breath_used_ms=0, tick_ms=40)
        observation = dict(sense=sense, state=dict(health=100, shields=0, mana=200))
        mask = 17 if tick < k else 26
        axes = [marker, tick / count, 0., 0.]
        owner = "model" if tick < k else "baseline"
        applied = dict(tick=tick, buttons=mask, axes=axes, owner=owner)
        frames.extend([observation, applied])
        native.append(dict(applied))
        previous = mask
    native.append({"ticks": count})
    raw = {name: "a"*64 for name in trainer.collect_recovery.RAW_FILES}
    raw["motor.jsonl"] = write_trace(directory/"motor.jsonl", frames)
    raw["native.jsonl"] = write_trace(directory/"native.jsonl", native)
    return dict(episode_id=f"{case}-yaw0", case=case, work_dir=directory.name,
                handoff_tick=k, handoff_reached=True, teacher_start_tick=k, control_ticks=count,
                model_ticks=k, teacher_ticks=suffix, ownership_complete=True, baseline_assisted=True,
                terminal="supported_dry", physical_success=True, raw_sha256=raw)


class RecoveryMotorTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def test_cap_precedes_goal_filter_and_first_teacher_observes_model_jump(self):
        job = successful_job(self.root)
        rows, source = trainer.correction_rows(self.root, job, 128)
        self.assertEqual(len(rows), 127)
        self.assertEqual(rows[0]["features"][-2:], [1., 1.])
        self.assertEqual(rows[1]["features"][-1], 0.)
        expected = [i for i in range(2, 130) if i != 3]
        self.assertEqual([r["target"] for r in rows],
                         [[.25, i/133, 0., 0., 0., 1.] for i in expected])
        self.assertEqual(source["excluded"], dict(model_prefix=2, failed_or_censored_suffix=0,
                                                 after_cap=3, remaining_goal=1))
        self.assertEqual(source["samples"], len(rows))

    def test_failures_and_censored_observed_landings_cannot_contribute(self):
        job = successful_job(self.root, suffix=3)
        for name in ("native.jsonl", "motor.jsonl"):
            (self.root/job["work_dir"]/name).unlink()
        failure = dict(job, terminal="died", physical_success=False)
        rows, source = trainer.correction_rows(self.root, failure, 128)
        self.assertEqual(rows, [])
        self.assertEqual(source["excluded"], dict(model_prefix=2, failed_or_censored_suffix=3,
                                                 after_cap=0, remaining_goal=0))
        censored = {k:v for k,v in job.items() if k not in ("model_ticks", "teacher_ticks", "control_ticks")}
        censored.update(terminal="unavailable", physical_success=None, ownership_complete=False,
                        handoff_reached=None, teacher_start_tick=None, reason="worker_failed",
                        observed_native_terminal={"terminal":"supported_dry", "ticks":5})
        rows, source = trainer.correction_rows(self.root, censored, 128)
        self.assertEqual(rows, [])
        self.assertIsNone(source["excluded"]["failed_or_censored_suffix"])
        self.assertIsNone(source["excluded"]["model_prefix"])
        self.assertEqual(source["reason"], "worker_failed")

    def test_landings_without_a_teacher_suffix_and_incomplete_ownership(self):
        job = successful_job(self.root, suffix=3)
        early = dict(job, control_ticks=1, handoff_reached=False, teacher_start_tick=None,
                     model_ticks=1, teacher_ticks=0)
        rows, source = trainer.correction_rows(self.root, early, 128)
        self.assertEqual(rows, [])
        self.assertEqual(source["excluded"]["model_prefix"], 1)
        for changed in (dict(ownership_complete=False), dict(baseline_assisted=False),
                        dict(teacher_start_tick=3), dict(handoff_reached=False)):
            with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, "teacher ownership"):
                trainer.correction_rows(self.root, dict(job, **changed), 128)

    def test_change_anywhere_in_either_trace_including_after_cap_fails(self):
        job = successful_job(self.root)
        for filename in ("motor.jsonl", "native.jsonl"):
            path = self.root / job["work_dir"] / filename
            original = path.read_bytes()
            path.write_bytes(original + b" ")
            with self.subTest(filename=filename), self.assertRaisesRegex(ValueError, "digest"):
                trainer.correction_rows(self.root, job, 128)
            path.write_bytes(original)

    def test_original_split_source_identities_and_order_are_bound(self):
        declaration = json.loads(trainer.DECLARATION.read_bytes())
        frozen = json.loads(trainer.collect_recovery.MODEL.read_bytes())["provenance"]
        source = {k:copy.deepcopy(frozen[k]) for k in trainer.ORIGINAL_FIELDS}
        source["source_receipt_file_sha256"] = declaration["reference_receipt_sha256"]
        rows = [{"features":[i]} for i in range(frozen["train_samples"])]
        def load(original_rows, provenance):
            with patch.object(trainer.train_contact_motor, "training_rows", return_value=(original_rows, provenance)), \
                 patch.object(trainer, "ORIGINAL_ROWS_SHA256", trainer.ordered_hash(rows)):
                return trainer.original_rows(self.root, declaration)
        actual, provenance = load(rows, source)
        self.assertEqual(actual, rows)
        self.assertEqual(provenance["source_receipt_file_sha256"], declaration["reference_receipt_sha256"])
        self.assertEqual(provenance["v2_source_receipt_file_sha256"], frozen["source_receipt_file_sha256"])
        bad = copy.deepcopy(source)
        bad["training_sources"][0]["motor_sha256"] = "f"*64
        for changed_rows, changed_source in ((list(reversed(rows)), source), (rows, bad),
                (rows, dict(source, source_receipt_file_sha256="0"*64)),
                (rows, dict(source, train_split_groups=source["train_split_groups"] + ["pool-100"]))):
            with self.subTest(source=changed_source.keys()), self.assertRaises(ValueError):
                load(changed_rows, changed_source)

    def test_training_order_full_audit_and_receipt_identity(self):
        jobs = [successful_job(self.root, "pool-90", 2, 1, .9),
                successful_job(self.root, "pool-110", 10, 1, .5),
                successful_job(self.root, "pool-110", 2, 1, .1)]
        receipt = self.root / "receipt.json"
        receipt.write_text("{}")
        original = [{"features":[5], "target":[5]}, {"features":[1], "target":[1]}]
        audit_args = (self.root, self.root, trainer.DECLARATION)
        with patch.object(trainer, "original_rows", return_value=(original, {"train_split_groups":["pool-90", "pool-110"]})), \
             patch.object(trainer.collect_recovery, "assess_recovery", return_value=jobs) as audit:
            rows, provenance = trainer.training_rows(*audit_args)
            self.assertEqual(rows[:2], original)
            self.assertEqual([r["target"][0] for r in rows[2:]], [.1,.5,.9])
            self.assertEqual(provenance["ordered_rows_sha256"], trainer.ordered_hash(rows))
            self.assertEqual(provenance["collection_receipt_sha256"], hashlib.sha256(b"{}").hexdigest())
            self.assertEqual([s["samples"] for s in provenance["correction_sources"]], [1,1,1])
            audit.assert_called_once_with(*audit_args)
            audit.return_value = [dict(jobs[0], case="pool-100")]
            with self.assertRaisesRegex(ValueError, "training split"):
                trainer.training_rows(*audit_args)
            audit.side_effect = ValueError("changed receipt")
            with patch.object(trainer, "correction_rows") as extract, self.assertRaisesRegex(ValueError, "receipt"):
                trainer.training_rows(*audit_args)
            extract.assert_not_called()
            def change_receipt(*_):
                receipt.write_text("[]")
                return jobs
            audit.side_effect = change_receipt
            with self.assertRaisesRegex(ValueError, "receipt"):
                trainer.training_rows(*audit_args)

    def test_refuses_changed_declaration_before_audit(self):
        altered = self.root / "declaration.json"
        data = json.loads(trainer.DECLARATION.read_bytes())
        data["training_contract"]["epochs"] = 2
        altered.write_text(json.dumps(data))
        with patch.object(trainer.collect_recovery, "assess_recovery") as audit, self.assertRaisesRegex(ValueError, "declaration"):
            trainer.training_rows(self.root, self.root, altered)
        audit.assert_not_called()

    def test_no_fit_without_corrections_or_over_existing_output(self):
        with patch.object(trainer, "training_rows", return_value=([{}], {"correction_samples":0})), \
             patch.object(trainer, "fit_weights") as optimizer, self.assertRaisesRegex(ValueError, "correction"):
            trainer.fit(self.root, self.root, trainer.DECLARATION)
        optimizer.assert_not_called()
        existing = self.root / "model.json"
        existing.write_bytes(b"keep")
        with patch.object(trainer, "fit") as fit, self.assertRaises(SystemExit):
            trainer.main([str(self.root), str(self.root), str(trainer.DECLARATION), "--output", str(existing)])
        fit.assert_not_called()
        self.assertEqual(existing.read_bytes(), b"keep")

    @unittest.skipUnless(importlib.util.find_spec("numpy"), "optional training dependency")
    def test_fixed_optimizer_and_standalone_export(self):
        frozen = json.loads(trainer.collect_recovery.MODEL.read_bytes())
        weights = {k:frozen[k] for k in ("normalization", "w1", "w2", "b1", "b2")}
        rows = [dict(features=[float(i)]*17, target=[float(i)]*6) for i in (0,1)]
        with patch.object(trainer, "training_rows", return_value=(rows, {"correction_samples":1})), \
             patch.object(trainer, "fit_weights", return_value=(weights, None, None)) as optimizer:
            model = trainer.fit(self.root, self.root, trainer.DECLARATION)
        optimizer.assert_called_once()
        (x, y, hx), settings = optimizer.call_args
        self.assertEqual((x.shape, y.shape, hx.shape), ((2,17), (2,6), (0,17)))
        self.assertEqual(x.tolist(), [r["features"] for r in rows])
        self.assertEqual(y.tolist(), [r["target"] for r in rows])
        self.assertEqual(settings, dict(epochs=200, hidden=32, seed=23, learning_rate=.01))
        self.assertEqual(model["provenance"]["batch_size"], 128)
        self.assertEqual(model["provenance"]["button_threshold"], .5)
        standalone = {}
        exec(motor_contact.policy_source(model), standalone)
        values = rows[1]["features"]
        self.assertEqual(standalone["predict"](standalone["MODEL"], values), motor_contact.predict(model, values))

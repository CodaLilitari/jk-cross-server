"""Offline evidence, attribution and paired scoring for the sealed recovery experiment."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.bot_development.analysis import audit_recovery_learning as audit


def write_rows(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def one_loss(path):
    """A complete one-tick model-owned death whose exported test policy says wait."""
    case = dict(case="pool", origin="41", wet="44", dry="10", start_sector="42", x="0", y="0",
                z="0", flags="0", health="100", endurance_ms="12000", pitch="0", vertical_speed="0",
                control_dt=".040", yaw_offsets="0")
    job, = audit.motor.make_jobs([case], ["every_tick"], False)
    sense = dict(position=[0, 0, 0], velocity=[0, 0, 0], facing=[1, 0, 0], up=[0, 0, 1],
                 tick_ms=40, buttons=0, breath_used_ms=12000, head_pitch=0, medium="water",
                 on_water_surface=False, supported=False)
    first = dict(event="observation", tick=0, step=0, sector=42, physics_flags=0, sense=sense,
                 state=dict(health=100, shields=0, mana=100), goal=dict(position=[1, 0, 0], sector=10))
    control = dict(owner="model", axes=[0]*4, buttons=0, tick=0, step=0)
    write_rows(path/"motor.jsonl", [first, dict(control, event="input", source_tick=0, presses=0)])
    write_rows(path/"native.jsonl", [dict(event="assigned", position=[1, 0, 0], sector=10, seed=19),
                                    dict(control, event="control", wet=True),
                                    dict(event="terminal", ticks=1, step=1, health=0, dry_steps=0,
                                         sector=42, first_breath_step=None, terminal="died")])
    write_rows(path/"start.json", [dict(wet_sector=44, wet_position=[0, 0, 0])])
    raw = (json.dumps(first)+"\n").encode()
    write_rows(path/"decisions.jsonl", [dict(tick=0, observation_sha256=audit.sha(raw), quantized=[0]*5)])
    (path/"worker.log").write_bytes(b"")
    (path/"engine.log").write_bytes(b"STOCK FULL TICK landed=0\n")
    return job, case, audit.motor.assess(job, path, 1, case)


def wait(observation, context):
    assert context["directive"]["parameters"] == {"position": [1, 0, 0], "duration_ms": 40}
    assert observation["lily"]["sense"]["buttons"] == 0
    return {"action": "wait"}


def pair_fixture():
    edge = [123, "origin", [0, 1, 2]]
    base = dict(case="pose", yaw_deg=0, initial_observation_sha256="start", seed=edge[0],
                origin_sha256=edge[1], target_sector=10, target_position=edge[2], ownership_complete=True,
                physical_success=False, initial_quantized=None)
    rows = {m: {("pose", a): dict(base) for a in audit.ARMS} for m in audit.MODELS}
    rows["v2"]["pose", "every_tick"]["initial_quantized"] = [0]*5
    rows["v3"]["pose", "every_tick"]["initial_quantized"] = [1]*5
    raw = {f: {"bytes": 5, "sha256": "hash"} for f in ("motor.jsonl", "native.jsonl")}
    evidence = {m: {"pose-baseline": {"raw": copy.deepcopy(raw)}} for m in audit.MODELS}
    return rows, evidence, edge


def score_fixture(gains):
    def pair(episode, case, v2, v3):
        return dict(episode_id=episode, case=case, matched_complete=True, outcomes=dict(v2=v2, v3=v3),
                    baseline_outcomes=[False, False])
    fresh = [pair(f"p{p}-yaw{yaw}", f"p{p}", False, (p, yaw) in gains)
             for p in range(6) for yaw in (-90, 0, 90, 180)]
    original = [pair("winner", "shaft", True, True), pair("other", "shaft", False, True)]
    history = [dict(controller="every_tick", case="shaft", episode_id=r["episode_id"], physical_success=r["outcomes"]["v2"])
               for r in original]
    return (dict(original=original, fresh=fresh, stress=[]), {"shaft": {"wet":"54","dry":"41"}}, history,
            audit.collect_recovery.read(audit.trainer.DECLARATION)["progress_criterion"])


class RecoveryEvaluationTests(unittest.TestCase):
    def test_complete_assignment_inventory_and_role_binding(self):
        original = audit.motor.CASES
        fresh = audit.QA / "lily-recovery-fresh-cases.tsv"
        stress = audit.QA / "lily-motor-stress-cases.tsv"
        for label, path in zip(("original", "fresh", "stress"), (original, fresh, stress)):
            with path.open() as stream:
                cases = list(audit.csv.DictReader(stream, delimiter="\t"))
            jobs = audit.motor.make_jobs(cases, list(audit.ARMS), original=label == "original")
            self.assertEqual(len(audit.assignments(jobs, list(reversed(jobs)))), 2*audit.SIZES[label])
            for broken in [jobs[:-1], jobs + jobs[:1], [dict(jobs[0], yaw_deg=9), *jobs[1:]]]:
                with self.assertRaises(ValueError):
                    audit.assignments(jobs, broken)
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp)/"receipt.json"
            header = dict(schema=1, evaluation="independent-stock-bank-motor", physics_hz=150, budget_sim_seconds=60,
                          required_dry_steps=38, observation="synchronous pre-input physical state",
                          cases_sha256=audit.motor.digest(stress), case_set="perturbation", scope="matrix")
            write_rows(raw, [header])
            with self.assertRaisesRegex(ValueError, "receipt header"):
                audit.audit_matrix("fresh", "v2", Path(tmp), {"digest": audit.motor.digest(fresh)}, {}, {}, {}, {})

    def test_rebuilds_physical_loss_and_detects_receipt_or_actor_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            job, case, row = one_loss(path)
            rebuilt, evidence = audit.audit_execution(job, row, path, case, wait)
            self.assertIs(rebuilt["physical_success"], False)
            self.assertEqual(evidence["reinferred_decisions"], 1)
            with self.assertRaisesRegex(ValueError, "receipt differs"):
                audit.audit_execution(job, dict(row, health=10), path, case, wait)
            with self.assertRaisesRegex(ValueError, "incorrect_initial_actor"):
                audit.audit_execution(job, row, path, dict(case, x="2"), wait)
            (path/"handoff.json").touch()
            with self.assertRaisesRegex(ValueError, "handoff"):
                audit.audit_execution(job, row, path, case, wait)

    def test_consistent_but_wrong_policy_action_fails_independent_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            job, case, _ = one_loss(path)
            for name in ("motor.jsonl", "native.jsonl", "decisions.jsonl"):
                records = [json.loads(line) for line in (path/name).read_bytes().splitlines()]
                if name == "decisions.jsonl":
                    records[0]["quantized"][0] = 50
                else:
                    records[1]["axes"][0] = .5
                write_rows(path/name, records)
            forged = audit.motor.assess(job, path, 1, case)
            for row in (forged, audit.motor.censored(job, "worker_failed")):
                with self.subTest(terminal=row["terminal"]), self.assertRaisesRegex(ValueError, "frozen decision mismatch"):
                    audit.audit_execution(job, row, path, case, wait)

    def test_censored_actuation_must_match_frozen_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            job, case, _ = one_loss(path)
            receipt = audit.motor.censored(job, "worker_failed")
            names = ("motor.jsonl", "native.jsonl")
            original = {name: (path/name).read_bytes() for name in names}
            for changed in ((names[0],), (names[1],), names):
                with self.subTest(changed=changed):
                    for name, data in original.items():
                        records = [json.loads(line) for line in data.splitlines()]
                        if name in changed:
                            records[1]["axes"][0] = .5
                        write_rows(path/name, records)
                    with self.assertRaisesRegex(ValueError, "action_does_not_match_decision"):
                        audit.audit_execution(job, receipt, path, case, wait)

    def test_censored_control_identity_and_button_edges(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            job, case, _ = one_loss(path)
            receipt = audit.motor.censored(job, "worker_failed")
            for name in ("motor.jsonl", "native.jsonl"):
                stream = path/name
                original = stream.read_bytes()
                changes = dict(tick=1, step=1, owner="baseline", event="observation", buttons=1)
                if name == "motor.jsonl":
                    changes.update(source_tick=1, presses=1)
                for field, value in changes.items():
                    with self.subTest(name=name, field=field):
                        records = [json.loads(line) for line in original.splitlines()]
                        records[1][field] = value
                        write_rows(stream, records)
                        with self.assertRaises(ValueError):
                            audit.audit_execution(job, receipt, path, case, wait)
                stream.write_bytes(original)

    def test_censored_control_streams_can_end_independently(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            job, case, _ = one_loss(path)
            receipt = audit.motor.censored(job, "worker_failed")
            motor, native = path/"motor.jsonl", path/"native.jsonl"
            observation, applied = motor.read_bytes().splitlines(keepends=True)
            assigned, actual, _ = native.read_bytes().splitlines(keepends=True)
            partial = b'{"event":'
            for applied_tail in (b"", partial, applied):
                for native_tail in (b"", partial, actual):
                    with self.subTest(applied=applied_tail, native=native_tail):
                        motor.write_bytes(observation + applied_tail)
                        native.write_bytes(assigned + native_tail)
                        kept, evidence = audit.audit_execution(job, receipt, path, case, wait)
                        self.assertEqual(kept, receipt)
                        self.assertEqual(evidence["reinferred_decisions"], 1)
                        self.assertIsNone(evidence["observed_native_terminal"])
            native.unlink()
            motor.write_bytes(observation)
            kept, evidence = audit.audit_execution(job, receipt, path, case, wait)
            self.assertEqual(kept, receipt)
            self.assertEqual(evidence["reinferred_decisions"], 1)
            for stream, prefix, record, other, other_prefix in (
                    (motor, observation, applied, native, assigned),
                    (native, assigned, actual, motor, observation)):
                with self.subTest(stream=stream.name):
                    other.write_bytes(other_prefix + partial)
                    forged = dict(json.loads(record), axes=[.5, 0, 0, 0])
                    stream.write_bytes(prefix + json.dumps(forged).encode())
                    with self.assertRaisesRegex(ValueError, "action_does_not_match_decision"):
                        audit.audit_execution(job, receipt, path, case, wait)
                    stream.write_bytes(prefix + partial + b"\n")
                    with self.assertRaises(json.JSONDecodeError):
                        audit.audit_execution(job, receipt, path, case, wait)

    def test_censored_prefix_preserves_held_buttons_and_native_step_rounding(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            job, case, _ = one_loss(path)
            job.update(control_dt=.125, requested_hold_ms=125)
            motor, native = path/"motor.jsonl", path/"native.jsonl"
            obs, applied = map(json.loads, motor.read_bytes().splitlines())
            assigned, control, _ = map(json.loads, native.read_bytes().splitlines())
            frames, journal, controls = [], [], [assigned]
            for tick, step in enumerate((0, 19, 38, 56, 75, 94, 112)):
                sample = dict(obs, tick=tick, step=step, sense=dict(obs["sense"], buttons=int(tick > 0), tick_ms=125))
                action = dict(tick=tick, step=step, buttons=1, axes=[.5, 0, 0, 0])
                frames.extend([sample, dict(applied, **action, source_tick=tick, presses=int(tick == 0))])
                controls.append(dict(control, **action))
                journal.append(dict(tick=tick, observation_sha256=audit.sha((json.dumps(sample)+"\n").encode()),
                                    quantized=[50, 0, 0, 0, 1]))
            write_rows(motor, frames)
            write_rows(native, controls)
            write_rows(path/"decisions.jsonl", journal)

            def hold(observation, context):
                return {"action": "motor", "steps": [dict(duration_ms=125, forward=.5, buttons=1)]}

            receipt = audit.motor.censored(job, "worker_failed")
            kept, evidence = audit.audit_execution(job, receipt, path, case, hold)
            self.assertEqual(kept, receipt)
            self.assertEqual(evidence["reinferred_decisions"], len(journal))
            controls[-1]["step"] += 1
            write_rows(native, controls)
            with self.assertRaisesRegex(ValueError, "invalid control identity at tick 6"):
                audit.audit_execution(job, receipt, path, case, hold)

    def test_partial_censored_tail_retains_prior_decision_but_malformed_complete_line_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            job, case, _ = one_loss(path)
            row = audit.motor.censored(job, "worker_failed")
            journal = path / "decisions.jsonl"
            first = journal.read_bytes()
            frames = path / "motor.jsonl"
            obs, _ = [json.loads(line) for line in frames.read_bytes().splitlines()]
            second = json.dumps(dict(obs, tick=1)).encode() + b"\n"
            with frames.open("ab") as output:
                output.write(second)
            journal.write_bytes(first + b'{"tick":1,"observation_sha256":')
            kept, evidence = audit.audit_execution(job, row, path, case, wait)
            self.assertIsNone(kept["physical_success"])
            self.assertEqual((evidence["reinferred_decisions"], evidence["incomplete_decision_replay_at_tick"]), (1, 1))
            journal.write_bytes(journal.read_bytes() + b"\n")
            with self.assertRaises(json.JSONDecodeError):
                audit.audit_execution(job, row, path, case, wait)
            # A syntactically complete last line can lose its newline and still prove a contradiction.
            journal.write_bytes(first + json.dumps(dict(tick=1, observation_sha256="wrong", quantized=[0]*5)).encode())
            with self.assertRaisesRegex(ValueError, "frozen decision mismatch"):
                audit.audit_execution(job, row, path, case, wait)

    def test_engine_marker_and_censored_outcomes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            job, case, row = one_loss(path)
            unavailable = audit.motor.censored(job, "worker_failed")
            kept, evidence = audit.audit_execution(job, unavailable, path, case, wait)
            self.assertEqual(kept, unavailable)
            self.assertEqual(evidence["reinferred_decisions"], 1)
            self.assertEqual(evidence["observed_native_terminal"]["terminal"], "died")
            with self.assertRaisesRegex(ValueError, "pending"):
                audit.audit_execution(job, dict(unavailable, reason="pending"), path, case, wait)
            with self.assertRaisesRegex(ValueError, "baseline has policy journal"):
                audit.audit_execution(dict(job, controller="baseline"), row, path, case, wait)
            for lines in (b"", b"STOCK FULL TICK landed=1\nSTOCK FULL TICK landed=0\n",
                          b"STOCK FULL TICK landed=0\npartial\n"):
                (path/"engine.log").write_bytes(lines)
                with self.assertRaisesRegex(ValueError, "final engine marker"):
                    audit.engine_code(path/"engine.log")

    def test_equal_starts_and_repeat_bytes_but_independent_first_actions(self):
        rows, evidence, edge = pair_fixture()
        pair = audit.check_pair("pose", rows, evidence, edge)
        self.assertTrue(pair["matched_complete"])
        self.assertNotEqual(*pair["first_model_actions"].values())
        rows["v3"]["pose", "every_tick"]["initial_observation_sha256"] = "wrong"
        with self.assertRaisesRegex(ValueError, "different actual starts"):
            audit.check_pair("pose", rows, evidence, edge)
        rows, evidence, edge = pair_fixture()
        with self.assertRaisesRegex(ValueError, "assigned edge or seed"):
            audit.check_pair("pose", rows, evidence, [999, *edge[1:]])
        evidence["v3"]["pose-baseline"]["raw"]["motor.jsonl"]["bytes"] += 1
        with self.assertRaisesRegex(ValueError, "baseline trace bytes"):
            audit.check_pair("pose", rows, evidence, edge)

    def test_clustered_threshold_and_retention_of_specific_shaft_winner(self):
        concentrated = score_fixture({(0, yaw) for yaw in (-90, 0, 90, 180)})
        score = audit.score(*concentrated)
        self.assertEqual((score["fresh_net"], score["fresh_positions_with_positive_net"], score["status"]),
                         (4, 1, "not_met"))
        enough = score_fixture({(0, -90), (0, 0), (1, 90), (2, 180)})
        self.assertEqual(audit.score(*enough)["status"], "met")
        enough[0]["fresh"][-1]["outcomes"] = dict(v2=True, v3=False)
        score = audit.score(*enough)
        self.assertEqual((score["fresh_net"], score["fresh_counts"]["regression"], score["status"]), (3, 1, "not_met"))
        enough[0]["fresh"][-1]["outcomes"] = dict(v2=False, v3=False)
        enough[0]["original"][0]["outcomes"]["v3"] = False
        score = audit.score(*enough)
        self.assertEqual((score["lost_original_shaft_winners"], score["status"]), (["winner"], "not_met"))
        enough[0]["original"][0].update(matched_complete=False, outcomes=dict(v2=True, v3=None))
        score = audit.score(*enough)
        self.assertEqual((score["unmeasured_original_shaft_winners"], score["status"]), (["winner"], "inconclusive"))

    def test_unmatched_baseline_does_not_disappear_from_fresh_comparison(self):
        sample = score_fixture({(0, -90), (0, 0), (1, 90), (2, 180)})
        sample[0]["fresh"][0].update(matched_complete=False, baseline_outcomes=[None, False])
        score = audit.score(*sample)
        self.assertEqual((score["fresh_counts"]["gain"], score["status"]), (4, "inconclusive"))
        self.assertIsNone(score["measured_thresholds"])

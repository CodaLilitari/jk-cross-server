"""Rebuild the sealed recovery evaluation from local evidence, without running the game or fitting."""
import argparse
from collections import Counter
from contextlib import nullcontext
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import runpy
import sys

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "native/tests/stock_water_replay"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(FIXTURE))
import collect_recovery
import evaluate_motor as motor
from bots.lily import motor_contact, train_recovery_motor as trainer

QA = ROOT / "qa"
FREEZE = QA / "lily-recovery-freeze.json"
FREEZE_SHA = "f6802ddbf9d8929fecd1d43cec82d370283819af8c032b04fad6f388a3a52dad"
HISTORY = QA / "lily-independent-motor.json"
HISTORY_SHA = "a0eb0352ed6c69e56242a114ef2d601b12852bcf2eaf61584f95093dc577f9cf"
SPEC = ROOT / "docs/superpowers/specs/2026-11-22-lily-recovery-learning-design.md"
SETS = ("fresh", "original", "stress")
MODELS = ("v2", "v3")
ARMS = ("baseline", "every_tick")
SIZES = {"original": 27, "stress": 16, "fresh": 24}
TRACE_FILES = ("start.json", "motor.jsonl", "native.jsonl", "decisions.jsonl", "engine.log", "worker.log")
TRAIN_FIELDS = ("train_samples", "original_samples", "correction_samples", "ordered_rows_sha256",
                "original_rows_sha256", "correction_rows_sha256", "declaration_sha256",
                "collection_receipt_sha256", "reference_receipt_sha256")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def equal(actual, expected, detail):
    motor.check(collect_recovery.same(actual, expected), detail)


def checked_bytes(path, digest):
    data = path.read_bytes()
    motor.check(sha(data) == digest, "file identity mismatch: " + path.name)
    return data


def trusted_export(stem, model_sha, export_sha, canonical_sha):
    model_path = ROOT / f"bots/lily/models/{stem}.json"
    policy = ROOT / f"bots/lily/policies/{stem}.py"
    model = motor_contact.validate_model(json.loads(checked_bytes(model_path, model_sha)))
    canonical = sha(motor_contact.canonical(model))
    equal(canonical, canonical_sha, "canonical model digest")
    equal(sha(motor_contact.policy_source(model).encode()), export_sha, "standalone export regeneration")
    checked_bytes(policy, export_sha)
    source = runpy.run_path(str(policy))
    equal([source["ABI_VERSION"], source["MODEL_SHA256"], source["MODEL"]], [1, canonical, model],
          "exported model or ABI")
    return dict(model=model, model_sha256=model_sha, candidate_sha256=export_sha, decide=source["decide"])


def frozen_inputs(declaration_path, freeze_path, collection, reference):
    freeze = json.loads(checked_bytes(freeze_path, FREEZE_SHA))
    decl = json.loads(checked_bytes(declaration_path, trainer.DECLARATION_SHA256))
    equal(freeze["declaration_sha256"], trainer.DECLARATION_SHA256, "freeze declaration")
    checked_bytes(SPEC, decl["spec_sha256"])
    for name, expected in freeze["files_sha256"].items():
        checked_bytes(ROOT / name, expected)
    checked_bytes(collection / "receipt.json", freeze["collection_receipt_sha256"])
    checked_bytes(reference / "receipt.json", freeze["reference_receipt_sha256"])
    history = json.loads(checked_bytes(HISTORY, HISTORY_SHA))["experiments"]
    old_freeze = collect_recovery.read(QA / "lily-contact-freeze.json")
    policies = {
        "v2": trusted_export("water_contact_v2", decl["v2_model_sha256"], decl["v2_policy_sha256"],
                             old_freeze["canonical_model_sha256"]),
        "v3": trusted_export("water_recovery_v3", freeze["model_file_sha256"], freeze["policy_file_sha256"],
                             freeze["canonical_model_sha256"]),
    }
    _, source = trainer.training_rows(reference, collection, declaration_path)
    model_source = policies["v3"]["model"]["provenance"]
    equal({k: model_source[k] for k in source}, source, "model training provenance")
    training = {k: source[k] for k in TRAIN_FIELDS}
    equal(training, {k: freeze[k] for k in training}, "frozen training matrix")
    training["collection_prefix_decisions_reinferred"] = 0
    for job in collect_recovery.read(collection / "receipt.json")["episodes"]:
        # The strict loader checks that these are exactly the original v2 prefix bytes.
        # Additionally run the export on every collected prefix, including failed teacher runs.
        n = job["decisions"]
        count = replay_decisions(collection / job["work_dir"], job["requested_hold_ms"],
                                 policies["v2"]["decide"], n, prefix=True)
        training["collection_prefix_decisions_reinferred"] += count
    stress = collect_recovery.read(QA / "lily-motor-stress-plan.json")
    paths = {"original": (motor.CASES, decl["cases_sha256"]),
             "fresh": (ROOT / decl["fresh_evaluation"]["cases"], decl["fresh_evaluation"]["cases_sha256"]),
             "stress": (ROOT / stress["cases"], stress["cases_sha256"])}
    cases = {}
    for label, (path, expected) in paths.items():
        data = checked_bytes(path, expected)
        rows = list(csv.DictReader(data.decode().splitlines(), delimiter="\t"))
        jobs = motor.make_jobs(rows, list(ARMS), original=(label == "original"))
        equal(len(jobs), 2*SIZES[label], "declared assignment count")
        cases[label] = dict(rows={r["case"]: r for r in rows}, jobs=jobs, digest=expected)
    fixture = dict(freeze["fixture_provenance"]["fixture_source_sha256"])
    del fixture["bots/map_audit.py"]  # Captured separately in collection, outside evaluate_motor's glob.
    live = "native/tests/stock_water_replay/live_policy.py"
    fixture[live] = history["contact_original"]["provenance"]["fixture_source_sha256"][live]
    for name, expected in fixture.items():
        checked_bytes(ROOT / name, expected)
    return decl, freeze, history, policies, cases, fixture, training


def keyed(rows):
    result = {}
    for r in rows:
        key = (r["episode_id"], r["controller"])
        motor.check(key not in result, "duplicate assignment: " + "/".join(key))
        result[key] = r
    return result


def assignments(jobs, recorded):
    rows = keyed(recorded)
    motor.check(rows.keys() == keyed(jobs).keys(), "missing or unexpected assignments")
    for job in jobs:
        row = rows[job["episode_id"], job["controller"]]
        equal({k: row[k] for k in job}, job, "changed assignment")
        motor.check(job["hold_ticks"] == 1, "wrong cadence")
    return rows


def check_decision(raw, journal_line, tick, duration, decide, decode=json.loads):
    record = decode(raw)
    decision = decode(journal_line)
    motor.check(record["tick"] == tick and record["event"] == "observation", "observation order")
    observation = {"state": record["state"], "lily": {"sense": record["sense"]}}
    context = {"directive": {"goal": "learned-motor", "parameters": {
        "position": record["goal"]["position"], "duration_ms": duration}}}
    expected = motor.quantized(decide(observation, context), duration)
    equal(decision, dict(tick=tick, observation_sha256=sha(raw), quantized=expected),
          f"frozen decision mismatch at tick {tick}")
    return record, expected


def replay_decisions(work, duration, decide, count, *, prefix=False):
    with (work/"motor.jsonl").open("rb") as frames, (work/"decisions.jsonl").open("rb") as journal:
        for tick in range(count):
            check_decision(frames.readline(), journal.readline(), tick, duration, decide)
            motor.check(bool(frames.readline()), "missing applied input")
        motor.check(not journal.readline() and (prefix or not frames.readline()), "unexpected decision or input")
    return count


def decode_censored_record(raw):
    """Only a missing record or an unfinished JSON prefix at EOF is an interruption."""
    if not raw:
        raise EOFError("missing record")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        tail = exc.doc[exc.pos:]
        unfinished = (not tail or exc.msg.startswith("Unterminated string")
                      or (exc.msg == "Expecting value" and any(token.startswith(tail)
                          for token in ("true", "false", "null", "-1")))
                      or (exc.msg.startswith("Expecting ',' delimiter") and re.fullmatch(r"\.|[Ee][+-]?", tail))
                      or (exc.msg.startswith("Invalid \\u") and re.fullmatch(r"u[0-9a-fA-F]{0,3}", tail)))
        if not raw.endswith(b"\n") and unfinished:
            raise EOFError("truncated JSON record") from exc
        raise


def available_record(line):
    try:
        record = decode_censored_record(line)
    except EOFError:
        return None
    motor.check(isinstance(record, dict), "expected a trace record")
    return record


def check_censored_control(record, event, tick, step, decision, previous):
    identity = dict(event=event, tick=tick, step=step, owner="model")
    if event == "input":
        identity.update(source_tick=tick, presses=decision[4] & ~previous)
    equal({k: record.get(k) for k in identity}, identity, f"invalid {event} identity at tick {tick}")
    axes, buttons = record.get("axes"), record.get("buttons")
    motor.check(isinstance(axes, list) and len(axes) == 4 and type(buttons) is int and buttons == decision[4]
                and all(type(a) in (int, float) and abs(a - n/100) < 1e-7 for a, n in zip(axes, decision)),
                f"action_does_not_match_decision in {event} at tick {tick}")


def censored_evidence(work, job, raw, decide):
    evidence = dict(raw=raw, reinferred_decisions=0, observed_native_terminal=collect_recovery.observed_terminal(work, job))
    if "decisions.jsonl" not in raw:
        return evidence
    if "motor.jsonl" not in raw:
        return dict(evidence, incomplete_decision_replay_at_tick=0)
    native_stream = (work/"native.jsonl").open("rb") if "native.jsonl" in raw else nullcontext(iter(()))
    previous = step = 0
    residual = 0.
    dt = motor.f32(job["control_dt"])
    with native_stream as native, (work/"motor.jsonl").open("rb") as frames, (work/"decisions.jsonl").open("rb") as journal:
        assigned = available_record(next(native, b""))
        if assigned is not None:
            equal(assigned.get("event"), "assigned", "invalid native trace start")
        for tick, line in enumerate(journal):
            try:
                observation, decision = check_decision(frames.readline(), line, tick, job["requested_hold_ms"],
                                                       decide, decode=decode_censored_record)
            except EOFError:
                evidence["incomplete_decision_replay_at_tick"] = tick
                break
            evidence["reinferred_decisions"] += 1
            equal(observation["step"], step, f"invalid observation step at tick {tick}")
            applied = available_record(frames.readline())
            actual = available_record(next(native, b""))
            if applied is not None:
                check_censored_control(applied, "input", tick, step, decision, previous)
            if actual is not None:
                check_censored_control(actual, "control", tick, step, decision, previous)
            if applied is not None and actual is not None:
                motor.check(applied["axes"] == actual["axes"], "applied/native axes differ")
            previous = decision[4]
            # Match the native clock's residual carry at each 150 Hz boundary.
            span = dt + residual
            count = math.floor(span * motor.HZ + .5)
            residual = span - count/motor.HZ
            step += count
    return evidence


def raw_inventory(work):
    return {name: {"sha256": motor.digest(work/name), "bytes": (work/name).stat().st_size}
            for name in TRACE_FILES if (work/name).is_file()}


def engine_code(path):
    lines = path.read_bytes().splitlines()
    markers = [line for line in lines if line.startswith(b"STOCK FULL TICK")]
    motor.check(len(markers) == 1 and markers[0] == lines[-1]
                and markers[0] in (b"STOCK FULL TICK landed=0", b"STOCK FULL TICK landed=1"),
                "missing or ambiguous final engine marker")
    return int(markers[0].endswith(b"0"))


def audit_execution(job, row, work, case, decide, legacy=None):
    raw = raw_inventory(work)
    motor.check(not (work/"handoff.json").exists(), "unexpected recovery handoff")
    baseline = job["controller"] == "baseline"
    motor.check(not baseline or "decisions.jsonl" not in raw, "baseline has policy journal")
    if row["physical_success"] is None:
        reason = row["reason"]
        motor.check(isinstance(reason, str) and reason and reason != "pending", "matrix still pending")
        # The evaluator does not retain independent worker/engine exit codes. Its censor
        # reason remains reported, even when a terminal was flushed before a process fault.
        equal({k: row[k] for k in motor.censored(job, reason)}, motor.censored(job, reason),
              "invalid censored outcome")
        return row, censored_evidence(work, job, raw, decide)
    if not baseline:
        motor.check("worker.log" in raw, "missing worker log")
    rebuilt = motor.assess(job, work, engine_code(work/"engine.log"), case)
    if legacy is not None and baseline:
        equal(rebuilt["native_sha256"], legacy[job["episode_id"]], "legacy native baseline")
        rebuilt["legacy_baseline_match"] = True
    equal(row, rebuilt, "receipt differs from raw evidence")
    count = 0
    if not baseline:
        equal(rebuilt["decisions"], rebuilt["control_ticks"], "incomplete every-tick decisions")
        count = replay_decisions(work, job["requested_hold_ms"], decide, rebuilt["decisions"])
    return rebuilt, dict(raw=raw, reinferred_decisions=count)


def audit_matrix(label, model, directory, case_set, policy, fixture, freeze, legacy):
    data = (directory/"receipt.json").read_bytes()
    receipt = json.loads(data)
    header = dict(schema=1, evaluation="independent-stock-bank-motor", physics_hz=150, budget_sim_seconds=60,
                  required_dry_steps=38, observation="synchronous pre-input physical state",
                  cases_sha256=case_set["digest"], case_set="original" if label == "original" else "perturbation",
                  scope="matrix")
    equal({k: receipt[k] for k in header}, header, f"{label}/{model} receipt header")
    equal(sorted(receipt["arms"]), sorted(ARMS), "wrong arms")
    rows = assignments(case_set["jobs"], receipt["episodes"])
    motor.check(all(r.get("reason") != "pending" for r in rows.values()), "matrix still pending")
    if "provenance" in receipt:
        provenance = receipt["provenance"]
        collect_recovery.verify_engine(provenance, freeze["fixture_provenance"])
        equal(provenance["fixture_source_sha256"], fixture, "evaluation fixture sources")
        equal(provenance["baseline_reference_sha256"], motor.digest(motor.PRIOR), "baseline reference digest")
        for k in ("model_sha256", "candidate_sha256"):
            equal(provenance[k], policy[k], f"{label}/{model} {k}")
        motor.check(re.fullmatch("[a-f0-9]{64}", provenance["executable_sha256"]), "invalid executable digest")
    else:
        motor.check(all(r["physical_success"] is None and r["reason"].startswith("fixture_setup_")
                        for r in rows.values()), "missing evaluation provenance")
    rebuilt, audit = [], {}
    for job in case_set["jobs"]:
        episode, arm = job["episode_id"], job["controller"]
        name = episode + "-" + arm
        try:
            outcome, evidence = audit_execution(job, rows[episode, arm], directory/name, case_set["rows"][job["case"]],
                                                policy["decide"], legacy if label == "original" else None)
        except (ValueError, OSError, KeyError, IndexError, TypeError) as exc:
            raise ValueError(f"{label}/{model}/{name}: {exc}") from exc
        rebuilt.append(outcome)
        audit[name] = evidence
    equal(motor.summarize(rebuilt), receipt["summary"], "receipt summary")
    equal(sha(data), motor.digest(directory/"receipt.json"), "receipt changed during audit")
    return dict(raw_receipt_sha256=sha(data), receipt=receipt, execution_audit=audit), keyed(rebuilt)


START = ("initial_observation_sha256", "seed", "origin_sha256", "target_sector", "target_position")


def check_pair(episode, all_rows, all_audits, edge):
    rows = [all_rows[m][episode, a] for m in MODELS for a in ARMS]
    complete = [r for r in rows if r["ownership_complete"]]
    for row in complete:
        equal([row[k] for k in START], [complete[0][k] for k in START], "different actual starts")
        equal([row[k] for k in ("seed", "origin_sha256", "target_position")], edge, "changed assigned edge or seed")
    baselines = [all_rows[m][episode, "baseline"] for m in MODELS]
    identical = None
    if all(r["ownership_complete"] for r in baselines):
        inventories = [all_audits[m][episode+"-baseline"]["raw"] for m in MODELS]
        for name in ("native.jsonl", "motor.jsonl"):
            equal(inventories[0][name], inventories[1][name], "different baseline trace bytes")
        identical = True
    return dict(episode_id=episode, case=rows[0]["case"], yaw_deg=rows[0]["yaw_deg"],
                matched_complete=len(complete) == 4, repeated_baseline_identical=identical,
                actual_start={k: complete[0][k] for k in START} if complete else None,
                first_model_actions={m: all_rows[m][episode, "every_tick"].get("initial_quantized") for m in MODELS},
                outcomes={m: all_rows[m][episode, "every_tick"]["physical_success"] for m in MODELS},
                baseline_outcomes=[r["physical_success"] for r in baselines])


def paired_changes(pairs):
    positions = {}
    totals = Counter()
    transitions = {k: [] for k in ("gain", "regression", "both", "neither", "censored")}
    for pair in pairs:
        v2, v3 = (pair["outcomes"][m] for m in MODELS)
        category = "censored" if None in (v2, v3) else {
            (False, True): "gain", (True, False): "regression",
            (True, True): "both", (False, False): "neither"}[v2, v3]
        totals[category] += 1
        transitions[category].append(pair["episode_id"])
        group = positions.setdefault(pair["case"], dict.fromkeys(transitions, 0))
        group[category] += 1
    for group in positions.values():
        group["net"] = group["gain"] - group["regression"]
    return dict(counts={k: totals[k] for k in transitions}, episodes=transitions, by_position=positions)


def score(pairs, original_rows, historical, criteria):
    fresh = paired_changes(pairs["fresh"])
    totals, positions = fresh["counts"], fresh["by_position"]
    winners = sorted(r["episode_id"] for r in historical if r["controller"] == "every_tick"
                     and r["physical_success"] is True
                     and (original_rows[r["case"]]["wet"], original_rows[r["case"]]["dry"]) == ("54", "41"))
    shaft = {p["episode_id"]: p["outcomes"]["v3"] for p in pairs["original"] if p["episode_id"] in winners}
    motor.check(shaft.keys() == set(winners), "missing historical shaft assignment")
    lost = sorted(episode for episode, success in shaft.items() if success is False)
    complete = all(p["matched_complete"] for group in pairs.values() for p in group)
    net = totals["gain"] - totals["regression"]
    positive = sum(g["net"] > 0 for g in positions.values())
    tests = dict(fresh_net=net >= criteria["fresh_net_additional_landings_minimum"],
                 fresh_positions=positive >= criteria["fresh_positions_with_positive_net_minimum"],
                 shaft_retention=len(lost) <= criteria["new_original_shaft_failures_among_v2_successes_maximum"])
    return dict(status="inconclusive" if not complete else ("met" if all(tests.values()) else "not_met"),
                measured_thresholds=tests if complete else None, declaration=criteria, complete_matched_evidence=complete,
                fresh_counts=totals,
                fresh_net=net, fresh_positions_with_positive_net=positive, fresh_by_position=positions,
                historical_original_shaft_winners=winners, lost_original_shaft_winners=lost,
                unmeasured_original_shaft_winners=sorted(k for k, v in shaft.items() if v is None))


def audit(directories, collection, reference, declaration, freeze_path):
    decl, freeze, history, policies, cases, fixture, training = frozen_inputs(declaration, freeze_path, collection, reference)
    legacy = {r["episode_id"]: r["native_sha256"] for r in collect_recovery.read(motor.PRIOR)["episodes"]
              if r["controller"] == "baseline"}
    original = history["contact_original"]["episodes"]
    edges = {r["target_sector"]: [r[k] for k in ("seed", "origin_sha256", "target_position")] for r in original}
    experiments, pairs, inventory = {}, {}, {}
    historical_matches = {}
    for label in SETS:
        all_rows, all_audits, history_count = {}, {}, 0
        history_name = {"original": "contact_original", "stress": "contact_perturbation"}.get(label)
        for model in MODELS:
            result, rows = audit_matrix(label, model, directories[label, model], cases[label], policies[model],
                                        fixture, freeze, legacy)
            if model == "v2" and history_name:
                earlier = assignments(cases[label]["jobs"], history[history_name]["episodes"])
                for key, row in rows.items():
                    if row["physical_success"] is not None:
                        equal(row, earlier[key], f"{label}/{key} historical v2 or baseline trajectory")
                        history_count += 1
                historical_matches[label] = history_count
            all_rows[model], all_audits[model] = rows, result["execution_audit"]
            experiments[f"{label}_{model}"] = result
        pairs[label] = [check_pair(episode, all_rows, all_audits, edges[row["target_sector"]])
                        for (episode, arm), row in all_rows["v2"].items() if arm == "every_tick"]
        totals = {}
        for model, rows in all_rows.items():
            for arm in ARMS:
                group = [r for (_, a), r in rows.items() if a == arm]
                totals[f"{model}_{arm}"] = dict(motor.summarize(group)["all"][arm],
                                                verified_control_ticks=sum(r["control_ticks"] for r in group
                                                                           if r["ownership_complete"]),
                                                verified_physics_steps=sum(r["physics_steps"] for r in group
                                                                           if r["ownership_complete"]),
                                                reinferred_decisions=sum(all_audits[model][r["episode_id"]+"-"+arm]
                                                                         ["reinferred_decisions"] for r in group))
        n = len(pairs[label])
        inventory[label] = dict(assignments=n, assigned_executions=n*4, unique_configurations=n*3,
                                repeated_baselines=n, completed_pair_checks=sum(p["matched_complete"] for p in pairs[label]),
                                arms=totals)
    totals = {k: sum(group[k] for group in inventory.values()) for k in
              ("assignments", "assigned_executions", "unique_configurations", "repeated_baselines", "completed_pair_checks")}
    for name in ("verified_control_ticks", "verified_physics_steps", "reinferred_decisions", "censored"):
        totals[name] = sum(arm[name] for group in inventory.values() for arm in group["arms"].values())
    return dict(schema=1, evaluation="sealed-stock-bank-recovery-transfer", declaration_sha256=trainer.DECLARATION_SHA256,
                freeze_sha256=FREEZE_SHA, frozen_at_utc=freeze["frozen_at_utc"], history_sha256=HISTORY_SHA,
                training_audit=training, historical_v2_and_baseline_rows_matched=historical_matches,
                totals=totals, inventory=inventory,
                criterion=score(pairs, cases["original"]["rows"], original, decl["progress_criterion"]),
                paired_assignments=pairs, paired_changes={s: paired_changes(pairs[s]) for s in SETS},
                experiments=experiments)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for label in SETS:
        for model in MODELS:
            parser.add_argument(f"--{label}-{model}", type=Path, required=True)
    for name in ("collection", "reference", "output"):
        parser.add_argument("--"+name, type=Path, required=True)
    parser.add_argument("--declaration", type=Path, default=trainer.DECLARATION)
    parser.add_argument("--freeze", type=Path, default=FREEZE)
    args = parser.parse_args(argv)
    directories = {(s, m): getattr(args, s+"_"+m) for s in SETS for m in MODELS}
    result = audit(directories, args.collection, args.reference, args.declaration, args.freeze)
    with args.output.open("x") as stream:
        json.dump(result, stream, allow_nan=False, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()

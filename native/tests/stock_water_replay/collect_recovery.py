"""Collect and audit continuous frozen-v2 to native control handoffs."""
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
import re
import shutil
from pathlib import Path
import subprocess
import tempfile

from evaluate_motor import (CASES, HERE, HZ, MAX_STEPS, ROOT, assess, build_replay, check,
                            digest, execute_trial, f32, make_jobs, physical_record, valid_terminal)

MODEL = ROOT / "bots/lily/models/water_contact_v2.json"
POLICY = ROOT / "bots/lily/policies/water_contact_v2.py"
BOUNDARIES = {"pool-90-yaw0": (25, 100, 200, 400), "pool-110-yaw0": (39, 154, 308, 616)}
REFERENCE_FILES = {"start":"start.json", "motor":"motor.jsonl", "native":"native.jsonl",
                   "decisions":"decisions.jsonl"}
RAW_FILES = (*REFERENCE_FILES.values(), "handoff.json", "worker.log", "engine.log", "process.json")
ENGINE_IDENTITIES = ("source_hashes", "policy_hash", "compiler_flags_sha256", "map_sha256", "geometry_sha256")
EVALUATION = "assisted-stock-bank-recovery"
RETAINED_EXECUTABLE = "recovery-replay"
# Exact in-repository sources of the recovery collector, replay, codec and map reader.
# Additional neighboring evaluation scripts do not affect this historical manifest.
FIXTURE_FILES = (
    *(HERE/name for name in (
        "bank_drive.inc", "bank_oracle.h", "bank_trace.inc", "collect_motor.py", "collect_recovery.py",
        "evaluate_bank.py", "evaluate_motor.py", "geometry.py", "independent_motor.inc", "recovery.inc",
        "replay.c", "replay_loop.inc", "replay_trace.inc", "run.py")),
    HERE.parent/"test_bot_portal_collision.c", ROOT/"bots/lily/protocol.py", ROOT/"bots/map_audit.py",
)


def read(path):
    return json.loads(path.read_bytes())


def lines(path):
    return path.read_bytes().splitlines(keepends=True)


def same(a, b):
    """JSON comparison that distinguishes true, 1 and 1.0."""
    return json.dumps(a, sort_keys=True, allow_nan=False) == json.dumps(b, sort_keys=True, allow_nan=False)


def passive_state(observations, dt):
    # play_exit initializes TRACE_X cases at t=80, waterSince=60. f32 at
    # each addition follows the native bot clock, including water reentry.
    clock, water, health, debt = 80., 60., 0., False
    for obs in observations:
        clock = f32(clock + f32(dt))
        if obs["sense"]["medium"] == "air":
            water = 0.
        elif not water:
            water = clock
        health = obs["state"]["health"]
        debt = obs["sense"]["breath_used_ms"] > 0
    return clock, water, health, debt


def check_controls(applied, actual, tick, owner, previous):
    axes, buttons = applied["axes"], applied["buttons"]
    check(applied["owner"] == actual["owner"] == owner and applied["source_tick"] == tick
          and same(actual["axes"], axes) and same(actual["buttons"], buttons)
          and len(axes) == 4 and all(type(x) in (int, float) and -1 <= x <= 1 for x in axes)
          and type(buttons) is int and 0 <= buttons <= 31
          and type(applied["presses"]) is int and applied["presses"] == buttons & ~previous,
          "invalid_applied_input")


def check_handoff(record, job, observations, start):
    k = job["handoff_tick"]
    reached = len(observations) > k
    check(type(record["schema"]) is int and record["schema"] == 1 and type(record["assigned_tick"]) is int
          and record["assigned_tick"] == k and record["reached"] is reached, "handoff_identity")
    if not reached:
        check(set(record) == {"schema", "assigned_tick", "reached"}, "spurious_handoff")
        return
    boundary = observations[k]
    before, after = record["before"], record["after"]
    clock, water, health, debt = passive_state(observations[:k], job["control_dt"])
    check(type(record["step"]) is int and record["step"] == job["handoff_step"] == boundary["step"]
          and f32(record["clock"]) == clock and type(record["held_buttons"]) is int
          and record["held_buttons"] == boundary["sense"]["buttons"], "handoff_boundary")
    check(record["pristine_planner"] is True and record["rng"] == start["seed"]
          and type(record["graph_nodes"]) is int and type(record["graph_edges"]) is int
          and record["graph_nodes"] > 0 and record["graph_edges"] > 0
          and tuple(record[key] for key in ("goal","objective","objective_route_node","route_count",
                                             "route_pos","water_exit_phase")) == (-1,0,-1,0,0,0),
          "nonpristine_planner")
    expected_before = dict(progress_position=observations[0]["sense"]["position"], stuck_at=80,
                           water_since=60, previous_health=0, had_breath_debt=0)
    check(same(before, expected_before), "invalid_pre_handoff_bookkeeping")
    check(after.keys() == before.keys() and after["progress_position"] == boundary["sense"]["position"]
          and f32(after["stuck_at"]) == clock and f32(after["water_since"]) == water
          and after["previous_health"] == health and type(after["had_breath_debt"]) is int
          and after["had_breath_debt"] == int(debt), "invalid_passive_bookkeeping")


def raw_hashes(work):
    return {name:digest(work/name) for name in RAW_FILES if (work/name).is_file()}


def audit_trial(job, work, ref, code):
    """Join all actual mixed inputs, the reference prefix and the precise boundary."""
    native = lines(work/"native.jsonl")
    motor = lines(work/"motor.jsonl")
    decisions = lines(work/"decisions.jsonl")
    reference_native = lines(ref/"native.jsonl")
    reference_motor = lines(ref/"motor.jsonl")
    reference_decisions = lines(ref/"decisions.jsonl")
    check(len(native) >= 3 and code in (0,1), "missing_physical_terminal")
    start, end = json.loads(native[0]), json.loads(native[-1])
    check(start["event"] == "assigned" and start["sector"] == job["target_sector"]
          and end["event"] == "terminal" and valid_terminal(end, job, code), "invalid_native_terminal")
    n, k = end["ticks"], job["handoff_tick"]
    prefix = min(n,k)
    reached = n > k
    check(len(native) == n+2 and len(motor) == n*2 and len(decisions) == prefix, "incomplete_timeline")
    check((work/"start.json").read_bytes() == (ref/"start.json").read_bytes()
          and native[:prefix+1] == reference_native[:prefix+1]
          and motor[:2*prefix+int(reached)] == reference_motor[:2*prefix+int(reached)]
          and decisions == reference_decisions[:prefix], "changed_reference_prefix_or_boundary")
    if not reached:
        check(native == reference_native and motor == reference_motor and decisions == reference_decisions,
              "early_terminal_differs_from_reference")
    observations = []
    step = previous = 0
    residual = 0.
    dt = f32(job["control_dt"])
    for tick in range(n):
        obs, applied = map(json.loads, motor[2*tick:2*tick+2])
        actual = json.loads(native[tick+1])
        check([obs["event"], applied["event"], actual["event"]] == ["observation","input","control"]
              and all(type(r["tick"]) is int and type(r["step"]) is int and
                      (r["tick"],r["step"]) == (tick,step) for r in (obs,applied,actual)),
              "unordered_control")
        physical_record(obs)
        sense = obs["sense"]
        check(sense["medium"] in ("air","water") and actual["wet"] is (sense["medium"] == "water")
              and type(sense["supported"]) is bool and type(sense["on_water_surface"]) is bool
              and sense["on_water_surface"] == bool(obs["physics_flags"] & 0x100000)
              and sense["buttons"] == previous and f32(sense["tick_ms"]) == f32(dt*1000)
              and same(obs["goal"], {"sector":start["sector"], "position":start["position"]})
              and all(type(actual[key]) is int and actual[key] == 0 for key in
                      ("action_seq", "sample_id", "revision", "world_epoch", "life_epoch")),
              "invalid_physical_observation")
        check_controls(applied, actual, tick, "model" if tick < k else "baseline", previous)
        observations.append(obs)
        previous = applied["buttons"]
        span = dt+residual
        count = math.floor(span*HZ+.5)
        residual = span-count/HZ
        if tick == n-1:
            check(step < end["step"] <= min(step+count, MAX_STEPS), "invalid_last_step")
        step += count
    handoff = read(work/"handoff.json")
    check_handoff(handoff, job, observations, start)
    if reached:
        graph = re.findall(rb"^BOT_NAV_READY nodes=(\d+) directed_edges=(\d+) ", (work/"engine.log").read_bytes(), re.M)
        check(len(graph) == 1 and tuple(map(int, graph[0])) == (handoff["graph_nodes"], handoff["graph_edges"]),
              "handoff_graph_identity")
    suffix_steps = end["step"]-job["handoff_step"] if reached else 0
    hashes = raw_hashes(work)
    check(set(hashes) == set(RAW_FILES), "incomplete_raw_files")
    return dict(job, terminal=end["terminal"], physical_success=end["terminal"] == "supported_dry",
                ownership_complete=True, baseline_assisted=True, handoff_reached=reached,
                teacher_start_tick=k if reached else None, teacher_start_step=job["handoff_step"] if reached else None,
                model_ticks=prefix, teacher_ticks=n-prefix, decisions=len(decisions), control_ticks=n,
                physics_steps=end["step"], suffix_physics_steps=suffix_steps, elapsed_sim_seconds=end["step"]/HZ,
                suffix_sim_seconds=suffix_steps/HZ, seed=start["seed"], target_position=start["position"],
                health=end["health"], sector=end["sector"], dry_steps=end["dry_steps"],
                first_breath_step=end["first_breath_step"], returncode=code, handoff=handoff, raw_sha256=hashes)


def assignments(decl):
    check(type(decl["schema"]) is int and decl["schema"] == 1 and decl["cases_sha256"] == digest(CASES)
          and decl["v2_policy_sha256"] == digest(POLICY) and decl["v2_model_sha256"] == digest(MODEL),
          "invalid_frozen_inputs")
    with CASES.open() as stream:
        cases = list(csv.DictReader(stream, delimiter="\t"))
    rows = {r["case"]:r for r in cases}
    originals = {j["episode_id"]:j for j in make_jobs(cases, ["every_tick"], True)}
    jobs = []
    expected = {(episode,k) for episode,ticks in BOUNDARIES.items() for k in ticks}
    for entry in decl["recovery_jobs"]:
        episode, k = entry["episode_id"], entry["handoff_tick"]
        check(type(k) is int and (episode,k) in expected, "undeclared_or_duplicate_assignment")
        expected.remove((episode,k))
        original = originals[episode]
        check(type(entry["handoff_step"]) is int and entry["handoff_step"] == math.floor(
              f32(original["control_dt"])*HZ*k+.5), "wrong_declared_boundary")
        fields = {key:entry[key] for key in ("handoff_tick","handoff_step")}
        fields.update({"reference_"+key+"_sha256":entry["reference_"+key+"_sha256"] for key in REFERENCE_FILES})
        for key in ("reference_boundary_observation_sha256", "reference_motor_prefix_including_boundary_sha256",
                    "reference_decision_prefix_sha256"):
            if key in entry:
                fields[key] = entry[key]
        jobs.append(dict(original, **fields, controller="recovery", baseline_assisted=True,
                         work_dir=f"{episode}-k{k}-recovery"))
    check(not expected, "missing_assignments")
    return jobs, rows


def validate_reference(reference, decl, jobs, rows):
    check(digest(reference/"receipt.json") == decl["reference_receipt_sha256"], "reference_receipt_mismatch")
    receipt = read(reference/"receipt.json")
    check(receipt["cases_sha256"] == decl["cases_sha256"] and receipt["case_set"] == "original"
          and receipt["scope"] == "matrix" and receipt["provenance"]["candidate_sha256"] == decl["v2_policy_sha256"]
          and receipt["provenance"]["model_sha256"] == decl["v2_model_sha256"], "wrong_reference_controller")
    verified = {}
    for job in jobs:
        episode = job["episode_id"]
        folder = reference/(episode+"-every_tick")
        if episode not in verified:
            matches = [r for r in receipt["episodes"] if (r["episode_id"],r["controller"]) == (episode,"every_tick")]
            check(len(matches) == 1, "missing_reference_row")
            old = matches[0]
            original = next(j for j in make_jobs([rows[job["case"]]], ["every_tick"], True) if j["episode_id"] == episode)
            calc = assess(original, folder, 0 if old["physical_success"] else 1, rows[job["case"]])
            check(same(calc, old), "invalid_reference_timeline")
            verified[episode] = {key:digest(folder/file) for key,file in REFERENCE_FILES.items()}
        motor = lines(folder/"motor.jsonl")
        decisions = lines(folder/"decisions.jsonl")
        k = job["handoff_tick"]
        if 2*k < len(motor):
            check(json.loads(motor[2*k])["step"] == job["handoff_step"], "reference_boundary_step")
            witness = {
                "reference_boundary_observation_sha256":motor[2*k],
                "reference_motor_prefix_including_boundary_sha256":b"".join(motor[:2*k+1]),
                "reference_decision_prefix_sha256":b"".join(decisions[:k]),
            }
            check(all(key not in job or hashlib.sha256(data).hexdigest() == job[key] for key,data in witness.items()),
                  "reference_boundary_digest")
        check(all(job["reference_"+key+"_sha256"] == value for key,value in verified[episode].items()),
              "reference_file_mismatch")
    return receipt["provenance"]


def verify_engine(provenance, reference_provenance):
    check(all(same(provenance[key], reference_provenance[key]) for key in ENGINE_IDENTITIES),
          "reference_engine_or_geometry_mismatch")


def fixture_manifest():
    return {str(p.relative_to(ROOT)):digest(p) for p in FIXTURE_FILES}


def verify_fixture(provenance, output):
    check(provenance.get("fixture_source_sha256") == fixture_manifest(), "fixture_source_mismatch")
    executable = output/RETAINED_EXECUTABLE
    check(executable.is_file() and not executable.is_symlink()
          and provenance.get("executable_sha256") == digest(executable), "retained_executable_mismatch")


def observed_terminal(work, job):
    # Check the native terminal record's format and physical rules independently
    # of the OS process status; it may have been flushed immediately before a crash.
    try:
        end = json.loads(lines(work/"native.jsonl")[-1])
        expected_clean_exit = int(end["terminal"] != "supported_dry")
        if end["event"] == "terminal" and valid_terminal(end, job, expected_clean_exit):
            return end
    except (OSError, ValueError, TypeError, KeyError, IndexError):
        pass
    return None


def censored(job, reason, work, status=None):
    return dict(job, terminal="unavailable", physical_success=None, handoff_reached=None,
                teacher_start_tick=None, teacher_start_step=None, ownership_complete=False,
                returncode=status["engine_returncode"] if status else None,
                worker_returncode=status["worker_returncode"] if status else None,
                observed_native_terminal=observed_terminal(work, job), reason=reason, raw_sha256=raw_hashes(work))


def classify_trial(job, work, ref):
    """Use the same captured process status and evidence at collection and re-audit."""
    if not (work/"process.json").is_file():
        return censored(job, "missing_process_evidence", work)
    status = read(work/"process.json")
    check(status.get("schema") == 1 and status.get("timed_out") in (None,"engine","worker")
          and all(value is None or type(value) is int for value in
                  (status["engine_returncode"], status["worker_returncode"]))
          and (status["error"] is None or isinstance(status["error"], str)), "invalid_process_evidence")
    engine, worker = status["engine_returncode"], status["worker_returncode"]
    if status["timed_out"]:
        return censored(job, status["timed_out"]+"_timeout", work, status)
    if engine not in (0,1):
        return censored(job, status["error"] or "engine_abnormal_exit", work, status)
    if worker != 0:
        return censored(job, status["error"] or "worker_failed", work, status)
    check(status["error"] is None, "unexplained_process_error_after_normal_exit")
    try:
        return dict(audit_trial(job, work, ref, engine), worker_returncode=worker)
    except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
        reason = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        return censored(job, reason, work, status)


def summary(rows):
    return dict(assigned=len(rows), assisted_landings=sum(r["physical_success"] is True for r in rows),
                physical_losses=sum(r["physical_success"] is False for r in rows),
                censored=sum(r["physical_success"] is None for r in rows),
                terminals=dict(Counter(r["terminal"] for r in rows)))


def assess_recovery(output: Path, reference: Path, declaration: Path) -> list[dict]:
    """Re-audit every assigned result from raw bytes before consuming any teacher rows."""
    output, reference, declaration = map(Path, (output, reference, declaration))
    decl = read(declaration)
    jobs, cases = assignments(decl)
    ref_provenance = validate_reference(reference, decl, jobs, cases)
    receipt = read(output/"receipt.json")
    check(receipt["schema"] == 1 and receipt["evaluation"] == EVALUATION and receipt["physics_hz"] == HZ
          and receipt["budget_physics_steps"] == MAX_STEPS and receipt["declaration_sha256"] == digest(declaration)
          and receipt["reference_receipt_sha256"] == decl["reference_receipt_sha256"]
          and len(receipt["episodes"]) == len(jobs) and receipt["complete"] is True, "incomplete_recovery_receipt")
    if "provenance" in receipt or any((output/j["work_dir"]).exists() for j in jobs):
        verify_fixture(receipt.get("provenance", {}), output)
        verify_engine(receipt["provenance"], ref_provenance)
        check(receipt["provenance"]["model_sha256"] == decl["v2_model_sha256"] and
              receipt["provenance"]["candidate_sha256"] == decl["v2_policy_sha256"], "wrong_collection_controller")
    results = []
    for job, recorded in zip(jobs, receipt["episodes"]):
        work = output/job["work_dir"]
        ref = reference/(job["episode_id"]+"-every_tick")
        check(all(same(recorded[key], value) for key,value in job.items()), "changed_recovery_assignment")
        if work.exists():
            derived = classify_trial(job, work, ref)
        else:
            check(recorded.get("reason","").startswith("fixture_setup_") or recorded.get("reason") == "work_dir_unavailable",
                  "missing_assignment_work_directory")
            derived = censored(job, recorded["reason"], work)
        check(same(derived, recorded), "recovery_receipt_disagrees_with_evidence")
        results.append(derived)
    check(same(summary(results), receipt["summary"]), "wrong_recovery_summary")
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("source","build","map","reference","declaration","output"):
        parser.add_argument("--"+key, type=Path, required=True)
    args = parser.parse_args(argv)
    decl = read(args.declaration)
    jobs, cases = assignments(decl)
    out = args.output.resolve()
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    results = [censored(j, "pending", out/j["work_dir"]) for j in jobs]
    receipt = dict(schema=1, evaluation=EVALUATION, physics_hz=HZ, budget_physics_steps=MAX_STEPS,
                   declaration_sha256=digest(args.declaration), reference_receipt_sha256=decl["reference_receipt_sha256"])

    def save():
        receipt.update(complete=all(r.get("reason") != "pending" for r in results), episodes=results,
                       summary=summary(results))
        temp = out/"receipt.tmp"
        temp.write_text(json.dumps(receipt, indent=2, allow_nan=False)+"\n")
        temp.replace(out/"receipt.json")

    save()
    with tempfile.TemporaryDirectory(prefix="lily-recovery-") as build:
        tmp = Path(build)
        try:
            ref_provenance = validate_reference(args.reference, decl, jobs, cases)
            manifest = fixture_manifest()
            built, geometry, provenance = build_replay(args.source, args.build, args.map, tmp, independent_motor=True)
            policy, model = tmp/"policy.py", tmp/"model.json"
            policy.write_bytes(POLICY.read_bytes())
            model.write_bytes(MODEL.read_bytes())
            executable = out/RETAINED_EXECUTABLE
            shutil.copyfile(built, executable)
            executable.chmod(0o500)
            provenance.update(candidate_sha256=digest(policy), model_sha256=digest(model), geometry_sha256=digest(geometry),
                              compiler_flags_sha256=digest(args.build/"CMakeFiles/sith_engine.dir/flags.make"),
                              fixture_source_sha256=manifest)
            verify_fixture(provenance, out)
            verify_engine(provenance, ref_provenance)
            check(provenance["candidate_sha256"] == decl["v2_policy_sha256"] and
                  provenance["model_sha256"] == decl["v2_model_sha256"], "changed_frozen_controller")
            receipt["provenance"] = provenance
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
            reason = "fixture_setup_" + (str(exc) if isinstance(exc, ValueError) else type(exc).__name__)
            results = [censored(j, reason, out/j["work_dir"]) for j in jobs]
            save()
            return 1
        for i, job in enumerate(jobs):
            work = out/job["work_dir"]
            try:
                execute_trial(job, cases[job["case"]], executable, geometry, work, policy, model,
                              recovery_tick=job["handoff_tick"])
            except (OSError, ValueError, subprocess.SubprocessError):
                # The launcher journals actual child return codes even on an exception.
                pass
            if work.exists():
                results[i] = classify_trial(job, work, args.reference/(job["episode_id"]+"-every_tick"))
            else:
                results[i] = censored(job, "work_dir_unavailable", work)
            print(job["work_dir"], results[i]["terminal"], results[i].get("reason",""), flush=True)
            save()
    assess_recovery(out, args.reference, args.declaration)
    return int(any(r["physical_success"] is None for r in results))


if __name__ == "__main__":
    raise SystemExit(main())

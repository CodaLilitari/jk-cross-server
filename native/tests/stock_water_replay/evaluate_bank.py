"""Compare the stock autonomous seat with a live, opt-in water_bc_v1 assignment."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import ExitStack, closing
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time

from collect_motor import case_environment
from run import HERE, build_replay

ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from bots.companion import Hub
from bots.companion_cli import call, load_private
from bots.lily.bank_task import bank_verdict
from bots.lily.runtime import get_directive

POLICY = ROOT / "bots/lily/policies/water_bc_v1.py"
MODEL = ROOT / "bots/lily/models/water_bc_v1.json"
CASES = HERE / "bank_cases.tsv"
ARMS = ("baseline", "candidate")
OWNERS = ("baseline", "candidate", "neutral", "unknown")
HZ = 150
MAX_STEPS = 60 * HZ


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assignments(cases):
    # Freeze the prior model split before attempting to load either controller.
    heldout = {"lily-232.797-yaw-90", "lily-232.797-yaw0", "lily-232.797-yaw90",
               "lily-232.797-yaw180", "pool-100-yaw0"}
    jobs = []
    seen = set()
    for row in cases:
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", row["case"]):
            raise ValueError("Invalid case name")
        for yaw in map(int, row["yaw_offsets"].split(",")):
            episode = f"{row['case']}-yaw{yaw}"
            if episode in seen:
                raise ValueError("Duplicate case and yaw")
            seen.add(episode)
            directive_id = "bank-" + hashlib.sha256(episode.encode()).hexdigest()[:32]
            for arm in ARMS:
                jobs.append(dict(episode_id=episode, directive_id=directive_id, case=row["case"], yaw_deg=yaw, controller=arm,
                                 control_dt=float(row["control_dt"]), target_sector=int(row["dry"]),
                                 split="holdout" if episode in heldout else "training"))
    return jobs


def unavailable(job, reason, terminal="unavailable"):
    verdict = bank_verdict(terminal=terminal, controller=job["controller"], wet_takeover=False,
                           baseline_assisted=False, ownership_complete=False)
    return dict(job, **verdict, reason=reason, evidence="native-stock-replay", wet_takeover=False,
                ownership_complete=False, baseline_assisted=False, control_ticks=dict.fromkeys(OWNERS, 0),
                baseline_fraction=None, elapsed_sim_seconds=None, health=None, sector=None,
                first_breath_seconds=None)


def valid_terminal(end, job, code):
    kind, step, ticks = end["terminal"], end["step"], end["ticks"]
    if not (type(step) is int and 1 <= step <= MAX_STEPS and type(ticks) is int and 1 <= ticks <= step
            and type(end["sector"]) is int and math.isfinite(end["health"])
            and type(end["dry_steps"]) is int and 0 <= end["dry_steps"] <= step):
        return False
    if end["first_breath_step"] is not None and not (type(end["first_breath_step"]) is int
                                                     and 1 <= end["first_breath_step"] <= step):
        return False
    if kind == "supported_dry":
        return code == 0 and end["health"] > 0 and end["dry_steps"] == 38 and end["sector"] == job["target_sector"]
    if kind == "died":
        return code == 1 and end["health"] <= 0 and end["dry_steps"] < 38
    return kind == "sim_timeout" and code == 1 and step == MAX_STEPS and end["health"] > 0 and end["dry_steps"] < 38


def score_trial(job, events, controller_rows, code, *, baseline_digest, candidate_digest, fence):
    """Join actual native motor emission to a scoped, journal-bound policy revision."""
    if code not in (0, 1):
        return unavailable(job, "native_process_error"), []
    if not events or events[-1].get("event") != "terminal":
        return unavailable(job, "missing_native_terminal"), []
    start, end = events[0], events[-1]
    if (start.get("event") != "assigned" or start.get("sector") != job["target_sector"]
            or not valid_terminal(end, job, code)
            or any(r["event"] != "control" for r in events[1:-1])):
        return unavailable(job, "invalid_native_evidence", "invalid_evidence"), []

    scoped = [r for r in controller_rows if fence and all(r.get(k) == v for k, v in fence.items())]
    tasks = {r["task_id"] for r in scoped if r["event"] == "bank_start"
             and r.get("directive_id") == job["directive_id"] and r.get("position") == start["position"]
             and r.get("sector") == start["sector"] and r.get("budget_seconds") == 60
             and r.get("policy_hash") == candidate_digest}
    bound = {(r["action_seq"], r["revision"], r["sample_id"]) for r in scoped
             if r["event"] == "attempt" and r.get("kind") == "motor" and r.get("policy_hash") == candidate_digest
             and r.get("revision") == (int(candidate_digest[:8], 16) or 1)
             and len(tasks) == 1 and r.get("task_id") in tasks}
    frames = events[1:-1]
    indices = Counter(r["tick"] for r in frames)
    counts = dict.fromkeys(OWNERS, 0)
    counts["unknown"] = len(set(range(end["ticks"])) - indices.keys())
    complete = set(indices) <= set(range(end["ticks"])) and list(indices) == sorted(indices)
    joined, wet_steps, seqs = [], [], set()
    for frame in frames:
        owner = frame["owner"]
        seq, revision, sample = (frame[k] for k in ("action_seq", "revision", "sample_id"))
        tick = frame["tick"]
        if indices[tick] != 1 or not 0 <= tick < end["ticks"] or type(frame["wet"]) is not bool:
            owner = "unknown"
        elif owner == "motor":
            matched = (job["controller"] == "candidate" and (seq, revision, sample) in bound
                       and all(frame[k] == fence[k] for k in ("life_epoch", "world_epoch")))
            owner = "candidate" if matched else "unknown"
            if matched:
                seqs.add(seq)
                if frame["wet"]:
                    wet_steps.append(frame["step"])
        elif owner not in ("baseline", "neutral") or seq or revision or sample:
            owner = "unknown"
        policy = {"baseline": baseline_digest, "candidate": candidate_digest}.get(owner)
        joined.append(dict(frame, attributed_owner=owner, policy_hash=policy))
        counts[owner] += 1
    complete = complete and not counts["unknown"]
    assisted = job["controller"] == "candidate" and counts["baseline"] > 0
    verdict = bank_verdict(terminal=end["terminal"], controller=job["controller"], wet_takeover=bool(wet_steps),
                           baseline_assisted=assisted, ownership_complete=complete)
    breath = end["first_breath_step"]
    return dict(job, **verdict, evidence="native-stock-replay", reason=None, control_ticks=counts,
                baseline_fraction=counts["baseline"]/end["ticks"], ownership_complete=complete,
                baseline_assisted=assisted, wet_takeover=bool(wet_steps), wet_motor_ticks=len(wet_steps),
                first_wet_motor_seconds=wet_steps[0]/HZ if wet_steps else None, applied_motor_actions=len(seqs),
                bound_motor_actions=len(bound), seed=start["seed"], target_position=start["position"],
                sector=end["sector"], health=end["health"], physics_steps=end["step"],
                elapsed_sim_seconds=end["step"]/HZ, first_breath_seconds=breath/HZ if breath is not None else None,
                dry_steps=end["dry_steps"]), joined


def summarize(rows):
    result = {}
    for split in ("all", "training", "holdout"):
        arms = result[split] = {}
        for arm in ARMS:
            group = [r for r in rows if r["controller"] == arm and (split == "all" or r["split"] == split)]
            arms[arm] = dict(assigned=len(group), physical_wins=sum(r["physical_success"] is True for r in group),
                             physical_losses=sum(r["physical_success"] is False for r in group),
                             censored=sum(r["physical_success"] is None for r in group),
                             attribution_eligible=sum(r["controller_success"] is not None for r in group),
                             controller_wins=sum(r["controller_success"] is True for r in group),
                             attributions=dict(Counter(r["attribution"] for r in group)))
    return result


def json_rows(path):
    if not path.exists():
        return []
    with path.open() as stream:
        return [json.loads(line) for line in stream]


def stop_process(process, interrupt=False):
    if process.poll() is None:
        process.send_signal(signal.SIGINT if interrupt else signal.SIGTERM)
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def live_case(command, env, work, job, environment, policy):
    with ExitStack() as stack:
        hub = stack.enter_context(closing(Hub(work, ["lily"], 0, experimental_ids=("lily",))))
        child = stack.enter_context(closing(hub.take_socket("lily")))
        credential_path = work/"companion/lily.json"
        credential = load_private(credential_path)
        goal = work/"directive.json"
        controller_log = stack.enter_context((work/"controller.log").open("wb"))
        cli = subprocess.Popen([sys.executable, "-B", "-m", "bots.lily", "--credentials", credential_path,
                                "--memory", work/"experience.sqlite3", "--trace", work/"controller.jsonl",
                                "--environment-id", environment, "--directive-file", goal, "--policy", policy,
                                "--duration-seconds", "75"], cwd=ROOT, stdout=controller_log, stderr=subprocess.STDOUT)
        stack.callback(stop_process, cli, True)
        engine_log = stack.enter_context((work/"engine.log").open("wb"))
        engine = subprocess.Popen(command, env=dict(env, JK_BOT_LILY="1", JK_BOT_COMPANION_FD=str(child.fileno()),
                                                    LILY_REPLAY_REALTIME="1"), pass_fds=(child.fileno(),),
                                  stdout=engine_log, stderr=subprocess.STDOUT)
        stack.callback(stop_process, engine)
        child.close()
        fence = None
        deadline = time.monotonic() + 75
        while engine.poll() is None:
            if time.monotonic() >= deadline:
                raise TimeoutError("wall_deadline")
            if cli.poll() is not None:
                raise RuntimeError("controller_exited")
            hub.pump()
            native = Path(env["LILY_BANK_TRACE"])
            if fence is None and native.is_file() and native.stat().st_size:
                obs = call(credential, "observation")
                if obs.get("native_active"):
                    with native.open() as stream:
                        header = json.loads(stream.readline())
                    if header["event"] != "assigned" or header["sector"] != job["target_sector"]:
                        raise ValueError("invalid_target")
                    fence = {k:obs[k] for k in ("run_id","world_epoch","life_epoch")}
                    directive = dict(fence, id=job["directive_id"], provenance="stock-bank-evaluation",
                                     expires_at=time.time()+90, goal="escape-bank",
                                     parameters=dict(position=header["position"], sector=header["sector"], budget_seconds=60))
                    stage = goal.with_suffix(".stage")
                    stage.write_text(json.dumps(directive))
                    stage.replace(goal)
                    if get_directive(goal, fence) != directive:
                        raise ValueError("invalid_fixture_directive")
            time.sleep(.005)
        hub.pump()
        if cli.poll() is not None:
            raise RuntimeError("controller_exited")
        return engine.returncode, fence


def run_trial(job, row, executable, geometry, provenance, directory, policy):
    work = directory / (job["episode_id"]+"-"+job["controller"])
    work.mkdir(mode=0o700)
    env = case_environment(row, job["yaw_deg"])
    native = work/"native.jsonl"
    env["LILY_BANK_TRACE"] = str(native)
    command = [executable, geometry, *[row[k] for k in ("origin","wet","dry","start_sector","control_dt")]]
    fence = None
    if job["controller"] == "candidate":
        code, fence = live_case(command, env, work, job, "stock-water-"+provenance["map_sha256"][:24], policy)
    else:
        with (work/"engine.log").open("wb") as log:
            code = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=75).returncode
    controller_rows = json_rows(work/"controller.jsonl")
    result, joined = score_trial(job, json_rows(native), controller_rows, code, baseline_digest=provenance["policy_hash"],
                                 candidate_digest=provenance["candidate_sha256"], fence=fence)
    path = work/"applied.jsonl"
    with path.open("w") as stream:
        for frame in joined:
            print(json.dumps(frame, separators=(",", ":")), file=stream)
    result.update(bank_task_starts=sum(r["event"] == "bank_start" for r in controller_rows),
                  live_task_outcomes=[{k:r.get(k) for k in ("terminal", "reason", "physical_success")}
                                      for r in controller_rows if r["event"] == "bank_outcome"],
                  applied_sha256=digest(path), native_sha256=digest(native) if native.exists() else None,
                  directive_delivered=fence is not None, controller_activated=any(r["event"]=="activated" and
                  r.get("policy_hash")==provenance["candidate_sha256"] for r in controller_rows))
    return result


def save_receipt(out, receipt, results):
    receipt.update(episodes=results, summary=summarize(results))
    pending = out/"receipt.tmp"
    pending.write_text(json.dumps(receipt, indent=2, allow_nan=False)+"\n")
    pending.replace(out/"receipt.json")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "build", "map", "output"):
        parser.add_argument("--"+name, type=Path, required=True)
    parser.add_argument("--workers", type=int, choices=range(1, 9), default=4)
    parser.add_argument("--episode", action="append", help="Run selected case/yaw IDs as a labeled subset.")
    args = parser.parse_args(argv)
    with CASES.open() as f:
        cases = list(csv.DictReader(f, delimiter="\t"))
    jobs = assignments(cases)
    if args.episode:
        if set(args.episode) - {j["episode_id"] for j in jobs}:
            parser.error("Unknown episode ID")
        jobs = [j for j in jobs if j["episode_id"] in args.episode]
    out = args.output.resolve()
    out.mkdir(parents=True, mode=0o700, exist_ok=False)
    receipt = dict(schema=1, evaluation="matched-stock-bank-escape", scope="subset" if args.episode else "full-matrix",
                   physics_hz=HZ, required_dry_steps=38, budget_sim_seconds=60, motor_duration_ms=550,
                   workers=args.workers, cases_sha256=digest(CASES),
                   execution="Native stock inputs; candidate uses real-time JKCP, loopback Hub, deployed Supervisor and isolated policy worker.")
    results = [unavailable(j, "pending") for j in jobs]
    save_receipt(out, receipt, results)
    rows = {r["case"]:r for r in cases}
    with tempfile.TemporaryDirectory(prefix="lily-bank-eval-") as tmp:
        try:
            executable, geometry, provenance = build_replay(args.source, args.build, args.map, Path(tmp), bank_evaluation=True)
            policy = Path(tmp)/"water_bc_v1.py"
            policy.write_bytes(POLICY.read_bytes())
            sources = [HERE/p for p in ("evaluate_bank.py", "run.py", "geometry.py", "collect_motor.py", "replay.c",
                       "replay_loop.inc", "replay_trace.inc", "bank_drive.inc", "bank_trace.inc", "bank_oracle.h")]
            sources += [HERE.parent/"test_bot_portal_collision.c", ROOT/"bots/companion.py", ROOT/"bots/companion_cli.py"]
            sources += sorted((ROOT/"bots/lily").glob("*.py"))
            provenance.update(candidate_sha256=digest(policy), model_sha256=digest(MODEL),
                              fixture_source_sha256={str(p.relative_to(ROOT)):digest(p) for p in sources},
                              geometry_sha256=digest(geometry))
            receipt["provenance"] = provenance
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            results = [unavailable(j, "fixture_setup_"+type(exc).__name__) for j in jobs]
            save_receipt(out, receipt, results)
            return 1
        with ThreadPoolExecutor(args.workers) as pool:
            futures = {pool.submit(run_trial, j, rows[j["case"]], executable, geometry, provenance, out, policy):i
                       for i, j in enumerate(jobs)}
            for future in as_completed(futures):
                i = futures[future]
                try:
                    results[i] = future.result()
                except Exception as exc:
                    reason = str(exc) if isinstance(exc, RuntimeError) and str(exc) == "controller_exited" else type(exc).__name__
                    results[i] = unavailable(jobs[i], "trial_"+reason)
                    print(jobs[i]["episode_id"], type(exc).__name__, file=sys.stderr, flush=True)
                save_receipt(out, receipt, results)
                print(results[i]["episode_id"], results[i]["controller"], results[i]["terminal"],
                      results[i]["attribution"], flush=True)
    return int(any(r["physical_success"] is None for r in results))


if __name__ == "__main__":
    raise SystemExit(main())

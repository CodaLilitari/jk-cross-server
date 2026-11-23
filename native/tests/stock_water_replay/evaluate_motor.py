"""Measure independent motor decisions in the stock bank replay under synchronous observations."""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import runpy
import socket
import struct
import subprocess
import sys
import tempfile

from collect_motor import case_environment
from evaluate_bank import (CASES, HZ, MAX_STEPS, MODEL, POLICY, ROOT, assignments as bank_assignments,
                           digest, valid_terminal)
from run import HERE, build_replay
from bots.lily import protocol

ARMS = ("baseline", "hold550", "hold100", "every_tick")
HOLD_MS = {"hold550":550, "hold100":100}
REPLY = struct.Struct("<I4bB")
PRIOR = ROOT / "qa/lily-bank-task.json"


def tick_ms(dt):
    ms = round(dt*1000)
    if not math.isclose(ms, dt*1000, abs_tol=1e-6) or not 7 <= ms <= 250:
        raise ValueError("Expected an integral captured control interval in [7,250] ms")
    return ms


def hold_ticks(arm, dt):
    ms = tick_ms(dt)
    return (HOLD_MS.get(arm, ms) + ms - 1)//ms


def quantized(result, duration):
    if result == {"action":"wait"}:
        return [0]*5
    if (result.get("action") != "motor" or type(result.get("steps")) is not list
            or len(result["steps"]) != 1):
        raise ValueError("Expected a single motor step or wait")
    body = dict(steps=result["steps"], revision=1, sample_id=1)
    payload = protocol.encode_command(protocol.MOTOR, body, 1)
    ms, *axes, buttons, weapon, force = protocol.STEP.unpack_from(payload, protocol.MOTOR_HEADER.size)
    if ms != duration or buttons > 3 or weapon or force:
        raise ValueError("Unexpected duration or non-movement control")
    return [*axes, buttons]


def worker(fd, policy, model, journal, duration):
    source = runpy.run_path(policy)
    weights = json.loads(Path(model).read_bytes())
    canonical = json.dumps(weights, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    model_hash = hashlib.sha256(canonical).hexdigest()
    if (source.get("ABI_VERSION") != 1 or source.get("MODEL") != weights
            or source.get("MODEL_SHA256") != model_hash):
        raise ValueError("Policy and frozen model identity disagree")
    with socket.socket(fileno=fd) as channel, open(journal,"w") as output:
        while True:
            raw, _, flags, _ = channel.recvmsg(2048)
            if not raw:
                return
            if flags & socket.MSG_TRUNC:
                raise ValueError("Oversize physical observation")
            record = json.loads(raw)
            observation = {"state":record["state"], "lily":{"sense":record["sense"]}}
            context = {"directive":{"goal":"learned-motor", "parameters":{
                "position":record["goal"]["position"], "duration_ms":duration}}}
            control = quantized(source["decide"](observation, context), duration)
            packet = REPLY.pack(record["tick"], *control)
            print(json.dumps(dict(tick=record["tick"], observation_sha256=hashlib.sha256(raw).hexdigest(),
                                  quantized=control)), file=output)
            if channel.send(packet) != len(packet):
                raise OSError("Incomplete policy reply")


def check(condition, message):
    if not condition:
        raise ValueError(message)


def physical_record(obs):
    sense, state = obs["sense"], obs["state"]
    vectors = [sense[k] for k in ("position","velocity","facing","up")] + [obs["goal"]["position"]]
    check(all(isinstance(v,list) and len(v) == 3 for v in vectors), "invalid_vector_shape")
    values = [x for vector in vectors for x in vector]
    values += [state[k] for k in ("health","shields","mana")]
    values += [sense[k] for k in ("breath_used_ms","tick_ms","head_pitch")]
    check(all(type(x) in (int,float) and math.isfinite(x) for x in values), "invalid_observation_number")
    check(type(obs["sector"]) is int and type(obs["physics_flags"]) is int and
          type(sense["buttons"]) is int, "invalid_physical_identity")


def f32(value):
    return struct.unpack("<f", struct.pack("<f",float(value)))[0]


def verify_start(obs, row, yaw, origin):
    sense = obs["sense"]
    check(obs["sector"] == int(row["start_sector"]) and obs["physics_flags"] == int(row["flags"],16)
          and [f32(x) for x in sense["position"]] == [f32(row[k]) for k in ("x","y","z")]
          and [f32(x) for x in sense["velocity"]] == [0,0,f32(row["vertical_speed"])]
          and f32(sense["head_pitch"]) == f32(row["pitch"])
          and f32(sense["tick_ms"]) == f32(f32(row["control_dt"])*1000)
          and sense["breath_used_ms"] == int(row["endurance_ms"])
          and f32(obs["state"]["health"]) == f32(row["health"]), "incorrect_initial_actor")
    # Stock initializes forward along the wet-node -> dry-node horizontal vector
    # and rotates counterclockwise by the assigned yaw. Check actual orientation.
    check(origin["wet_sector"] == int(row["wet"]) and obs["goal"]["sector"] == int(row["dry"]),
          "incorrect_bank_edge")
    dx, dy = [d-w for d,w in zip(obs["goal"]["position"][:2],origin["wet_position"][:2])]
    norm = math.hypot(dx,dy)
    check(norm > 0, "undefined_start_heading")
    angle = math.radians(yaw)
    co, si = math.cos(angle), math.sin(angle)
    expected = ((dx*co-dy*si)/norm, (dx*si+dy*co)/norm, 0)
    check(all(math.isclose(a,b,abs_tol=2e-5) for a,b in zip(sense["facing"],expected))
          and all(math.isclose(a,b,abs_tol=2e-5) for a,b in zip(sense["up"],(0,0,1))),
          "incorrect_initial_heading")


def assess(job, work, code, row):
    """Prove continuous ownership by joining pre-input state, actual inputs and decision bytes."""
    native = (work/"native.jsonl").read_bytes().splitlines()
    trace = (work/"motor.jsonl").read_bytes().splitlines(keepends=True)
    records = [json.loads(line) for line in native]
    owner = "baseline" if job["controller"] == "baseline" else "model"
    journal = [] if owner == "baseline" else [json.loads(line) for line in
                                              (work/"decisions.jsonl").read_bytes().splitlines()]
    check(len(records) >= 3 and code in (0,1), "missing_physical_terminal")
    start, end = records[0], records[-1]
    check(start["event"] == "assigned" and start["sector"] == job["target_sector"]
          and end["event"] == "terminal" and valid_terminal(end,job,code), "invalid_native_terminal")
    origin = json.loads((work/"start.json").read_bytes())
    ticks = end["ticks"]
    check(len(trace) == 2*ticks and len(records) == ticks+2, "incomplete_ticks")
    hold = job["hold_ticks"]
    check(len(journal) == (0 if owner == "baseline" else (ticks+hold-1)//hold), "missing_decisions")
    previous = step = wet_ticks = 0
    residual = 0.
    dt = struct.unpack("<f", struct.pack("<f",job["control_dt"]))[0]
    for tick in range(ticks):
        raw, emitted = trace[2*tick:2*tick+2]
        obs, applied, actual = json.loads(raw), json.loads(emitted), records[tick+1]
        source = tick - tick % hold
        check([obs["event"],applied["event"],actual["event"]] == ["observation","input","control"]
              and all(row["tick"] == tick and row["step"] == step for row in (obs,applied,actual)),
              "unordered_control")
        physical_record(obs)
        if tick == 0:
            verify_start(obs,row,job["yaw_deg"],origin)
        sense = obs["sense"]
        wet = sense["medium"] == "water"
        check(type(sense["on_water_surface"]) is bool and type(sense["supported"]) is bool
              and sense["medium"] in ("water","air") and actual["wet"] is wet
              and sense["on_water_surface"] == bool(obs["physics_flags"] & 0x100000)
              and sense["buttons"] == previous and (tick or wet)
              and math.isclose(sense["tick_ms"], dt*1000, abs_tol=.0001)
              and obs["goal"] == {"position": start["position"], "sector": start["sector"]},
              "invalid_physical_observation")
        axes, buttons = applied["axes"], applied["buttons"]
        check(applied["owner"] == actual["owner"] == owner and applied["source_tick"] == source
              and actual["axes"] == axes and actual["buttons"] == buttons
              and len(axes) == 4 and all(math.isfinite(x) for x in axes)
              and type(buttons) is int and 0 <= buttons <= 31
              and applied["presses"] == buttons & ~previous, "invalid_applied_input")
        if owner == "model":
            decision = journal[source//hold]
            q = decision["quantized"]
            check(decision["tick"] == source and len(q) == 5
                  and all(type(n) is int and -100<=n<=100 for n in q[:4])
                  and type(q[4]) is int and 0 <= q[4] <= 3 and buttons == q[4]
                  and all(abs(a-n/100) < 1e-7 for a,n in zip(axes,q[:4])),
                  "action_does_not_match_decision")
            if tick == source:
                check(decision["observation_sha256"] == hashlib.sha256(raw).hexdigest(), "stale_observation")
        previous = buttons
        wet_ticks += wet
        span = dt+residual
        count = math.floor(span*HZ+.5)
        residual = span-count/HZ
        if tick == ticks-1:
            check(step < end["step"] <= min(step+count,MAX_STEPS), "invalid_last_step")
        step += count
    result = dict(job, terminal=end["terminal"], physical_success=end["terminal"]=="supported_dry",
                  ownership_complete=True, baseline_assisted=False, owner=owner, wet_ticks=wet_ticks,
                  control_ticks=ticks, decisions=len(journal), physics_steps=end["step"], health=end["health"],
                  sector=end["sector"], first_breath_step=end["first_breath_step"], dry_steps=end["dry_steps"],
                  seed=start["seed"], target_position=start["position"], elapsed_sim_seconds=end["step"]/HZ,
                  origin_sha256=digest(work/"start.json"), initial_facing=json.loads(trace[0])["sense"]["facing"],
                  initial_observation_sha256=hashlib.sha256(trace[0]).hexdigest(),
                  initial_quantized=journal[0]["quantized"] if journal else None,
                  native_sha256=digest(work/"native.jsonl"), motor_sha256=digest(work/"motor.jsonl"))
    if journal:
        result["decisions_sha256"] = digest(work/"decisions.jsonl")
    return result


def censored(job, reason):
    return dict(job, terminal="unavailable", reason=reason, physical_success=None,
                ownership_complete=False, baseline_assisted=False)


def execute_trial(job, row, executable, geometry, work, policy, model, *, recovery_tick=None):
    work.mkdir(mode=0o700)
    status = dict(schema=1, engine_returncode=None, worker_returncode=None, timed_out=None, error=None)
    try:
        return _execute_trial(job, row, executable, geometry, work, policy, model, recovery_tick, status)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        status["error"] = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        raise
    finally:
        if recovery_tick is not None:
            (work/"process.json").write_text(json.dumps(status)+"\n")


def _execute_trial(job, row, executable, geometry, work, policy, model, recovery_tick, status):
    env = case_environment(row,job["yaw_deg"])
    env.update(LILY_BANK_TRACE=str(work/"native.jsonl"), LILY_INDEPENDENT_TRACE=str(work/"motor.jsonl"),
               LILY_INDEPENDENT_ORIGIN=str(work/"start.json"), LILY_HOLD_TICKS=str(job["hold_ticks"]))
    if recovery_tick is not None:
        env.update(LILY_RECOVERY_TICK=str(recovery_tick), LILY_RECOVERY_HANDOFF=str(work/"handoff.json"))
    command = [executable,geometry,*[row[k] for k in ("origin","wet","dry","start_sector","control_dt")]]
    with (work/"engine.log").open("wb") as log:
        if job["controller"] == "baseline":
            code = subprocess.run(command, env=env, stdout=log, stderr=log, timeout=75).returncode
        else:
            with (work/"worker.log").open("wb") as worker_log:
                engine_sock, worker_sock = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
                with engine_sock, worker_sock:
                    process = subprocess.Popen([sys.executable,"-B",__file__,"worker",str(worker_sock.fileno()),
                                                str(policy),str(model),str(work/"decisions.jsonl"),
                                                str(job["requested_hold_ms"])],
                                               pass_fds=(worker_sock.fileno(),),stdout=worker_log,stderr=worker_log)
                    try:
                        worker_sock.close()
                        fd = engine_sock.fileno()
                        with subprocess.Popen(command,env=dict(env,LILY_MODEL_FD=str(fd)),pass_fds=(fd,),
                                              stdout=log,stderr=log) as engine:
                            engine_sock.close()
                            try:
                                code = engine.wait(timeout=75)
                            except subprocess.TimeoutExpired:
                                status["timed_out"] = "engine"
                                engine.kill()
                                raise
                            finally:
                                status["engine_returncode"] = engine.wait()
                        if code not in (0,1) and process.poll() is None:
                            process.kill()
                        try:
                            worker_code = process.wait(timeout=1)
                        except subprocess.TimeoutExpired:
                            status["timed_out"] = "worker"
                            raise
                    finally:
                        if process.poll() is None:
                            process.kill()
                        status["worker_returncode"] = process.wait()
            if code == 3:
                match = re.search(rb"^INDEPENDENT_ERROR ([a-z_]+)$",(work/"engine.log").read_bytes(),re.M)
                raise ValueError(match[1].decode() if match else "invalid_exchange")
            check(worker_code == 0, "worker_failed")
    return code


def run_trial(job, row, executable, geometry, out, policy, model):
    work = out / (job["episode_id"]+"-"+job["controller"])
    code = execute_trial(job, row, executable, geometry, work, policy, model)
    return assess(job,work,code,row)


def make_jobs(cases, arms, original):
    jobs = []
    for old in bank_assignments(cases):
        if old["controller"] != "baseline":
            continue
        for arm in arms:
            dt = old["control_dt"]
            ms = tick_ms(dt)
            hold = hold_ticks(arm,dt)
            jobs.append({k:v for k,v in old.items() if k!="directive_id"} | dict(
                controller=arm, split=old["split"] if original else "perturbation",
                requested_hold_ms=HOLD_MS.get(arm, ms), hold_ticks=hold, effective_hold_ms=hold*ms))
    return jobs


def summarize(rows):
    by_split = {}
    for split in ["all", *sorted({r["split"] for r in rows})]:
        by_split[split] = {}
        for arm in dict.fromkeys(r["controller"] for r in rows):
            group = [r for r in rows if r["controller"] == arm and (split == "all" or r["split"] == split)]
            by_split[split][arm] = dict(assigned=len(group), wins=sum(r["physical_success"] is True for r in group),
                                        losses=sum(r["physical_success"] is False for r in group),
                                        censored=sum(r["physical_success"] is None for r in group),
                                        terminals=dict(Counter(r["terminal"] for r in group)))
    return by_split


def validate_pairs(results):
    group = defaultdict(list)
    for index, row in enumerate(results):
        if row["ownership_complete"]:
            group[row["episode_id"]].append(index)
    for indices in group.values():
        rows = [results[i] for i in indices]
        same_start = len({(r["initial_observation_sha256"],r["seed"]) for r in rows}) == 1
        same_action = len({tuple(r["initial_quantized"]) for r in rows if r["owner"] == "model"}) <= 1
        for i in indices:
            if not same_start or not same_action:
                results[i] = censored(results[i], "paired_start_or_action_mismatch")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("source","build","map","output"):
        parser.add_argument("--"+key, type=Path, required=True)
    parser.add_argument("--policy",type=Path,default=POLICY)
    parser.add_argument("--model",type=Path,default=MODEL)
    parser.add_argument("--cases",type=Path,default=CASES)
    parser.add_argument("--arms",default=",".join(ARMS),help="Comma-separated baseline,hold550,hold100,every_tick")
    parser.add_argument("--episode",action="append")
    parser.add_argument("--workers",type=int,choices=range(1,9),default=4)
    args = parser.parse_args(argv)
    arms = args.arms.split(",")
    if set(arms)-set(ARMS) or len(set(arms)) != len(arms):
        parser.error("Invalid or duplicate arms")
    with args.cases.open() as stream:
        cases = list(csv.DictReader(stream,delimiter="\t"))
    original = digest(args.cases) == digest(CASES)
    jobs = make_jobs(cases,arms,original)
    if args.episode:
        if set(args.episode)-{j["episode_id"] for j in jobs}:
            parser.error("Unknown episode")
        jobs = [j for j in jobs if j["episode_id"] in args.episode]
    rows = {r["case"]:r for r in cases}
    out = args.output.resolve()
    out.mkdir(mode=0o700,parents=True,exist_ok=False)
    receipt = dict(schema=1,evaluation="independent-stock-bank-motor",physics_hz=HZ,budget_sim_seconds=60,
                   required_dry_steps=38,observation="synchronous pre-input physical state",
                   cases_sha256=digest(args.cases),case_set="original" if original else "perturbation",
                   arms=arms,workers=args.workers,scope="subset" if args.episode else "matrix")
    results = [censored(j,"pending") for j in jobs]

    def save():
        receipt.update(episodes=results, summary=summarize(results))
        stage = out/"receipt.tmp"
        stage.write_text(json.dumps(receipt,indent=2,allow_nan=False)+"\n")
        stage.replace(out/"receipt.json")
    save()
    with tempfile.TemporaryDirectory(prefix="lily-independent-") as tmp:
        temp = Path(tmp)
        try:
            exe, geometry, provenance = build_replay(args.source,args.build,args.map,temp,independent_motor=True)
            policy, model = temp/"frozen_policy.py", temp/"frozen_model.json"
            policy.write_bytes(args.policy.read_bytes())
            model.write_bytes(args.model.read_bytes())
            prior = json.loads(PRIOR.read_bytes())
            references = {r["episode_id"]:r["native_sha256"] for r in prior["episodes"] if r["controller"]=="baseline"}
            files = [*HERE.glob("*.inc"), *HERE.glob("*.c"), *HERE.glob("*.h"), *HERE.glob("*.py"),
                     HERE.parent/"test_bot_portal_collision.c", ROOT/"bots/lily/protocol.py"]
            provenance.update(candidate_sha256=digest(policy),model_sha256=digest(model),geometry_sha256=digest(geometry),
                              baseline_reference_sha256=digest(PRIOR),
                              compiler_flags_sha256=digest(args.build/"CMakeFiles/sith_engine.dir/flags.make"),
                              fixture_source_sha256={str(p.relative_to(ROOT)):digest(p) for p in sorted(files)})
            receipt["provenance"] = provenance
        except (OSError,ValueError,subprocess.SubprocessError) as exc:
            results = [censored(j,"fixture_setup_"+type(exc).__name__) for j in jobs]
            save()
            return 1
        with ThreadPoolExecutor(args.workers) as pool:
            pending = {pool.submit(run_trial,j,rows[j["case"]],exe,geometry,out,policy,model):i for i,j in enumerate(jobs)}
            for task in as_completed(pending):
                i = pending[task]
                try:
                    row = task.result()
                    if original and row["controller"] == "baseline":
                        check(row["native_sha256"] == references[row["episode_id"]],"legacy_baseline_mismatch")
                        row["legacy_baseline_match"] = True
                    results[i] = row
                except Exception as exc:
                    results[i] = censored(jobs[i], str(exc)[:160] if isinstance(exc,ValueError) else type(exc).__name__)
                print(jobs[i]["episode_id"],jobs[i]["controller"],results[i]["terminal"],
                      results[i].get("reason",""),flush=True)
                save()
    validate_pairs(results)
    save()
    return int(any(r["physical_success"] is None for r in results))


if __name__ == "__main__":
    if len(sys.argv) == 7 and sys.argv[1] == "worker":
        worker(int(sys.argv[2]),sys.argv[3],sys.argv[4],sys.argv[5],int(sys.argv[6]))
    else:
        raise SystemExit(main())

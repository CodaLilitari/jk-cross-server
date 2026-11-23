"""Run and independently recheck one declared every-tick or native stock-water attempt."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import subprocess
import time

from . import audit_recovery_learning as prior
from bots.lily import motor_contact as contact

motor = prior.motor
ROOT = prior.ROOT
check, equal, read = motor.check, prior.equal, prior.collect_recovery.read
MODEL_RAW = {"worker.log", "decisions.jsonl"}
BASE_RAW = {"assignment.json", "process.json", "engine.log", "start.json", "motor.jsonl", "native.jsonl"}


def now():
    return datetime.now(timezone.utc).isoformat()


def write(path, record):
    """Publish a complete JSON file exactly once; never overwrite evidence."""
    temporary = path.with_suffix(path.suffix + ".partial")
    with temporary.open("x") as stream:
        json.dump(record, stream, indent=2, allow_nan=False)
        stream.write("\n")
    os.link(temporary, path)
    temporary.unlink()


def file_record(path):
    check(path.is_file() and not path.is_symlink(), f"missing or indirect file: {path.name}")
    return {"sha256":motor.digest(path), "bytes":path.stat().st_size}


def model_data(policy, model):
    for path in (policy, model):
        check(path.is_file() and not path.is_symlink(), "missing or indirect model file")
    check(model.stat().st_size <= 2*1024*1024, "model exceeds size limit")
    data = model.read_bytes()
    values = json.loads(data)
    canonical = contact.canonical(values)
    generated = contact.policy_source(values).encode()
    check(policy.read_bytes() == generated, "frozen export identity")
    identity = dict(model_sha256=sha256(data).hexdigest(), canonical_sha256=sha256(canonical).hexdigest(),
                    policy_sha256=sha256(generated).hexdigest())
    return identity, generated


def model_identity(policy, model):
    return model_data(policy, model)[0]


def wait_native(command, env, log, status, *, timeout=75):
    with subprocess.Popen(command, env=env, stdout=log, stderr=log) as engine:
        try:
            engine.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            status["timed_out"] = "engine"
            engine.kill()
        finally:
            status["engine_returncode"] = engine.wait()


def execute(assignment, work, case, executable, geometry, policy, model):
    """Capture true child wait results, including launcher faults. The caller owns the claim."""
    job = assignment["job"]
    started = time.monotonic()
    status = dict(schema=1, started_at_utc=now(), engine_returncode=None, worker_returncode=None,
                  timed_out=None, error=None)
    try:
        if job["controller"] == "baseline":
            env = motor.case_environment(case, job["yaw_deg"])
            env.update(LILY_BANK_TRACE=str(work/"native.jsonl"), LILY_INDEPENDENT_TRACE=str(work/"motor.jsonl"),
                       LILY_INDEPENDENT_ORIGIN=str(work/"start.json"), LILY_HOLD_TICKS="1")
            command = [executable, geometry, *[case[k] for k in ("origin","wet","dry","start_sector","control_dt")]]
            with (work/"engine.log").open("xb") as log:
                wait_native(command, env, log, status)
        else:
            check(job["controller"] == "every_tick" and job["hold_ticks"] == 1, "invalid model arm")
            motor._execute_trial(job, case, executable, geometry, work, policy, model, None, status)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        status["error"] = {"type":type(exc).__name__, "message":str(exc)}
    finally:
        status.update(ended_at_utc=now(), elapsed_seconds=time.monotonic()-started)
        write(work/"process.json", status)


def time_utc(value):
    stamp = datetime.fromisoformat(value)
    check(stamp.utcoffset() is not None and stamp.utcoffset().total_seconds() == 0, "expected UTC timestamp")
    return stamp


def clean_process(status, native):
    check(set(status) == {"schema", "started_at_utc", "ended_at_utc", "elapsed_seconds", "engine_returncode",
                        "worker_returncode", "timed_out", "error"}, "process schema fields")
    equal(status["schema"], 1, "process schema")
    check(time_utc(status["ended_at_utc"]) >= time_utc(status["started_at_utc"]), "reversed process timestamps")
    elapsed = status["elapsed_seconds"]
    check(type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed >= 0, "invalid elapsed duration")
    engine, worker = status["engine_returncode"], status["worker_returncode"]
    timeout, error = status["timed_out"], status["error"]
    check(all(v is None or type(v) is int for v in (engine, worker)), "invalid process wait result")
    check(timeout in (None, "engine", "worker") and (not native or (worker is None and timeout != "worker")),
          "invalid process timeout or native worker")
    if error is not None:
        check(isinstance(error, dict) and set(error) == {"type","message"}
              and all(isinstance(v, str) for v in error.values()), "invalid launcher error")
    check(engine is not None or error is not None, "missing engine wait without launcher failure")
    check(native or worker is not None or error is not None, "missing worker wait without launcher failure")
    check(timeout is None or status[timeout+"_returncode"] is not None, "timeout without reaped child")
    normal = engine in (0, 1) and (native or worker == 0) and timeout is None
    check(not normal or error is None, "unexplained error after clean exits")
    return normal


def available_stream(path):
    """Keep complete records, including a final JSON object lacking only its newline."""
    if not path.exists():
        return []
    records = [prior.available_record(line) for line in path.read_bytes().splitlines(keepends=True)]
    return records[:-1] if records and records[-1] is None else records


def censored_engine(work, job, case, status, decide):
    """Check the engine oracle and available actuation even when a worker lost its journal."""
    wait_code = status["engine_returncode"] if status else None
    code = wait_code if wait_code in (0, 1) else None
    log = work/"engine.log"
    if log.exists() and any(line.startswith(b"STOCK FULL TICK") for line in log.read_bytes().splitlines()):
        marked = prior.engine_code(log)
        if code is not None:
            equal(marked, code, "censored engine marker")
        code = marked

    events = available_stream(work/"native.jsonl")
    if not events:
        return None
    assigned = events[0]
    equal([assigned.get("event"), assigned.get("sector")], ["assigned",job["target_sector"]], "native assignment")
    end = events[-1] if events[-1].get("event") == "terminal" else None
    controls = events[1:-1] if end is not None else events[1:]
    check(all(r.get("event") == "control" for r in controls), "unexpected native event")
    if end is None:
        return None
    physical_code = int(end["terminal"] != "supported_dry") if code is None else code
    check(motor.valid_terminal(end, job, physical_code), "invalid native terminal")
    equal(len(controls), end["ticks"], "terminal/control count")

    # Physical controls and timings are independently witnessed by the engine.
    # A journal prefix can corroborate only its own recorded decisions.
    frames = available_stream(work/"motor.jsonl")
    check(len(frames) <= 2*len(controls), "motor stream exceeds terminal")
    journal = available_stream(work/"decisions.jsonl")
    check(len(journal) <= len(controls), "journal exceeds terminal")
    previous = step = 0
    residual = 0.
    dt = motor.f32(job["control_dt"])
    owner = "model" if decide is not None else "baseline"
    for tick, actual in enumerate(controls):
        equal([actual["tick"],actual["step"],actual["owner"]], [tick,step,owner], "native tick/owner")
        axes, buttons = actual["axes"], actual["buttons"]
        check(len(axes) == 4 and all(type(a) in (int,float) and math.isfinite(a) for a in axes)
              and type(buttons) is int and 0 <= buttons <= (3 if decide else 31), "invalid physical control")
        if 2*tick < len(frames):
            obs = frames[2*tick]
            motor.physical_record(obs)
            equal([obs["event"],obs["tick"],obs["step"],obs["sense"]["buttons"]],
                  ["observation",tick,step,previous], "physical observation order/buttons")
            equal(obs["goal"], {"sector":assigned["sector"], "position":assigned["position"]}, "physical goal")
            sense = obs["sense"]
            wet = sense["medium"] == "water"
            equal(actual["wet"], wet, "physical medium")
            check(type(sense["on_water_surface"]) is bool and type(sense["supported"]) is bool
                  and sense["medium"] in ("water","air") and (tick or wet)
                  and sense["on_water_surface"] == bool(obs["physics_flags"] & 0x100000)
                  and math.isclose(sense["tick_ms"],dt*1000,abs_tol=.0001), "invalid physical observation")
            if tick == 0 and (work/"start.json").exists():
                origin = prior.available_record((work/"start.json").read_bytes())
                if origin is not None:
                    motor.verify_start(obs, case, job["yaw_deg"], origin)
            if decide is not None:
                duration = job["requested_hold_ms"]
                observation = {"state":obs["state"], "lily":{"sense":obs["sense"]}}
                context = {"directive":{"goal":"learned-motor","parameters":{
                    "position":assigned["position"], "duration_ms":duration}}}
                expected = motor.quantized(decide(observation,context),duration)
                prior.check_censored_control(actual, "control", tick, step, expected, previous)
        if 2*tick+1 < len(frames):
            applied = frames[2*tick+1]
            equal([applied[k] for k in ("event","tick","step","owner","source_tick","axes","buttons","presses")],
                  ["input",tick,step,owner,tick,axes,buttons,buttons & ~previous], "physical actuation")
        previous = buttons
        span = dt+residual
        ticks = math.floor(span*motor.HZ+.5)
        residual = span-ticks/motor.HZ
        if tick == len(controls)-1:
            check(step < end["step"] <= min(step+ticks,motor.MAX_STEPS), "invalid terminal physics step")
        step += ticks
    if (len(frames) == 2*len(controls) and (decide is None or len(journal) == len(controls))
            and (work/"start.json").is_file()
            and prior.available_record((work/"start.json").read_bytes()) is not None):
        # A fully witnessed terminal retains all the unchanged stock joins, even
        # when an independently observed late failure prevents scoring it.
        motor.assess(job, work, physical_code, case)
    return end


def audit_attempt(assignment, work, case, policy, model):
    """Reconstruct one claim from immutable raw files; contradictions raise ValueError.

    assignment comes from an independently reconstructed block ledger. policy/model
    are exact measured paths, both None for the native arm. No game launch or writes.
    """
    check(work.is_dir() and not work.is_symlink(), "missing or indirect attempt directory")
    raw = {p.name:file_record(p) for p in sorted(work.iterdir())}
    equal(read(work/"assignment.json"), assignment, "attempt claim")
    equal(assignment["fixture_source_sha256"], motor.digest(Path(motor.__file__)), "pinned evaluator source")
    job = assignment["job"]
    native = assignment["candidate_id"] == "native"
    arm = "baseline" if native else "every_tick"
    jobs = motor.make_jobs([case], [arm], assignment["role"] == "original")
    expected = next((j for j in jobs if j["episode_id"] == job["episode_id"]), None)
    equal(job, expected, "assigned case/job/controller")
    equal(job["hold_ticks"], 1, "every-tick cadence")
    allowed = BASE_RAW if native else BASE_RAW | MODEL_RAW
    # Preserve a partial process receipt after a violent interruption without promoting it.
    check(set(raw) <= allowed | {"process.json.partial"}, "foreign trace or handoff")
    check(not ("process.json.partial" in raw and "process.json" in raw
               and raw["process.json.partial"] != raw["process.json"]), "conflicting process witnesses")
    decide = None
    if native:
        equal([policy, model, assignment["model"]], [None, None, None], "native model identity")
    else:
        identity, source = model_data(policy, model)
        equal(identity, assignment["model"], "assigned model identity")
        namespace = {}
        exec(compile(source, str(policy), "exec"), namespace)
        decide = namespace["decide"]

    sidecar = "process.json.partial" in raw
    status = read(work/"process.json") if "process.json" in raw else None
    if status is None and sidecar:
        status = prior.available_record((work/"process.json.partial").read_bytes().rstrip())
    if status is None or not clean_process(status, native):
        partial = prior.censored_evidence(work, job, raw, decide)
        partial["observed_native_terminal"] = censored_engine(work, job, case, status, decide)
        return dict(partial, status="censored", row=None, process=status,
                    reason=("unpublished_process_witness" if sidecar else
                            "missing_process_witness" if status is None else "abnormal_process"))
    check(set(raw) - {"process.json","process.json.partial"} == allowed - {"process.json"}, "clean attempt file inventory")
    code = status["engine_returncode"]
    equal(prior.engine_code(work/"engine.log"), code, "engine marker/wait disagreement")
    row = motor.assess(job, work, code, case)
    count = 0
    if not native:
        equal(row["decisions"], row["control_ticks"], "every-tick ownership")
        count = prior.replay_decisions(work, job["requested_hold_ms"], decide, row["control_ticks"])
    if sidecar:
        end = available_stream(work/"native.jsonl")[-1]
        return dict(status="censored", row=None, reason="unpublished_process_witness", process=status, raw=raw,
                    observed_native_terminal=end, observed_start={key:row[key] for key in prior.START},
                    reinferred_decisions=count)
    return dict(status="complete", row=row, process=status, raw=raw, reinferred_decisions=count)


def match_starts(evaluations, expected_ids, edges):
    first = {}
    for name, rows in evaluations.items():
        equal([r["episode_id"] for r in rows], list(expected_ids), "paired assignment order: " + name)
        for r in rows:
            initial = [r[k] for k in prior.START]
            equal(initial, first.setdefault(r["episode_id"], initial), "different actual starts")
            equal([r[k] for k in ("seed", "origin_sha256", "target_position")], edges[r["target_sector"]],
                  "changed stock edge or seed")

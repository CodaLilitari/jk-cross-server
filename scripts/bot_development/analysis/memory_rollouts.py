"""Explicit policy state through the unchanged synchronous stock-input fixture."""
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import socket
import struct
import subprocess
import sys
import time

from bots.lily import motor_memory as memory
from . import outcome_rollouts as old
from .outcome_rollouts import check, equal, file_record, motor, read, write

FIELDS = {"tick","observation_sha256","quantized","state_before_sha256","state_after_sha256"}


def model_data(policy, model):
    for path in (policy,model):
        check(path.is_file() and not path.is_symlink(),"missing or indirect model")
    check(model.stat().st_size <= 2*1024*1024,"oversize model")
    data = model.read_bytes()
    values = json.loads(data)
    if values.get("schema") != 3:
        return old.model_data(policy,model)
    canonical = memory.canonical(values)
    source = memory.policy_source(values).encode()
    check(policy.read_bytes()==source,"frozen memory export")
    return dict(model_sha256=sha256(data).hexdigest(),canonical_sha256=sha256(canonical).hexdigest(),
                policy_sha256=sha256(source).hexdigest()),source


def model_identity(policy,model):
    return model_data(policy,model)[0]


class Session:
    """One episode or independent evidence pass; no state outside this instance."""
    def __init__(self,source,duration):
        self.scope = {}
        exec(compile(source,"frozen-memory-export","exec"),self.scope)
        self.model = self.scope["MODEL"]
        self.identity = sha256(memory.canonical(self.model)).hexdigest()
        equal([self.scope.get("ABI_VERSION"),self.scope.get("STATE_VERSION"),self.scope.get("MODEL_SHA256")],
              [1,1,self.identity],"memory export ABI/identity")
        self.state = memory.initial_state(self.model,self.identity)
        self.duration, self.tick = duration, 0

    def advance(self,raw):
        record = json.loads(raw)
        check(type(record["tick"]) is int and record["tick"] == self.tick and record["event"]=="observation",
              "nonconsecutive memory tick")
        before = sha256(memory.json_bytes(self.state)).hexdigest()
        observation = {"state":record["state"],"lily":{"sense":record["sense"]}}
        context = {"state":self.state,"directive":{"goal":"learned-motor","parameters":{
            "position":record["goal"]["position"],"duration_ms":self.duration}}}
        result = self.scope["decide"](observation,context)
        check(isinstance(result,dict) and "state" in result,"memory policy omitted state")
        proposed = memory.validate_state(self.model,result["state"],self.identity)
        action = {key:value for key,value in result.items() if key!="state"}
        quantized = motor.quantized(action,self.duration)
        self.state, self.tick = proposed,self.tick+1
        return dict(tick=record["tick"],observation_sha256=sha256(raw).hexdigest(),quantized=quantized,
                    state_before_sha256=before,state_after_sha256=sha256(memory.json_bytes(proposed)).hexdigest())


def worker(fd,policy,model,journal,duration):
    _,source = model_data(Path(policy),Path(model))
    session = Session(source,duration)
    with socket.socket(fileno=fd) as channel, open(journal,"x") as output:
        while True:
            raw,_,flags,_ = channel.recvmsg(2048)
            if not raw:
                return
            check(not flags & socket.MSG_TRUNC,"oversize physical observation")
            entry = session.advance(raw)
            packet = struct.pack("<I4bB",entry["tick"],*entry["quantized"])
            print(json.dumps(entry,separators=(",",":")),file=output)
            if channel.send(packet)!=len(packet):
                raise OSError("Incomplete memory policy reply")


def execute(assignment,work,case,executable,geometry,policy,model):
    if model is None or read(model).get("schema") != 3:
        return old.execute(assignment,work,case,executable,geometry,policy,model)
    job = assignment["job"]
    check(job["controller"]=="every_tick" and job["hold_ticks"]==1,"memory requires every-tick control")
    started = time.monotonic()
    status = dict(schema=1,started_at_utc=old.now(),engine_returncode=None,worker_returncode=None,timed_out=None,error=None)
    env = motor.case_environment(case,job["yaw_deg"])
    env.update(LILY_BANK_TRACE=str(work/"native.jsonl"),LILY_INDEPENDENT_TRACE=str(work/"motor.jsonl"),
               LILY_INDEPENDENT_ORIGIN=str(work/"start.json"),LILY_HOLD_TICKS="1")
    command = [executable,geometry,*[case[k] for k in ("origin","wet","dry","start_sector","control_dt")]]
    try:
        with (work/"engine.log").open("xb") as log, (work/"worker.log").open("xb") as worker_log:
            first,second = socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
            with first,second:
                process = subprocess.Popen([sys.executable,"-B","-m",__name__,"worker",str(second.fileno()),
                                            str(policy),str(model),str(work/"decisions.jsonl"),str(job["requested_hold_ms"])],
                                           cwd=old.ROOT,pass_fds=(second.fileno(),),stdout=worker_log,stderr=worker_log)
                try:
                    second.close()
                    fd = first.fileno()
                    with subprocess.Popen(command,env=dict(env,LILY_MODEL_FD=str(fd)),pass_fds=(fd,),stdout=log,stderr=log) as engine:
                        first.close()
                        try:
                            engine.wait(timeout=75)
                        except subprocess.TimeoutExpired:
                            status["timed_out"]="engine"
                            engine.kill()
                        finally:
                            status["engine_returncode"]=engine.wait()
                    if status["engine_returncode"] not in (0,1) and process.poll() is None:
                        process.kill()
                    try:
                        process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        status["timed_out"]="worker"
                finally:
                    if process.poll() is None:
                        process.kill()
                    status["worker_returncode"]=process.wait()
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        status["error"] = dict(type=type(exc).__name__,message=str(exc))
    finally:
        status.update(ended_at_utc=old.now(),elapsed_seconds=time.monotonic()-started)
        write(work/"process.json",status)


def journal_records(work,initial_hash):
    rows = old.available_stream(work/"decisions.jsonl")
    previous = initial_hash
    for tick,row in enumerate(rows):
        check(set(row)==FIELDS and type(row["tick"]) is int and row["tick"]==tick,"memory journal fields/tick")
        q = row["quantized"]
        check(isinstance(q,list) and len(q)==5 and all(type(x) is int and -100<=x<=100 for x in q[:4])
              and type(q[4]) is int and 0<=q[4]<=3,"memory journal quantized action")
        for name in ("observation_sha256","state_before_sha256","state_after_sha256"):
            check(isinstance(row[name],str) and re.fullmatch("[0-9a-f]{64}",row[name]),"memory journal digest")
        equal(row["state_before_sha256"],previous,"memory state chain")
        previous = row["state_after_sha256"]
    return rows


def available_witnesses(work,job,case,edge=None):
    """Validate complete identity records even if later streams never appeared."""
    native=old.available_stream(work/"native.jsonl")
    assigned=native[0] if native else None
    if assigned is not None:
        check(set(assigned)=={"event","sector","position","seed"} and assigned["event"]=="assigned"
              and type(assigned["sector"]) is int and assigned["sector"]==job["target_sector"]
              and type(assigned["seed"]) is int and 0<=assigned["seed"]<=0xffffffff,
              "invalid assigned record")
        memory.vector(assigned["position"],3)
        if edge is not None:
            equal([assigned["seed"],assigned["position"]],[edge[0],edge[2]],"assigned historical edge")
    origin=old.prior.available_record((work/"start.json").read_bytes()) if (work/"start.json").exists() else None
    if origin is not None:
        check(set(origin)=={"wet_sector","wet_position"} and type(origin["wet_sector"]) is int
              and origin["wet_sector"]==int(case["wet"]),"invalid origin record")
        memory.vector(origin["wet_position"],3)
        if edge is not None:
            equal(motor.digest(work/"start.json"),edge[1],"historical origin witness")
    frames=old.available_stream(work/"motor.jsonl")
    if frames:
        obs=frames[0]
        motor.physical_record(obs)
        equal([obs["event"],obs["tick"],obs["step"],obs["goal"]["sector"]],
              ["observation",0,0,job["target_sector"]],"first observation identity")
        if origin is not None:
            motor.verify_start(obs,case,job["yaw_deg"],origin)
        if edge is not None:
            equal(obs["goal"]["position"],edge[2],"first observation historical goal")
    if edge is None:
        goal=assigned["position"] if assigned else frames[0]["goal"]["position"] if frames else None
        edge=[assigned["seed"] if assigned else None,motor.digest(work/"start.json") if origin else None,goal]
    return edge


def replay_available(work,job,case,source):
    """Check every available journal/control, including tails with no terminal or journal."""
    session = Session(source,job["requested_hold_ms"])
    journal = journal_records(work,sha256(memory.json_bytes(session.state)).hexdigest())
    frames = old.available_stream(work/"motor.jsonl")
    raw_frames = (work/"motor.jsonl").read_bytes().splitlines(keepends=True) if (work/"motor.jsonl").exists() else []
    native = old.available_stream(work/"native.jsonl")
    origin = old.prior.available_record((work/"start.json").read_bytes()) if (work/"start.json").exists() else None
    assigned = native.pop(0) if native else None
    if assigned is not None:
        equal([assigned.get("event"),assigned.get("sector")],["assigned",job["target_sector"]],"memory assigned target")
    end = native.pop() if native and native[-1].get("event")=="terminal" else None
    if end is not None:
        check(motor.valid_terminal(end,job,int(end["terminal"]!="supported_dry")),"memory native terminal")
        equal(len(native),end["ticks"],"memory terminal tick count")
        check(len(frames)<=2*len(native) and len(journal)<=len(native),"memory trace exceeds terminal")
    previous = step = reinferred = verified = unavailable = 0
    residual = 0.
    dt = motor.f32(job["control_dt"])
    first_goal = None
    for tick in range(max((len(frames)+1)//2,len(native),len(journal))):
        check(step < motor.MAX_STEPS,"memory trace exceeds physics budget")
        obs = frames[2*tick] if 2*tick<len(frames) else None
        applied = frames[2*tick+1] if 2*tick+1<len(frames) else None
        actual = native[tick] if tick<len(native) else None
        decision = journal[tick] if tick<len(journal) else None
        expected = None
        if obs is not None:
            motor.physical_record(obs)
            sense = obs["sense"]
            if first_goal is None:
                first_goal = obs["goal"]
            goal = {"sector":assigned["sector"],"position":assigned["position"]} if assigned else first_goal
            equal([obs["event"],obs["tick"],obs["step"],sense["buttons"],obs["goal"]],
                  ["observation",tick,step,previous,goal],"memory physical observation order")
            equal(obs["goal"]["sector"],job["target_sector"],"memory observation target")
            wet = sense["medium"]=="water"
            check(type(sense["on_water_surface"]) is bool and type(sense["supported"]) is bool
                  and sense["medium"] in ("air","water") and (tick or wet)
                  and sense["on_water_surface"]==bool(obs["physics_flags"]&0x100000)
                  and math.isclose(sense["tick_ms"],dt*1000,abs_tol=.0001),"memory physical observation")
            if tick==0 and origin is not None:
                motor.verify_start(obs,case,job["yaw_deg"],origin)
            expected = session.advance(raw_frames[2*tick])
            if decision is not None:
                equal(decision,expected,"frozen memory decision")
                reinferred += 1
            if actual is not None:
                equal(actual.get("wet"),wet,"memory native medium")
        for event,record in (("input",applied),("control",actual)):
            if record is None:
                continue
            equal([record.get(k) for k in ("event","tick","step","owner")],[event,tick,step,"model"],"memory actuation identity")
            q = record.get("buttons")
            axes = record.get("axes")
            check(type(q) is int and 0<=q<=3 and isinstance(axes,list) and len(axes)==4
                  and all(type(a) in (int,float) and math.isfinite(a) and -1.0000001<=a<=1.0000001
                          and abs(a-round(100*a)/100)<1e-7 for a in axes),"memory physical action")
            if event=="input":
                equal([record["source_tick"],record["presses"]],[tick,q&~previous],"memory button edges")
            else:
                check(type(record.get("wet")) is bool and (tick or record["wet"]),"memory control medium")
            comparable = expected if expected is not None else decision
            if comparable is not None:
                old.prior.check_censored_control(record,event,tick,step,comparable["quantized"],previous)
        if actual is not None and applied is not None:
            equal([actual["axes"],actual["buttons"]],[applied["axes"],applied["buttons"]],"memory actuation disagreement")
        action = actual if actual is not None else applied
        if action is not None:
            previous = action["buttons"]
            verified += int(expected is not None)
            unavailable += int(expected is None)
        span = dt+residual
        ticks = math.floor(span*motor.HZ+.5)
        residual = span-ticks/motor.HZ
        if end is not None and tick==len(native)-1:
            check(step<end["step"]<=min(step+ticks,motor.MAX_STEPS),"memory terminal physics step")
        step += ticks
    observed_start = None
    if frames and assigned is not None and origin is not None:
        observed_start = dict(initial_observation_sha256=sha256(raw_frames[0]).hexdigest(),seed=assigned["seed"],
                              origin_sha256=motor.digest(work/"start.json"),target_sector=assigned["sector"],
                              target_position=assigned["position"])
    return dict(reinferred_decisions=reinferred,verified_controls=verified,unverifiable_controls=unavailable,
                unverifiable_journal=len(journal)-reinferred,observed_native_terminal=end,observed_start=observed_start)


def audit_attempt(assignment,work,case,policy,model,*,edge=None):
    edge=available_witnesses(work,assignment["job"],case,edge)
    if model is None or read(model).get("schema")!=3:
        result=old.audit_attempt(assignment,work,case,policy,model)
        if result["status"]=="censored":
            from .audit_outcome_learning import interrupted_controls
            verified,unavailable=interrupted_controls(assignment,work,case,(policy,model),edge,
                                                      result.get("observed_native_terminal") is not None)
            result.update(verified_controls=verified,unverifiable_controls=unavailable)
        return result
    check(work.is_dir() and not work.is_symlink(),"missing or indirect memory attempt")
    raw = {p.name:file_record(p) for p in sorted(work.iterdir())}
    equal(read(work/"assignment.json"),assignment,"memory attempt claim")
    equal(assignment["fixture_source_sha256"],motor.digest(Path(motor.__file__)),"frozen native evaluator")
    job = assignment["job"]
    expected = next((j for j in motor.make_jobs([case],["every_tick"],assignment["role"]=="original") if j["episode_id"]==job["episode_id"]),None)
    equal(job,expected,"memory assigned case")
    equal(job["hold_ticks"],1,"memory cadence")
    allowed = old.BASE_RAW|old.MODEL_RAW
    check(set(raw)<=allowed|{"process.json.partial"},"foreign memory attempt evidence")
    sidecar = "process.json.partial" in raw
    check(not (sidecar and "process.json" in raw and raw["process.json.partial"]!=raw["process.json"]),"conflicting process witnesses")
    identity,source = model_data(policy,model)
    equal(identity,assignment["model"],"assigned memory model")
    status = read(work/"process.json") if "process.json" in raw else None
    if status is None and sidecar:
        status = old.prior.available_record((work/"process.json.partial").read_bytes().rstrip())
    clean = status is not None and old.clean_process(status,False)
    available = replay_available(work,job,case,source)
    if status is not None and status["engine_returncode"] in (0,1) and available["observed_native_terminal"] is not None:
        equal(status["engine_returncode"],int(available["observed_native_terminal"]["terminal"]!="supported_dry"),
              "memory terminal/known engine wait")
    if (work/"engine.log").exists() and any(line.startswith(b"STOCK FULL TICK") for line in (work/"engine.log").read_bytes().splitlines()):
        marker = old.prior.engine_code(work/"engine.log")
        if status is not None and status["engine_returncode"] in (0,1):
            equal(marker,status["engine_returncode"],"memory engine marker/wait")
        if available["observed_native_terminal"]:
            equal(marker,int(available["observed_native_terminal"]["terminal"]!="supported_dry"),"memory marker/terminal")
    if not clean:
        return dict(available,raw=raw,process=status,status="censored",row=None,
                    reason="unpublished_process_witness" if sidecar else "missing_process_witness" if status is None else "abnormal_process")
    check(set(raw)-{"process.json.partial"}==allowed,"clean memory file inventory")
    equal(old.prior.engine_code(work/"engine.log"),status["engine_returncode"],"memory clean marker/wait")
    row = motor.assess(job,work,status["engine_returncode"],case)
    equal(available["reinferred_decisions"],row["control_ticks"],"memory every-tick replay")
    if sidecar:
        return dict(available,raw=raw,process=status,status="censored",row=None,reason="unpublished_process_witness")
    return dict(available,raw=raw,process=status,status="complete",row=row)


if __name__=="__main__":
    check(len(sys.argv)==7 and sys.argv[1]=="worker","expected memory worker arguments")
    worker(int(sys.argv[2]),sys.argv[3],sys.argv[4],sys.argv[5],int(sys.argv[6]))

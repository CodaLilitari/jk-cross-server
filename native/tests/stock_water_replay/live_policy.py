"""Exercise real JKCP motor control and live policy replacement under stock physics.

This bounded integration probe uses owned map geometry, an identified native
fixture seat, loopback HTTP, separate policy processes and real engine input
handlers. It is not a rendered match or a competitive skill evaluation.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

from collect_motor import case_environment
from run import HERE, build_replay

sys.path.insert(0,str(HERE.parents[2]))
from bots.companion import Hub
from bots.companion_cli import call, load_private
from bots.lily.memory import ExperienceStore, skill_key
from bots.lily.runtime import Supervisor


def source(turn):
    return '''ABI_VERSION = 1
def decide(observation, context):
    if context.get("undertaking"):
        return {"action":"wait"}
    sense = observation["lily"]["sense"]
    if sense["medium"] == "water" or not sense["supported"]:
        return {"action":"baseline"}
    return {"action":"motor", "skill":"forward-probe", "steps":[{
        "duration_ms":550, "forward":0.45, "turn":TURN}],
        "goal":{"direction":sense["facing"], "distance":0.015}}
'''.replace("TURN",repr(turn))


def replace(path, text):
    stage=path.with_suffix(".stage")
    stage.write_text(text,encoding="utf-8")
    stage.replace(path)


def trace_rows(path):
    if not path.exists():
        return []
    # The last line may be in flight; complete JSONL records alone are evidence.
    lines=path.read_text().splitlines(keepends=True)
    return [json.loads(line) for line in lines if line.endswith("\n")]


def readback(rows, database, environment):
    """A fresh supervisor/worker reads retained evidence at a recorded source pose.

    This offline readback issues no game commands. Its expected wins and trials
    come independently from the first supervisor's physical trace.
    """
    outcomes = {r["episode_id"]: r for r in rows if r["event"] == "outcome"}
    attempts = [r for r in rows if r["event"] == "attempt" and r["skill"] == "forward-probe"]
    samples = {(r["run_id"],r["world_epoch"],r["life_epoch"],r["sense"]["sample_id"]): r
               for r in rows if r["event"] == "observation"}
    for attempt in attempts:
        if outcomes.get(attempt["episode_id"], {}).get("physical_success") is not True:
            continue
        sample = samples.get(tuple(attempt[k] for k in ("run_id","world_epoch","life_epoch","sample_id")))
        if not sample or not sample["sense"]["safe_handover"]:
            continue
        sense = sample["sense"]
        planar = [*sense["facing"][:2],0.]
        if skill_key(environment, "forward-probe", sense, planar) == attempt["key"]:
            break
    else:
        return {"matched":False,"reason":"no-scored-skill-at-recorded-source-pose"}
    verdicts = [outcomes.get(a["episode_id"],{}).get("physical_success")
                for a in attempts if a["key"] == attempt["key"]]
    expected_wins = verdicts.count(True)
    expected_trials = expected_wins + verdicts.count(False)
    observation = {k:sample[k] for k in ("run_id","world_epoch","life_epoch","state")}
    observation.update(native_active=True, lily={"sense":sense,"offers":None,"progress":None,
                                                "age_seconds":{"sense":0.0}})
    class OfflineSupervisor(Supervisor):
        def send(self, obs, result, command, marker, sampled_at):
            # Called only after normal policy ABI and native payload validation.
            # Capture the proposed ordinary inputs before lease/transport access.
            self.preview = {"skill":result["skill"], "steps":command["steps"],
                            "estimate":result["state"]["estimate"]}
            return "not_sent"

    def no_transport(*args):
        raise AssertionError("Recorded-pose decision must not dispatch inputs")

    def preview(policy, path):
        store = ExperienceStore(path)
        supervisor = OfflineSupervisor(policy,store,environment,no_transport)
        try:
            end = time.monotonic() + 3
            while not hasattr(supervisor,"preview") and time.monotonic() < end:
                supervisor.step(observation)
                time.sleep(.01)
            return getattr(supervisor,"preview",{})
        finally:
            supervisor.close()
            store.close()

    with tempfile.TemporaryDirectory(prefix="lily-retained-context-") as tmp:
        policy = Path(tmp)/"readback.py"
        policy.write_text("""ABI_VERSION = 1
def decide(observation, context):
    estimate = context["skills"]["forward-probe"]
    demonstrated = estimate["trials"] > 0 and estimate["probability"] >= 2 / 3
    skill = "forward-probe" if demonstrated else "sidestep"
    step = {"duration_ms":250, "forward":.6} if demonstrated else {"duration_ms":250, "strafe":.6}
    return {"action":"motor", "skill":skill, "steps":[step], "state":{"estimate":estimate}}
""")
        fresh = preview(policy,Path(tmp)/"fresh.sqlite3")
        learned = preview(policy,database)
        policy_hash = hashlib.sha256(policy.read_bytes()).hexdigest()
    estimate = learned.get("estimate",{})
    return {"matched":estimate.get("trials")==expected_trials and estimate.get("wins")==expected_wins
                      and estimate.get("probability")==(expected_wins+1)/(expected_trials+2)
                      and fresh.get("skill")=="sidestep" and learned.get("skill")=="forward-probe",
            "method":"After the live CLI exited, independent supervisors and workers used the identical captured pose and policy bytes. Validated decisions were captured before transport.",
            "comparison_policy_sha256":policy_hash, "fresh_database_decision":fresh, "reopened_database_decision":learned,
            "skill":"forward-probe","source_sample_id":attempt["sample_id"],"action_seq":attempt["action_seq"],
            "key_sha256":hashlib.sha256(attempt["key"].encode()).hexdigest(),
            "trace_wins":expected_wins,"trace_trials":expected_trials,"worker_context_estimate":estimate}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("source","build","map","output"):
        parser.add_argument("--"+name,type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(mode=0o700,parents=True,exist_ok=False)
    policy=args.output / "live_policy.py"
    trace=args.output / "controller.jsonl"
    first,second=source(.25),source(-.25)
    hashes=[hashlib.sha256(s.encode()).hexdigest() for s in (first,second)]
    replace(policy,first)
    row=next(csv.DictReader((HERE/"bank_cases.tsv").open(),delimiter="\t"))
    engine=controller=hub=None
    stop=threading.Event()
    pumping=None
    observations=[]
    edited=rejected_candidate=False
    with tempfile.TemporaryDirectory(prefix="lily-live-physics-") as tmp:
        executable,geometry,provenance=build_replay(args.source,args.build,args.map,Path(tmp))
        engine_log=(args.output / "engine.log").open("wb")
        controller_log=(args.output / "controller.log").open("wb")
        try:
            hub=Hub(args.output,["lily"],0,experimental_ids=("lily",))
            def pump():
                while not stop.wait(.005):
                    hub.pump()
            pumping=threading.Thread(target=pump,name="physical-probe-pump",daemon=True)
            pumping.start()
            child=hub.take_socket("lily")
            env=case_environment(row,0)
            env.update(JK_BOT_LILY="1",JK_BOT_COMPANION_FD=str(child.fileno()),
                       LILY_REPLAY_REALTIME="1",LILY_REPLAY_CONTINUE="1",LILY_REPLAY_SECONDS="30")
            engine=subprocess.Popen([executable,geometry,*[row[n] for n in
                ("origin","wet","dry","start_sector","control_dt")]],env=env,
                pass_fds=(child.fileno(),),stdout=engine_log,stderr=subprocess.STDOUT)
            child.close()
            credential=load_private(args.output/"companion/lily.json")
            controller=subprocess.Popen([sys.executable,"-B","-m","bots.lily",
                "--credentials",str(args.output/"companion/lily.json"),"--policy",str(policy),
                "--memory",str(args.output/"experience.sqlite3"),
                "--environment-id","stock-water-"+provenance["map_sha256"][:24],
                "--trace",str(trace),"--duration-seconds","26"],
                cwd=HERE.parents[2],stdout=controller_log,stderr=subprocess.STDOUT)
            deadline=time.monotonic()+35
            while engine.poll() is None and time.monotonic()<deadline:
                observed=call(credential,"observation")
                sense=(observed.get("lily") or {}).get("sense")
                if sense:
                    observations.append({"time":time.monotonic(),"sense":sense,
                                         "controller_running":controller.poll() is None})
                rows=trace_rows(trace)
                if not edited and sum(r.get("event")=="outcome" and r.get("policy_hash")==hashes[0] for r in rows)>=2:
                    replace(policy,second)
                    edited=True
                if edited and not rejected_candidate and sum(r.get("event")=="outcome" and r.get("policy_hash")==hashes[1] for r in rows)>=2:
                    replace(policy,"ABI_VERSION=1\nraise ValueError('deliberate invalid candidate')\n")
                    rejected_candidate=True
                time.sleep(.04)
            engine.wait(timeout=3)
            controller.wait(timeout=3)
        finally:
            for process in (controller,engine):
                if process and process.poll() is None:
                    process.terminate()
                    try: process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill(); process.wait()
            stop.set()
            if pumping: pumping.join(timeout=2)
            if hub: hub.close()
            engine_log.close();controller_log.close()
    rows=trace_rows(trace)
    outcomes=[r for r in rows if r.get("event")=="outcome"]
    applied={h:[r for r in rows if r.get("event")=="observation" and r.get("policy_hash")==h
                and r.get("episode_id") and r["sense"].get("owner")=="motor"] for h in hashes}
    checks={"engine_landed":engine.returncode==0,
        "controller_exited_cleanly":controller.returncode==0,
        "both_policies_activated":all(any(r.get("event")=="activated" and r.get("policy_hash")==h for r in rows) for h in hashes),
        "both_policies_applied_inputs":all(applied.values()),
        "invalid_candidate_rejected":any(r.get("event")=="rejected" for r in rows),
        "baseline_resumed_after_controller_stop":any(not o["controller_running"] and o["sense"]["owner"]=="baseline" for o in observations)}
    retained = readback(rows,args.output/"experience.sqlite3","stock-water-"+provenance["map_sha256"][:24])
    checks["real_outcomes_in_restarted_worker_context"] = retained["matched"]
    receipt={"schema":1,"probe":"stock-physics live JKCP motor control and executable replacement",
        "provenance":provenance,"restart_readback":retained,"policy_hashes":hashes,"checks":checks,
        "activated":[{k:r[k] for k in ("policy_hash","previous_hash","monotonic_seconds") if k in r} for r in rows if r["event"]=="activated"],
        "observed_motor_samples":{h:len(applied[h]) for h in hashes},
        "outcomes":[{k:r[k] for k in ("policy_hash","action_seq","status","physical_success","duration_seconds","applied_ms") if k in r} for r in outcomes],
        "limitations":["No rendering, multiplayer opponents, inventory COG execution or Force effects in this fixture.",
            "The two probe policies deliberately test control authority; they are not competitive candidates.",
            "A short observed displacement is distinct from successful water escape or improved game performance."]}
    (args.output/"receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
    print(json.dumps({"checks":checks,"motor_samples":receipt["observed_motor_samples"],"outcomes":len(outcomes)},indent=2))
    return 0 if all(checks.values()) else 1


if __name__=="__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Record a bounded autonomous four-seat JKWeb trial using installed Chrome.

This preserves the reviewed capture adapter. It checks exact launcher entry points
before extending diagnostics in memory; no engine or checkout files are patched.
All recordings, observations and credentials stay in the caller's work directory.
"""
from pathlib import Path
import argparse,asyncio,gzip,hashlib,json,signal,subprocess,time,types,sys,os
p=argparse.ArgumentParser(description=__doc__)
p.add_argument("--label",required=True)
p.add_argument("--seconds",type=int,default=240)
p.add_argument("--commit",required=True,help="Exact clean Git HEAD or deployed-build.json commit")
p.add_argument("--checkout",required=True,type=Path)
p.add_argument("--work-dir",required=True,type=Path)
p.add_argument("--data",required=True,type=Path,help="Locally owned JK install")
p.add_argument("--chrome",required=True,type=Path,help="Installed Chrome/Chromium executable")
p.add_argument("--python",type=Path,default=Path(sys.executable))
p.add_argument("--relay-script",required=True,type=Path)
p.add_argument("--model-gob",type=Path)
p.add_argument("--mode",choices=("ff-guns","ff-sabers","nf-guns","nf-sabers"),default="ff-guns")
p.add_argument("--companion-chat",action="store_true")
p.add_argument("--warmup-seconds",type=int,default=30)
p.add_argument("--timeout",type=int,default=90)
a=p.parse_args()
import aiohttp
if not a.label.replace("-","").isalnum() or not 30<=a.seconds<=240:raise SystemExit("Invalid bounded run")
if len(a.commit)!=40 or any(c not in "0123456789abcdef" for c in a.commit):raise SystemExit("Expected exact reviewed commit")
root=a.work_dir.resolve()
checkout=a.checkout.resolve()
python=a.python.resolve()
root.mkdir(parents=True,exist_ok=True)
if root == checkout or checkout in root.parents:
    raise SystemExit("Keep private run outputs outside the source checkout")
if a.warmup_seconds<0 or a.timeout<=0:
    raise SystemExit("Invalid warmup or timeout")
for required in (python,a.chrome,a.relay_script):
    if not required.is_file(): raise SystemExit("Required executable/script does not exist: "+str(required))
if not a.data.is_dir() or a.model_gob and not a.model_gob.is_file():
    raise SystemExit("Game data or model path does not exist")
manifest=checkout/"deployed-build.json"
if manifest.is_file():
    deployed=json.loads(manifest.read_text())
    if deployed["commit"]!=a.commit: raise SystemExit("Deployment commit mismatch")
    for rel,expected in deployed["files"].items():
        file=(checkout/rel).resolve()
        if checkout not in file.parents or hashlib.sha256(file.read_bytes()).hexdigest()!=expected:
            raise SystemExit("Deployed runtime differs: "+rel)
else:
    observed=subprocess.check_output(["git","rev-parse","HEAD"],cwd=checkout,text=True).strip()
    if observed!=a.commit: raise SystemExit("Checkout HEAD differs from requested commit")
    runtime=("web_bots","bots/companion.py","bin/bots-jkweb")
    subprocess.run(["git","diff","--exit-code","HEAD","--",*runtime],cwd=checkout,check=True,stdout=subprocess.DEVNULL)
    web=json.loads((checkout/"web_bots/BUILD.json").read_text())
    deployed={"commit":a.commit,"files":{}}
    for rel,info in web["files"].items():
        file=(checkout/rel).resolve()
        if checkout not in file.parents or file.stat().st_size!=info["bytes"] or hashlib.sha256(file.read_bytes()).hexdigest()!=info["sha256"]:
            raise SystemExit("Packaged runtime differs: "+rel)
        deployed["files"][rel]=info["sha256"]
logpath=root/("headless-"+a.label+"-"+str(time.time_ns())+".log")
log=logpath.open("x",encoding="utf8")
cmd=[str(python),"-u","-m","web_bots.serve","--data",str(a.data.resolve()),
     "--relay-script",str(a.relay_script.resolve()),"--runtime",str(root/"runs"),
     "--room","PrivateRecording_"+a.label,"--mode",a.mode]
if a.model_gob: cmd.extend(["--model-gob",str(a.model_gob.resolve())])
if a.companion_chat: cmd.append("--companion-chat")
process_options={"creationflags":subprocess.CREATE_NEW_PROCESS_GROUP} if os.name=="nt" else {"start_new_session":True}
proc=subprocess.Popen(cmd,cwd=checkout,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,"JK_BOT_TRACE_FORCE":"1"},**process_options)
log.close();run=None;traces={n:[] for n in ("lily","boba","jan","yun")};started=time.monotonic()
try:
    for _ in range(100):
        time.sleep(.2)
        if proc.poll() is not None:raise RuntimeError("Arena exited during startup")
        ready=next((json.loads(x) for x in logpath.read_text().splitlines() if x.startswith('{"runtime":')),None)
        if ready:run=Path(ready["runtime"]);break
    if run is None:raise RuntimeError("Arena readiness timed out")
    creds={n:json.loads((run/"companion"/(n+".json")).read_text()) for n in traces}
    (root/("headless-"+a.label+"-active.json")).write_text(json.dumps({"runtime":str(run),"started_monotonic":started,"label":a.label}))
    from launcher_adapter import load_capture_launcher
    module=load_capture_launcher(checkout)
    args=types.SimpleNamespace(run_json=run/"run.json",chrome=a.chrome.resolve(),
        record_seconds=a.seconds,warmup_seconds=a.warmup_seconds,hold_seconds=0,timeout=a.timeout)
    events={n:[] for n in traces};cursors={n:0 for n in traces}
    async def work():
        stop=asyncio.Event()
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as session:
            async def one(n):
                c=creds[n]
                try:
                    async with session.get(c["url"]+"/v1/bots/"+n+"/observation",headers={"Authorization":"Bearer "+c["token"]}) as r:
                        if r.status!=200:return
                        o=await r.json()
                        if o["state"]:
                            o.pop("run_id",None);o["wall_seconds"]=round(time.monotonic()-started,3);traces[n].append(o)
                except (aiohttp.ClientError,asyncio.TimeoutError):pass
            async def get_events(n):
                c=creds[n]
                try:
                    async with session.get(c["url"]+"/v1/bots/"+n+"/events?after="+str(cursors[n]),headers={"Authorization":"Bearer "+c["token"]}) as r:
                        if r.status!=200:return
                        data=await r.json();cursors[n]=data["cursor"]
                        for event in data["events"]:
                            if event.get("kind")=="chat":
                                events[n].append({**event,"wall_seconds":round(time.monotonic()-started,3)})
                except (aiohttp.ClientError,asyncio.TimeoutError):pass
            async def collect():
                saved=0;event_at=0
                while not stop.is_set():
                    await asyncio.gather(*(one(n) for n in traces))
                    if time.monotonic()-event_at>1:
                        await asyncio.gather(*(get_events(n) for n in traces));event_at=time.monotonic()
                    if time.monotonic()-saved>5:
                        (run/"own-state-traces.json").write_text(json.dumps(traces));(run/"companion-chat-events.json").write_text(json.dumps(events));saved=time.monotonic()
                    try:await asyncio.wait_for(stop.wait(),.25)
                    except asyncio.TimeoutError:pass
            collector=asyncio.create_task(collect())
            try:await module.launch(args)
            finally:stop.set();await collector
    asyncio.run(work())
    (run/"companion-chat-events.json").write_text(json.dumps(events))
    qpath=next(run.glob("chrome-qa-*/qualification.json"));q=json.loads(qpath.read_text())
    result={"label":a.label,"build":deployed["commit"],"runtime":str(run),"receipt":str(qpath),"capture_seconds_requested":a.seconds,"trace_enabled":True,"companion_chat_enabled":a.companion_chat,"warmup_seconds":a.warmup_seconds,
        "recording_start_trace_seconds":q["recording_start_monotonic"]-started,
        "recording_return_trace_seconds":q["recording_return_monotonic"]-started,"capture":q["latest"]["capture"],
        "headless":True,"qualified":q["qualified"],"phase":q["phase"],"joined":q["latest"]["joined_count"],
        "renderer":q["latest"]["seats"]["lily"]["graphics"]["renderer"],
        "shipped_js_sha256":deployed["files"]["bin/bots-jkweb/openjkdf2.js"],
        "shipped_wasm_sha256":deployed["files"]["bin/bots-jkweb/openjkdf2.wasm"]}
    (run/"review-result.json").write_text(json.dumps(result,indent=2))
    (root/("headless-"+a.label+"-result.json")).write_text(json.dumps(result,indent=2))
    # Same trace envelope consumed by the preserved analysis tools. No bearer credentials.
    envelope={"result":result,"qualification":q,"observations":traces,"directed_commands":[],"chat_events":events}
    (run/"trial-traces.json.gz").write_bytes(gzip.compress(json.dumps(envelope).encode("utf-8")))
    print("JKHEADLESS "+json.dumps(result),flush=True)
finally:
    if run is not None:(run/"own-state-traces.json").write_text(json.dumps(traces))
    if os.name=="nt":
        subprocess.run(["taskkill","/PID",str(proc.pid),"/T","/F"],capture_output=True)
    else:
        try: os.killpg(proc.pid,signal.SIGTERM)
        except ProcessLookupError: pass
    try:proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name=="nt": proc.kill()
        else:
            try: os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError: pass
        proc.wait(timeout=5)

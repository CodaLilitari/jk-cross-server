"""One predeclared paired memory experiment, with immutable claims and no retries."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile

import numpy as np

from bots.lily import memory_search as search, motor_memory as memory
from . import run_outcome_learning as old
from . import outcome_rollouts as legacy
from . import memory_rollouts as trial
from .outcome_rollouts import ROOT,check,equal,file_record,motor,now,read,write

RUN_ID = "lily-memory-learning-20261122-01"
RUN_DIRECTORY = Path("/tmp")/RUN_ID
EXPERIMENT = "lily-protected-memory-v1"
DECLARATION = "qa/lily-memory-declaration.json"
SPEC = "docs/superpowers/specs/2026-11-22-lily-memory-learning-design.md"
PLAN = "docs/superpowers/plans/2026-11-22-lily-memory-learning.md"
PRIOR_HEADER = "6884edf86455a97c1e2bb814bfdc95f442039b4a3dec5d18e079972439386c15"
PRIOR_AUDIT = "cfbebdbea0101e1df447b2fc4d87c2e69f845f52360b893e355641f7d324a2c2"
PREVIOUS_FILES = {
    "qa/lily-outcome-declaration.json":"911ca8c8a3218334d117de8995ce88114f99ebde431c77500e894db196ac3b98",
    "qa/lily-outcome-evaluation.json":PRIOR_AUDIT,
    "qa/lily-outcome-candidates.tar.gz":"37d3f40886f253fb12b347238ad7081e2c9ea09608261815f75be217f79f5e49",
    "qa/lily-outcome-build-inputs.tar.gz":"6c0cc363ca28040eaec778031bd154249152f1783483b8b56bf288ed9b9febb6",
    "qa/lily-recovery-evaluation.json":"3c9ac2887e7d2a00736f5656280cb76be5009bb59f6f9b65506533812022a263",
    "qa/lily-independent-motor.json":"a0eb0352ed6c69e56242a114ef2d601b12852bcf2eaf61584f95093dc577f9cf"}
G4 = dict(model_sha256="af75dcd370fcc828c71075c40942712aeacbac8f7efccdf02b584da5350cecf6",
          canonical_sha256=memory.BASE_SHA256,policy_sha256="30ace86bb9f39221acf57b4b2f6abe11d4dab8e71d00dbc66d8e6586f15d9597")
NEW_SOURCES = {SPEC,PLAN,"bots/lily/motor_memory.py","bots/lily/memory_search.py",
               *(f"scripts/bot_development/analysis/{n}.py" for n in ("memory_rollouts","run_memory_learning","audit_memory_learning")),
               *(f"tests/test_lily_memory_{n}.py" for n in ("motor","search","rollouts","experiment"))}
RECIPE = dict(
    model=dict(base_canonical_sha256=memory.BASE_SHA256,units=4,features=17,outputs=6,parameters=100,static_effective_parameters=96,
               initial_seed=541123,initial_retention=[.3,.75,.93,.98],reference_tick_ms=40,decay="(.995 sigmoid(a)) ** (tick_ms/40)",
               no_history="m=u",initial_output_residual=0),
    search=dict(generations=8,directions=4,candidates_per_generation=9,arms=["static","recurrent"],
                direction_seed=541124,schedule_seed=541125,axis_scale=.30/2,button_scale=.90/2,
                input_scale=.15/17**.5,bias_scale=.12,retention_scale=.35,half_from_generation=5,
                fixed_anchors=8,rotating_pool=6,rotating_shaft=2,anchor_retention="monotonic per incumbent",
                rank=["missing v3 shaft wins","missing G4 pool wins","negative landings","charged steps"],tie="incumbent-first"),
    open=dict(arms=["v3","g4","static","recurrent","no_history"],required_pool_wins=24,required_shaft_wins=8,
              final_generation=8,tie_order=["static","recurrent"],old_development_is_open=True),
    transfer=dict(arms=["v3","g4","native","static","recurrent","no_history"],pool_net_min=4,positive_pool_positions_min=3,
                  lost_v3_shaft_max=0,lost_original_v3_shaft_max=0,historical_winners=24,
                  memory_net_min=1,memory_positive_positions_min=2,selection_locked=True),
    execution=dict(workers_max=2,retries=0,canonical_output=str(RUN_DIRECTORY),initial_free_bytes_min=4*1024**3,physics_hz=150,max_physics_steps=9000,
                   required_dry_steps=38,hold_ticks=1,teacher=False,live_promotion=False))


def execution_budget(selected):
    return dict(calibration=144,training=2304,open=160,transfer=288 if selected else 0,
                diagnostics=134 if selected else 0,total=3030 if selected else 2608)


def verify_files(root,files):
    for name,digest in files.items():
        check(isinstance(name,str) and not Path(name).is_absolute() and ".." not in Path(name).parts,"invalid frozen path")
        path = root/name
        check(path.is_file() and not path.is_symlink() and motor.digest(path)==digest,"changed frozen file: "+name)


def verify_pin_inventory(frozen,previous_files,old_decl):
    expected=old_decl["frozen_files_sha256"]|{name:motor.digest(ROOT/name) for name in NEW_SOURCES}
    equal(frozen,expected,"complete inherited and new source pins")
    equal(previous_files,PREVIOUS_FILES,"complete authenticated historical pins")


def schedule(ids,anchors):
    check(len(ids)==len(set(ids))==64 and len(anchors)==len(set(anchors))==8 and not set(ids)&set(anchors),"invalid rehearsal assignment set")
    rng = np.random.Generator(np.random.PCG64(541125))
    pool = list(rng.permutation([i for i in ids if "-pool-" in i]))
    shaft = list(rng.permutation([i for i in ids if "-shaft-" in i]))
    check((len(pool),len(shaft))==(48,16),"expected 48 pool and 16 shaft training starts")
    return [list(anchors)+pool[6*g:6*g+6]+shaft[2*g:2*g+2] for g in range(8)]


def make_declaration(commit,retained):
    check(re.fullmatch("[0-9a-f]{40}",commit) and old.git_bytes(commit,SPEC)==(ROOT/SPEC).read_bytes(),"source commit/spec binding")
    previous,_,banks = old.declaration(ROOT/"qa/lily-outcome-declaration.json")
    header_bytes = (retained/"run.json").read_bytes()
    equal(sha256(header_bytes).hexdigest(),PRIOR_HEADER,"prior retained run header")
    header = json.loads(header_bytes)
    old.verify_build_files(retained,header["build"],previous)
    frozen = dict(previous["frozen_files_sha256"])
    for name in sorted(NEW_SOURCES):
        frozen[name] = motor.digest(ROOT/name)
    for name,digest in frozen.items():
        equal(sha256(old.git_bytes(commit,name)).hexdigest(),digest,"uncommitted frozen source: "+name)
    files = {name:motor.digest(ROOT/name) for name in PREVIOUS_FILES}
    verify_pin_inventory(frozen,files,previous)
    for name,digest in files.items():
        equal(sha256(old.git_bytes(commit,name)).hexdigest(),digest,"source-committed historical input")
    anchors = [i for i in banks["development"]["ids"] if "-shaft-" in i]
    return dict(schema=1,experiment=EXPERIMENT,run_id=RUN_ID,created_at_utc=now(),implementation_commit=commit,
                recipe=RECIPE,budget_without_selection=execution_budget(False),budget_with_selection=execution_budget(True),
                previous_files_sha256=files,previous_header=header,previous_header_sha256=PRIOR_HEADER,
                frozen_files_sha256=frozen,training_batches=schedule(banks["train"]["ids"],anchors),anchors=anchors,
                cases=deepcopy(previous["cases"]),diagnostics=deepcopy(previous["diagnostics"]),
                g4=G4,v3=old.identity(old.PARENT),fixture_sources=old.fixture_sources(previous))


def declaration(path,*,published=True):
    data = path.read_bytes()
    if published:
        check(data==old.git_bytes("HEAD",DECLARATION),"unpublished or changed memory declaration")
    decl = json.loads(data)
    equal([decl["schema"],decl["experiment"],decl["run_id"]],[1,EXPERIMENT,RUN_ID],"memory experiment identity")
    equal(decl["recipe"],RECIPE,"fixed memory recipe")
    equal([decl["budget_without_selection"],decl["budget_with_selection"]],[execution_budget(False),execution_budget(True)],"fixed execution budget")
    verify_files(ROOT,decl["previous_files_sha256"])
    equal(decl["previous_files_sha256"]["qa/lily-outcome-evaluation.json"],PRIOR_AUDIT,"prior audit binding")
    verify_files(ROOT,decl["frozen_files_sha256"])
    check(NEW_SOURCES <= decl["frozen_files_sha256"].keys(),"missing memory source pin")
    commit = decl["implementation_commit"]
    check(isinstance(commit,str) and re.fullmatch("[0-9a-f]{40}",commit),"invalid memory source commit")
    for name,digest in decl["frozen_files_sha256"].items():
        equal(sha256(old.git_bytes(commit,name)).hexdigest(),digest,"memory source commit binding")
    legacy.time_utc(decl["created_at_utc"])
    equal(decl["previous_header_sha256"],PRIOR_HEADER,"fixed previous header")
    equal(sha256((json.dumps(decl["previous_header"],indent=2)+"\n").encode()).hexdigest(),PRIOR_HEADER,"retained previous header bytes")
    previous,_,banks = old.declaration(ROOT/"qa/lily-outcome-declaration.json")
    verify_pin_inventory(decl["frozen_files_sha256"],decl["previous_files_sha256"],previous)
    for name,digest in decl["previous_files_sha256"].items():
        equal(sha256(old.git_bytes(commit,name)).hexdigest(),digest,"historical input source commit binding")
    equal([decl["cases"],decl["diagnostics"]],[previous["cases"],previous["diagnostics"]],"unchanged assignment banks")
    equal(decl["fixture_sources"],old.fixture_sources(previous),"unchanged native fixture")
    equal([decl["v3"],decl["g4"]],[old.identity(old.PARENT),G4],"reference model identities")
    anchors = [i for i in banks["development"]["ids"] if "-shaft-" in i]
    equal(decl["anchors"],anchors,"all eight fixed shaft anchors")
    equal(decl["training_batches"],schedule(banks["train"]["ids"],anchors),"fixed shared rehearsal schedule")
    rehearsal = dict(role="rehearsal",sha256=sha256(memory.json_bytes([banks["train"]["sha256"],banks["development"]["sha256"],anchors])).hexdigest(),
                     cases=banks["train"]["cases"]|banks["development"]["cases"],jobs=banks["train"]["jobs"]|banks["development"]["jobs"],
                     ids=banks["train"]["ids"]+anchors)
    banks["rehearsal"] = rehearsal
    return decl,sha256(data).hexdigest(),banks


def model_paths(output,name):
    check(isinstance(name,str) and re.fullmatch(r"[a-z][a-z0-9_-]*",name),"invalid memory artifact name")
    directory=output/"models"/name
    return directory/"policy.py",directory/"model.json"


def check_model(output,ref):
    policy,model=model_paths(output,ref["artifact"])
    equal(trial.model_identity(policy,model),old.identity(ref),"measured memory artifact")
    return policy,model


def reference_bytes():
    with tarfile.open(ROOT/"qa/lily-outcome-candidates.tar.gz") as archive:
        g4={name:archive.extractfile("models/g04-c11/"+name).read() for name in ("model.json","policy.py")}
    return {"v3":{name:(ROOT/old.PARENT["model" if name=="model.json" else "policy"]).read_bytes() for name in ("model.json","policy.py")},"g4":g4}


def prior_results():
    audit=json.loads(legacy.prior.checked_bytes(ROOT/"qa/lily-outcome-evaluation.json",PRIOR_AUDIT))
    references={"v3":old.identity(old.PARENT),"g4":G4}
    expected={name:{} for name in references}
    for block in audit["blocks"].values():
        for attempt in block["attempts"]:
            if attempt["status"]!="complete":
                continue
            identity=old.identity(block["models"][attempt["candidate_id"]])
            for name,ref in references.items():
                if identity==ref:
                    value={k:attempt[k] for k in ("physical_success","physics_steps","initial_observation_sha256")}
                    equal(value,expected[name].setdefault(attempt["episode_id"],value),"contradictory historical reference")
    return expected


def check_replication(rows,expected):
    checked=0
    for row in rows:
        if row["episode_id"] in expected:
            equal({k:row[k] for k in expected[row["episode_id"]]},expected[row["episode_id"]],"baseline replication mismatch: "+row["episode_id"])
            checked+=1
    return checked


def transfer_arms(freeze,refs):
    selected=freeze.get("selected")
    check(selected in ("static","recurrent") and freeze.get("model")==refs[selected],"no exact selected memory checkpoint")
    return {name:None if name=="native" else refs[name] for name in ("v3","g4","native","static","recurrent","no_history")}


def paired(rows,left,right,ids):
    groups={name:{row["episode_id"]:row for row in rows[name]} for name in (left,right)}
    for name in groups:
        check(len(rows[name])==len(groups[name]) and set(groups[name])==set(ids),"paired comparison denominator")
    positions={}
    pairs=[]
    gains=losses=charged=0
    for episode in ids:
        a,b=groups[left][episode],groups[right][episode]
        check(type(a["physical_success"]) is bool and type(b["physical_success"]) is bool,"unscored pair")
        equal(a["case"],b["case"],"paired geometry")
        delta=int(a["physical_success"])-int(b["physical_success"])
        gain,loss=delta>0,delta<0
        gains+=gain
        losses+=loss
        positions[a["case"]]=positions.get(a["case"],0)+delta
        time=(a["physics_steps"] if a["physical_success"] else 9000)-(b["physics_steps"] if b["physical_success"] else 9000)
        charged+=time
        pairs.append(dict(episode_id=episode,case=a["case"],left=a["physical_success"],right=b["physical_success"],charged_step_difference=time))
    return dict(left=left,right=right,gains=gains,regressions=losses,ties=len(ids)-gains-losses,net=gains-losses,
                positive_positions=[p for p,n in positions.items() if n>0],positions_with_positive_net=sum(n>0 for n in positions.values()),
                position_net=positions,charged_step_difference=charged,pairs=pairs)


def memory_comparison(rows,ids):
    static=paired(rows,"recurrent","static",ids)
    removed=paired(rows,"recurrent","no_history",ids)
    return dict(against_static=static,against_no_history=removed,
                meets_memory_criterion=all(p["net"]>=1 and p["positions_with_positive_net"]>=2 for p in (static,removed)))


def audit_block(output,label,bank,ids,refs,binding,edges):
    directory=output/"blocks"/label if (output/"blocks").is_dir() else output/label
    models={name:old.identity(ref) if ref else None for name,ref in refs.items()}
    ledger=old.assignments(label,bank,ids,models,binding)
    old.require_inventory(directory,{a["work_dir"] for a in ledger},{"assignments.json","block.json"})
    equal(read(directory/"assignments.json"),ledger,"memory assignment ledger")
    block=read(directory/"block.json")
    equal(block["assignments_sha256"],motor.digest(directory/"assignments.json"),"memory ledger digest")
    paths={name:check_model(output,ref) if ref else (None,None) for name,ref in refs.items()}
    check(len(block["attempts"])==len(ledger),"memory block denominator")
    rebuilt=[]
    for assignment,recorded in zip(ledger,block["attempts"],strict=True):
        work=directory/assignment["work_dir"]
        result=trial.audit_attempt(assignment,work,bank["cases"][assignment["job"]["case"]],*paths[assignment["candidate_id"]],
                                   edge=edges.get(assignment["job"]["target_sector"]))
        equal(result,recorded,"memory receipt differs from raw evidence")
        rebuilt.append(result)
    equal(block["counts"],old.counts_for(rebuilt),"memory block totals")
    check(type(block["free_bytes_after"]) is int and block["free_bytes_after"]>=0,"invalid free-space witness")
    rows=old.measured_rows(block,ledger,models)
    legacy.match_starts(rows,ids,edges)
    return old.link(output,str((directory/"block.json").relative_to(output))),rows,block


class Incomplete(ValueError):
    """An independently checked prefix cannot support an experimental selection."""


class Evidence:
    """Consume prerequisites in order; reject every unconsumed file on interruption."""
    def __init__(self,root):
        self.root=root
        self.seen={root}

    def entry(self,path,directory=False):
        check(not path.is_symlink(),"indirect evidence: "+path.name)
        if not path.exists():
            return False
        check(path.is_dir() if directory else path.is_file(),"wrong evidence type: "+path.name)
        self.seen.add(path)
        return True

    def directory(self,path):
        if not self.entry(path,True):
            raise Incomplete("missing directory: "+path.name)

    def model_bytes(self,path,expected):
        if not self.entry(path):
            raise Incomplete("missing artifact: "+path.name)
        actual=path.read_bytes()
        if actual==expected:
            return
        check(len(actual)<len(expected) and expected.startswith(actual),"changed artifact bytes: "+path.name)
        raise Incomplete("unfinished artifact: "+path.name)

    def publication(self,path,expected):
        partial=path.with_suffix(path.suffix+".partial")
        has_partial=self.entry(partial)
        if has_partial:
            try:
                available=legacy.prior.decode_censored_record(partial.read_bytes())
            except EOFError:
                available=None
            if available is not None:
                equal(available,expected,"contradictory partial publication: "+path.name)
        if not self.entry(path):
            raise Incomplete("unpublished receipt: "+path.name)
        equal(read(path),expected,"reconstructed memory receipt: "+path.name)
        if has_partial:
            check(partial.read_bytes()==path.read_bytes(),"conflicting receipt publication: "+path.name)
            raise Incomplete("unfinished publication: "+path.name)

    def tree(self,path):
        self.directory(path)
        for child in sorted(path.iterdir()):
            if child.is_dir() and not child.is_symlink():
                self.tree(child)
            else:
                self.entry(child)

    def finish(self):
        def visit(parent):
            for child in parent.iterdir():
                check(child in self.seen and not child.is_symlink(),"unexpected evidence beyond completed prerequisite: "+str(child.relative_to(self.root)))
                if child.is_dir():
                    visit(child)
        visit(self.root)


def audit_partial_block(output,label,bank,ids,refs,binding,edges,*,evidence=None):
    directory=output/"blocks"/label
    models={name:old.identity(ref) if ref else None for name,ref in refs.items()}
    ledger=old.assignments(label,bank,ids,models,binding)
    names={a["work_dir"] for a in ledger}
    evidence=evidence or Evidence(output)
    def labeled(attempts):
        from .audit_outcome_learning import public_attempt
        return [dict(public_attempt(a,r),verified_controls=r.get("verified_controls",0)) for a,r in zip(ledger,attempts,strict=True)]
    if not directory.exists():
        attempts=[dict(status="unrun") for _ in ledger]
        return dict(counts=old.counts_for(attempts),attempts=labeled(attempts))
    evidence.directory(directory)
    check(directory.is_dir() and not directory.is_symlink(),"indirect partial block")
    children={p.name:p for p in directory.iterdir()}
    check(children.keys() <= names|{"assignments.json","assignments.json.partial","block.json","block.json.partial"},"foreign partial block evidence")
    try:
        evidence.publication(directory/"assignments.json",ledger)
    except Incomplete:
        check(not children.keys()&names,"attempt without complete assignment ledger")
        attempts=[dict(status="unrun") for _ in ledger]
        return dict(counts=old.counts_for(attempts),attempts=labeled(attempts))
    paths={name:check_model(output,ref) if ref else (None,None) for name,ref in refs.items()}
    attempts=[]
    gap=False
    for assignment in ledger:
        work=directory/assignment["work_dir"]
        if not work.exists():
            attempts.append(dict(status="unrun"))
            gap=True
            continue
        check(not gap,"gap in attempt claim prefix")
        evidence.directory(work)
        try:
            evidence.publication(work/"assignment.json",assignment)
        except Incomplete:
            check({p.name for p in work.iterdir()}<={"assignment.json","assignment.json.partial"},"actuation before complete attempt claim")
            result=dict(status="censored",row=None,reason="unfinished_attempt_claim",process=None,reinferred_decisions=0,
                        observed_native_terminal=None,raw={p.name:file_record(p) for p in work.iterdir()})
            attempts.append(result)
            gap=True
            continue
        result=trial.audit_attempt(assignment,work,bank["cases"][assignment["job"]["case"]],*paths[assignment["candidate_id"]],
                                   edge=edges.get(assignment["job"]["target_sector"]))
        evidence.tree(work)
        start=result.get("row") if result["status"]=="complete" else result.get("observed_start")
        if start is not None and edges:
            equal([start[k] for k in ("seed","origin_sha256","target_position")],edges[assignment["job"]["target_sector"]],"partial historical edge")
        attempts.append(result)
    counts=old.counts_for(attempts)
    recorded=None
    for filename in ("block.json","block.json.partial"):
        path=directory/filename
        if path.exists():
            evidence.entry(path)
            try:
                item=legacy.prior.decode_censored_record(path.read_bytes())
            except EOFError:
                check(filename.endswith(".partial"),"truncated complete block receipt")
                continue
            check(isinstance(item,dict) and set(item)=={"assignments_sha256","counts","attempts","free_bytes_after"}
                  and type(item["free_bytes_after"]) is int and item["free_bytes_after"]>=0,"partial block fields")
            expected=dict(assignments_sha256=motor.digest(directory/"assignments.json"),counts=counts,attempts=attempts,
                          free_bytes_after=item["free_bytes_after"])
            equal(item,expected,"partial receipt differs from raw evidence")
            if recorded is not None:
                equal(item,recorded,"conflicting partial block receipt")
            recorded=item
    return dict(counts=counts,attempts=labeled(attempts))


def run_block(output,label,bank,ids,refs,binding,edges,workers):
    check(type(workers) is int and 1<=workers<=2,"memory execution supports at most two workers")
    paths={name:check_model(output,ref) if ref else (None,None) for name,ref in refs.items()}
    models={name:old.identity(ref) if ref else None for name,ref in refs.items()}
    ledger=old.assignments(label,bank,ids,models,binding)
    header=json.loads(legacy.prior.checked_bytes(output/"run.json",binding["run_sha256"]))
    def verify_replay():
        for name in ("replay","map.numeric"):
            equal(file_record(output/"build"/name),header["build"]["files"][name],"retained replay/geometry")
    verify_replay()
    reserve=sum((int(60/a["job"]["control_dt"])+2)*4352+65536 for a in ledger)
    check(shutil.disk_usage(output).free>=reserve,"insufficient disk for declared block")
    def attempt(a,work):
        case=bank["cases"][a["job"]["case"]]
        policy,model=paths[a["candidate_id"]]
        trial.execute(a,work,case,output/"build/replay",output/"build/map.numeric",policy,model)
        return trial.audit_attempt(a,work,case,policy,model,edge=edges[a["job"]["target_sector"]])
    directory=output/"blocks"/label
    block=old.dispatch(directory,ledger,workers,attempt)
    verify_replay()
    rows=old.measured_rows(block,ledger,models)
    legacy.match_starts(rows,ids,edges)
    return old.link(output,str((directory/"block.json").relative_to(output))),rows,block


class Experiment:
    def __init__(self,output,decl,digest,banks,*,audit=False,workers=2):
        check(type(workers) is int and 1<=workers<=2,"memory execution supports one or two workers")
        if not audit:
            check(output.absolute()==RUN_DIRECTORY and output.resolve()==RUN_DIRECTORY,"expected single canonical memory run directory")
        self.output,self.decl,self.digest,self.banks,self.audit,self.workers=output,decl,digest,banks,audit,workers
        self.evidence=Evidence(output) if audit else None
        previous=read(ROOT/"qa/lily-outcome-declaration.json")
        _,self.edges,self.winners=old.history(previous)
        self.models={}
        self.rankings=[]
        self.starts={}
        self.report=dict(schema=1,experiment=EXPERIMENT,run_id=RUN_ID,declaration_sha256=digest,
                         status="inconclusive",models=self.models,blocks={},generations=[],selection=None,criterion=None)

    def record(self,path,value):
        target=self.output/path
        if self.audit:
            self.evidence.publication(target,value)
        else:
            write(target,value)
        return old.link(self.output,path)

    def artifact(self,name,model_bytes,policy_bytes):
        policy,model=model_paths(self.output,name)
        if self.audit:
            self.evidence.directory(model.parent)
            self.evidence.model_bytes(model,model_bytes)
            self.evidence.model_bytes(policy,policy_bytes)
            old.require_inventory(model.parent,set(),{"model.json","policy.py"})
        else:
            old.claim(model.parent)
            model.write_bytes(model_bytes)
            policy.write_bytes(policy_bytes)
        ref=dict(artifact=name,**trial.model_identity(policy,model))
        self.models[name]=ref
        return ref

    def value_artifact(self,name,values):
        return self.artifact(name,memory.canonical(values)+b"\n",memory.policy_source(values).encode())

    def block(self,label,bank,ids,refs,predecessor):
        binding=old.bound(self.binding,predecessor)
        if self.audit:
            directory=self.output/"blocks"/label
            stored=read(directory/"block.json") if (directory/"block.json").is_file() else None
            if stored is None or stored["counts"]["completed"]!=stored["counts"]["assigned"] or any(directory.glob("*.partial")):
                partial=audit_partial_block(self.output,label,bank,ids,refs,binding,self.edges,evidence=self.evidence)
                self.report["blocks"][label]=dict(role=bank["role"],models=deepcopy(refs),**partial)
                raise Incomplete("unfinished block: "+label)
            receipt,rows,block=audit_block(self.output,label,bank,ids,refs,binding,self.edges)
            self.evidence.tree(directory)
        else:
            receipt,rows,block=run_block(self.output,label,bank,ids,refs,binding,self.edges,self.workers)
        from .audit_outcome_learning import public_attempt
        ledger=old.assignments(label,bank,ids,{n:old.identity(r) if r else None for n,r in refs.items()},binding)
        attempts=[dict(public_attempt(a,r),verified_controls=r.get("verified_controls",r.get("reinferred_decisions",0))) for a,r in zip(ledger,block["attempts"],strict=True)]
        self.report["blocks"][label]=dict(role=bank["role"],models=deepcopy(refs),receipt=receipt,counts=block["counts"],attempts=attempts)
        for group in rows.values():
            for row in group:
                witness={k:row[k] for k in legacy.prior.START}
                equal(witness,self.starts.setdefault(row["episode_id"],witness),"different actual starts across blocks")
        if not self.audit:
            print(json.dumps(dict(block=label,**block["counts"])),flush=True)
        return receipt,rows

    def header(self,retained=None):
        if not self.audit:
            check(not self.output.exists() and self.output.absolute()==self.output.resolve()==RUN_DIRECTORY,"run already claimed or noncanonical output")
            check(retained is not None,"retained fixture is required")
            equal(motor.digest(retained/"run.json"),PRIOR_HEADER,"retained input run")
            equal(old.tree_files(retained/"build"),self.decl["previous_header"]["build"]["files"],"retained build input inventory")
            free=shutil.disk_usage(self.output.parent).free
            check(free>=RECIPE["execution"]["initial_free_bytes_min"],"insufficient initial disk")
            old.claim(self.output)
            shutil.copytree(retained/"build",self.output/"build")
            for name in ("models","blocks","rankings"):
                old.claim(self.output/name)
            header=dict(schema=1,run_id=RUN_ID,declaration_sha256=self.digest,implementation_commit=self.decl["implementation_commit"],
                        declaration_commit=subprocess.check_output(["git","-C",str(ROOT),"rev-parse","HEAD"],text=True).strip(),
                        started_at_utc=now(),initial_free_bytes=free,build=self.decl["previous_header"]["build"],
                        fixture_sources=self.decl["fixture_sources"],**old.runtime())
            write(self.output/"run.json",header)
        header=read(self.output/"run.json")
        if self.audit:
            self.evidence.publication(self.output/"run.json",header)
            self.evidence.tree(self.output/"build")
            for name in ("models","blocks","rankings"):
                self.evidence.directory(self.output/name)
        equal([header["schema"],header["run_id"],header["declaration_sha256"],header["implementation_commit"]],
              [1,RUN_ID,self.digest,self.decl["implementation_commit"]],"memory run header")
        equal(sha256(old.git_bytes(header["declaration_commit"],DECLARATION)).hexdigest(),self.digest,"published declaration commit")
        check(legacy.time_utc(header["started_at_utc"])>=legacy.time_utc(self.decl["created_at_utc"]),"run predates declaration")
        equal(header["build"],self.decl["previous_header"]["build"],"same retained build")
        equal(header["fixture_sources"],self.decl["fixture_sources"],"memory fixture source binding")
        equal(old.tree_files(self.output/"build"),header["build"]["files"],"measured retained build bytes")
        check(type(header["initial_free_bytes"]) is int and header["initial_free_bytes"]>=RECIPE["execution"]["initial_free_bytes_min"],"initial disk witness")
        if not self.audit:
            equal({k:header[k] for k in ("python","numpy")},old.runtime(),"changed runtime")
        self.binding=dict(run_id=RUN_ID,declaration_sha256=self.digest,run_sha256=motor.digest(self.output/"run.json"),
                          fixture_source_sha256=header["fixture_sources"]["evaluator"]["native/tests/stock_water_replay/evaluate_motor.py"])
        self.report.update(run_sha256=self.binding["run_sha256"],implementation_commit=header["implementation_commit"],
                           declaration_commit=header["declaration_commit"],runtime={k:header[k] for k in ("python","numpy")})

    def perform(self,retained=None):
        self.header(retained)
        refs={name:self.artifact(name,data["model.json"],data["policy.py"]) for name,data in reference_bytes().items()}
        equal(old.identity(refs["v3"]),self.decl["v3"],"retained v3 bytes")
        equal(old.identity(refs["g4"]),self.decl["g4"],"retained G4 bytes")
        base=read(check_model(self.output,refs["g4"])[1])
        current={name:self.value_artifact("s0" if name=="static" else "r0",search.initial_model(base,mode))
                 for name,mode in (("static","instant"),("recurrent","carried"))}
        bank=self.banks["rehearsal"]
        calibration,baseline=self.block("calibration",bank,bank["ids"],refs,self.binding["run_sha256"])
        historical=prior_results()
        replication={n:check_replication(baseline[n],historical[n]) for n in refs}
        anchors=self.decl["anchors"]
        check(all(r["physical_success"] for r in baseline["v3"] if r["episode_id"] in anchors),"v3 did not reproduce all eight anchor wins")
        calibrated=self.record("calibration.json",dict(**self.binding,block=calibration,references=refs,replicated_prior_starts=replication))
        previous=calibrated["sha256"]
        prior_anchor_rows={}
        for generation,ids in enumerate(self.decl["training_batches"],1):
            prepared={}
            for arm in ("static","recurrent"):
                parent=current[arm]
                policy,model=check_model(self.output,parent)
                candidates=search.candidate_models(read(model),generation,self.digest)
                candidate_refs={}
                for index,c in enumerate(candidates):
                    name=c["candidate_id"]
                    candidate_refs[name]=self.artifact(name,model.read_bytes(),policy.read_bytes()) if index==0 else self.value_artifact(name,c["model"])
                prepared[arm]=(parent,candidates,candidate_refs)
            # Both complete populations exist before either arm observes this generation.
            for arm in ("static","recurrent"):
                parent,candidates,candidate_refs=prepared[arm]
                label=("s" if arm=="static" else "r")+f"-g{generation:02d}"
                receipt,rows=self.block(label,bank,ids,candidate_refs,previous)
                incumbent=rows[candidates[0]["candidate_id"]]
                expected={r["episode_id"]:{k:r[k] for k in ("physical_success","physics_steps","initial_observation_sha256")}
                          for r in (baseline["g4"] if generation==1 else prior_anchor_rows[arm])}
                equal(check_replication(incumbent,expected),16 if generation==1 else 8,"incumbent/zero-residual replication")
                pool=[i for i in ids if "-pool-" in i]
                shaft=[i for i in ids if "-shaft-" in i]
                reference_rows={n:[r for r in baseline[n] if r["episode_id"] in ids] for n in refs}
                result=search.select_generation(candidates,rows,ids,anchors,pool,shaft,reference_rows)
                ranking=dict(arm=arm,generation=generation,parent=parent,models=candidate_refs,block=receipt,**result)
                linked=self.record("rankings/"+label+".json",ranking)
                self.rankings.append(linked)
                self.report["generations"].append(ranking)
                previous=linked["sha256"]
                current[arm]=candidate_refs[result["selected_id"]]
                prior_anchor_rows[arm]=[r for r in rows[result["selected_id"]] if r["episode_id"] in anchors]
        refs.update(current)
        recurrent=read(check_model(self.output,current["recurrent"])[1])
        refs["no_history"]=self.value_artifact("no_history",search.without_history(recurrent))
        training=self.record("training.json",dict(**self.binding,calibration=calibrated,generations=self.rankings,checkpoints=refs))
        bank=self.banks["development"]
        opened,rows=self.block("open",bank,bank["ids"],refs,training["sha256"])
        for name in ("v3","g4"):
            equal(check_replication(rows[name],historical[name]),32,"full open baseline replication")
        pool=[i for i in bank["ids"] if "-pool-" in i]
        shaft=[i for i in bank["ids"] if "-shaft-" in i]
        choice=search.select_open(rows,pool,shaft)
        selection=self.record("selection.json",dict(**self.binding,training=training,block=opened,checkpoints=refs,**choice))
        self.report["selection"]=choice
        selected=choice["selected"]
        freeze=dict(**self.binding,selected=selected,model=refs[selected] if selected else None,selection=selection)
        self.record("freeze.json",freeze)
        self.report["freeze"]=freeze
        self.report["selection"]=choice
        self.report["open_comparisons"]={"memory":memory_comparison(rows,bank["ids"]),
                                         **{n:{family:paired({n:[r for r in rows[n] if r["episode_id"] in ids],
                                                            "v3":[r for r in rows["v3"] if r["episode_id"] in ids]},n,"v3",ids)
                                               for family,ids in (("pool",pool),("shaft",shaft))} for n in ("g4","static","recurrent")}}
        if selected is None:
            self.report.update(status="no_selection",execution_budget=execution_budget(False),transfer_executed=False)
            self.finish(False)
            return self.report
        arms=transfer_arms(freeze,refs)
        bank=self.banks["sealed"]
        transfer,sealed=self.block("sealed",bank,bank["ids"],arms,motor.digest(self.output/"freeze.json"))
        diagnostic={}
        links={"sealed":transfer}
        previous=transfer["sha256"]
        for role in old.DIAGNOSTIC:
            bank=self.banks[role]
            receipt,data=self.block(role,bank,bank["ids"],{"v3":refs["v3"],"selected":refs[selected]},previous)
            links[role],diagnostic[role]=receipt,data
            previous=receipt["sha256"]
        self.record("evaluation.json",dict(**self.binding,freeze=old.link(self.output,"freeze.json"),blocks=links))
        self.report["criterion"]=self.criteria(selected,sealed,diagnostic)
        self.report.update(status="complete",execution_budget=execution_budget(True),transfer_executed=True)
        self.finish(True)
        return self.report

    def criteria(self,selected,sealed,diagnostic):
        ids=self.banks["sealed"]["ids"]
        comparisons={}
        for reference in ("v3","g4"):
            comparisons[reference]={}
            for family in ("pool","shaft"):
                subset=[i for i in ids if "-"+family+"-" in i]
                values={n:[r for r in sealed[n] if r["episode_id"] in subset] for n in (selected,reference)}
                comparisons[reference][family]=paired(values,selected,reference,subset)
        original={n:{r["episode_id"]:r for r in diagnostic["original"][n]} for n in ("v3","selected")}
        historical_reproduced=all(original["v3"][i]["physical_success"] for i in self.winners)
        lost=[i for i in self.winners if not original["selected"][i]["physical_success"]]
        pool,shaft=comparisons["v3"]["pool"],comparisons["v3"]["shaft"]
        return dict(selected=selected,comparisons=comparisons,memory=memory_comparison(sealed,ids),
                    historical_v3_reproduced=historical_reproduced,lost_original_v3_shaft_winners=lost,
                    progress=(pool["net"]>=4 and pool["positions_with_positive_net"]>=3 and shaft["regressions"]==0 and not lost) if historical_reproduced else None)

    def finish(self,selected):
        if self.audit:
            self.evidence.finish()
        root_files={"run.json","calibration.json","training.json","selection.json","freeze.json"}
        if selected:
            root_files.add("evaluation.json")
        old.require_inventory(self.output,{"build","models","blocks","rankings"},root_files)
        old.require_inventory(self.output/"models",set(self.models),set())
        old.require_inventory(self.output/"blocks",set(self.report["blocks"]),set())
        old.require_inventory(self.output/"rankings",set(),{Path(x["path"]).name for x in self.rankings})
        counters={k:0 for k in ("assigned","attempted","completed","wins","failed","censored","invalid","unrun")}
        for block in self.report["blocks"].values():
            for k in counters:
                counters[k]+=block["counts"][k]
        equal(counters["assigned"],execution_budget(selected)["total"],"final fixed execution denominator")
        self.report["counts"]=counters
        self.report["reinferred_decisions"]=sum(a["reinferred_decisions"] for b in self.report["blocks"].values() for a in b["attempts"])
        files=old.tree_files(self.output)
        self.report["retained_files"]=len(files)
        self.report["retained_bytes"]=sum(x["bytes"] for x in files.values())
        self.report["raw_inventory_sha256"]=sha256(memory.json_bytes(files)).hexdigest()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage",choices=("declare","run"))
    parser.add_argument("--declaration",type=Path,default=ROOT/DECLARATION)
    parser.add_argument("--output",type=Path)
    parser.add_argument("--retained",type=Path,required=True)
    parser.add_argument("--source-commit")
    parser.add_argument("--workers",type=int,default=2)
    args=parser.parse_args(argv)
    try:
        if args.stage=="declare":
            check(args.source_commit is not None,"declaration needs canonical source commit")
            write(args.declaration,make_declaration(args.source_commit,args.retained))
            print(json.dumps(file_record(args.declaration)))
        else:
            check(args.output is not None and type(args.workers) is int and 1<=args.workers<=2,"run needs output and one or two workers")
            decl,digest,banks=declaration(args.declaration)
            result=Experiment(args.output,decl,digest,banks,workers=args.workers).perform(args.retained)
            print(json.dumps({k:result[k] for k in ("status","counts","selection")}),flush=True)
    except (OSError,ValueError,KeyError,subprocess.SubprocessError) as exc:
        parser.exit(1,type(exc).__name__+": "+str(exc)+"\n")
    return 0


if __name__=="__main__":
    raise SystemExit(main())

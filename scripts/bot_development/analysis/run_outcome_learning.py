"""Execute the predeclared, no-retry stock-water head search in three gated stages."""
import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import csv
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

import numpy as np

from bots.lily import outcome_search as search
from . import outcome_build_inputs as inputs
from . import outcome_rollouts as trial
from .outcome_rollouts import ROOT, check, contact, equal, file_record, motor, now, read, write

RUN_ID = "lily-outcome-learning-20261122-01"
NEW = ("train", "development", "sealed")
DIAGNOSTIC = ("original", "stress", "recovery")
PATHS = {**{role:f"qa/lily-outcome/{role}.tsv" for role in NEW},
         "original":"native/tests/stock_water_replay/bank_cases.tsv", "stress":"qa/lily-motor-stress-cases.tsv",
         "recovery":"qa/lily-recovery-fresh-cases.tsv"}
COUNTS = dict(train=64, development=32, sealed=48, original=27, stress=16, recovery=24)
FREE = 2684354560
ALG = "scripts/bot_development/analysis/"
REQUIRED_SOURCES = {ALG+name+".py" for name in ("outcome_build_inputs","outcome_rollouts","run_outcome_learning","audit_outcome_learning",
                    "audit_recovery_learning","declare_outcome_poses","validate_replay_poses")} | {
                    "bots/lily/"+name+".py" for name in ("outcome_search","motor_contact","motor_model")}
RECIPE = {
    "search": dict(method="elitist-antithetic-output-head-search", generations=8, directions=6, batch_size=8,
                   seed=41023, schedule_seed=31023, head_shape=[6,33], axis_scale=.18, button_scale=.65,
                   half_scale_from_generation=5, normalizer_divisor=33, train_executions=832),
    "development": dict(policies=["v3","g4","g8"], executions=96, preserve_v3_shaft_successes=True,
                        strict_pool_improvement=True, tie_order=["g4","g8"], stop_without_selection=True),
    "evaluation": dict(sealed_policies=["v3","selected","native"], sealed_executions=144,
                       diagnostic_policies=["v3","selected"], diagnostic_executions=134, no_second_selection=True),
    "progress_criterion": dict(sealed_net_additional_pool_landings_minimum=4, sealed_pool_positions_with_positive_net_minimum=3,
                               lost_sealed_v3_shaft_wins_maximum=0, lost_original_v3_shaft_wins_maximum=0,
                               expected_original_v3_shaft_wins=24),
    "execution": dict(physics_hz=150, max_physics_steps=9000, required_dry_steps=38, controller="every_tick",
                      hold_ticks=1, teacher_control=False, retries=0, max_workers=4, minimum_initial_free_bytes=FREE)}
PARENT = dict(model="bots/lily/models/water_recovery_v3.json", policy="bots/lily/policies/water_recovery_v3.py",
              model_sha256=search.V3_FILE_SHA256, canonical_sha256=search.V3_CANONICAL_SHA256,
              policy_sha256=search.V3_EXPORT_SHA256)
PRIOR_FILES = {"historical_edges":("qa/lily-independent-motor.json",trial.prior.HISTORY_SHA),
               "historical_recovery":("qa/lily-recovery-evaluation.json","3c9ac2887e7d2a00736f5656280cb76be5009bb59f6f9b65506533812022a263")}
SPEC = "docs/superpowers/specs/2026-11-22-lily-outcome-learning-design.md"


class BlockStopped(ValueError):
    """Attempt evidence was retained, but the stage cannot advance."""


def claim(path):
    path.mkdir(mode=0o700)


def require_inventory(directory, directories, files):
    """A completed predecessor must have exactly its declared direct children."""
    check(directory.is_dir() and not directory.is_symlink(), f"missing or indirect inventory: {directory.name}")
    actual = {p.name:p for p in directory.iterdir()}
    check(actual.keys() == directories | files
          and all(not p.is_symlink() and (p.is_dir() if name in directories else p.is_file())
                  for name,p in actual.items()), f"ambiguous evidence inventory: {directory.name}")


def stage_inventory(output, stage):
    folders = {"build", "models", "train"}
    files = {"run.json", "training.json"}
    if stage == "evaluate":
        folders.add("select")
        files.update(("selection.json", "freeze.json"))
    require_inventory(output, folders, files)
    artifacts = {"v3", *(f"g{g:02d}-c{i:02d}" for g in range(1,9) for i in range(13))}
    require_inventory(output/"models", artifacts, set())
    for artifact in artifacts:
        require_inventory(output/"models"/artifact, set(), {"model.json","policy.py"})
    require_inventory(output/"train", {f"g{n:02d}" for n in range(1,9)}, set())
    if stage == "evaluate":
        require_inventory(output/"select", {"development"}, set())


def canonical_output(run_id, output):
    equal(run_id, RUN_ID, "declared run ID")
    expected = Path("/dev/shm")/run_id
    check(output.absolute() == expected and output.resolve() == expected, "expected canonical /dev/shm run directory")
    return expected


def checked_input(entry, path):
    equal(entry["path"], path, "declared source/role path")
    return trial.prior.checked_bytes(ROOT/path, entry["sha256"])


def load_bank(role, entry):
    rows = list(csv.DictReader(checked_input(entry, PATHS[role]).decode().splitlines(), delimiter="\t"))
    jobs = motor.make_jobs(rows, ["every_tick", "baseline"], role == "original")
    ids = [job["episode_id"] for job in jobs if job["controller"] == "every_tick"]
    equal(ids, entry["episode_ids"], "case role/assignment order")
    equal(len(ids), COUNTS[role], "case assignment count")
    cases = {row["case"]:row for row in rows}
    check(len(cases) == len(rows), "duplicate pose group")
    if role in NEW:
        equal(len(cases), entry["groups"], "pose groups")
        for row in rows:
            family = {"10":"pool","41":"shaft"}[row["dry"]]
            check(re.fullmatch(f"outcome-{role}-{family}-[0-9]{{2}}", row["case"]), "wrong pose role")
            equal(row["yaw_offsets"], "-45,45,135,-135" if role=="sealed" else "-90,0,90,180", "yaw bank")
        geom_path = f"qa/lily-outcome/{role}-geometry.json"
        equal(entry["geometry_path"], geom_path, "geometry role")
        geom = json.loads(trial.prior.checked_bytes(ROOT/geom_path, entry["geometry_sha256"]))
        equal([geom["cases_sha256"],geom["all_spheres_inside"],geom["yaw_trials"],geom["pose_groups"]],
              [entry["sha256"],True,COUNTS[role],entry["groups"]], "geometry evidence")
    return dict(role=role, sha256=entry["sha256"], cases=cases, ids=ids,
                jobs={(j["episode_id"],j["controller"]):j for j in jobs})


def git_bytes(commit, name):
    return subprocess.check_output(["git", "-C", str(ROOT), "show", f"{commit}:{name}"])


def declaration(path):
    data = path.read_bytes()
    check(data == git_bytes("HEAD", "qa/lily-outcome-declaration.json"), "unpublished or changed declaration")
    decl = json.loads(data)
    equal([decl["schema"],decl["experiment"],decl["run_id"]], [1,"lily-outcome-head-v4",RUN_ID], "experiment identity")
    for name, expected in RECIPE.items():
        equal(decl[name], expected, "fixed "+name+" recipe")
    equal(decl["parent"], PARENT, "v3 identity")
    equal(trial.model_identity(ROOT/PARENT["policy"], ROOT/PARENT["model"]), identity(PARENT), "v3 measured bytes")
    trial.time_utc(decl["created_at_utc"])
    commit = decl["implementation_commit"]
    check(isinstance(commit,str) and re.fullmatch(r"[0-9a-f]{40}",commit), "missing implementation freeze")
    frozen = decl["frozen_files_sha256"]
    check(REQUIRED_SOURCES <= frozen.keys(), "incomplete frozen sources")
    for name, digest in frozen.items():
        check(not Path(name).is_absolute() and ".." not in Path(name).parts, "invalid frozen path")
        trial.prior.checked_bytes(ROOT/name, digest)
        committed = git_bytes(commit, name)
        equal(trial.prior.sha(committed), digest, "implementation commit binding: " + name)
    checked_input(decl["spec"], SPEC)
    allocation = json.loads(checked_input(decl["geometry_allocation"], "qa/lily-outcome/spacing-and-allocation.json"))
    equal(allocation["generator_sha256"], frozen[ALG+"declare_outcome_poses.py"], "pose generator")
    check(set(decl["cases"]) == set(NEW) and set(decl["diagnostics"]) == set(DIAGNOSTIC), "case role membership")
    banks = {role:load_bank(role, s) for role,s in (decl["cases"]|decl["diagnostics"]).items()}
    all_ids = [i for b in banks.values() for i in b["ids"]]
    check(len(set(all_ids)) == len(all_ids), "overlapping assignment IDs")
    ids = banks["train"]["ids"]
    rng = np.random.Generator(np.random.PCG64(31023))
    pool, shaft = [list(rng.permutation([i for i in ids if family in i])) for family in ("-pool-", "-shaft-")]
    equal(decl["training_batches"], [pool[6*g:6*g+6]+shaft[2*g:2*g+2] for g in range(8)], "training schedule")
    for label, (filename, digest) in PRIOR_FILES.items():
        equal(decl[label]["sha256"], digest, "historical receipt")
        checked_input(decl[label], filename)
    equal(decl["historical_edges"]["experiment"], "contact_original", "stock edge experiment")
    freeze = json.loads(trial.prior.checked_bytes(trial.prior.FREEZE, trial.prior.FREEZE_SHA))
    equal(decl["fixture_reference"], freeze["fixture_provenance"], "historical fixture reference")
    inputs.declared(decl)
    return decl, trial.prior.sha(data), banks


def identity(ref):
    return {k:ref[k] for k in ("model_sha256","canonical_sha256","policy_sha256")}


def model_paths(output, artifact):
    check(re.fullmatch(r"v3|g0[1-8]-c(?:0[0-9]|1[0-2])", artifact), "invalid model artifact")
    directory = output/"models"/artifact
    return directory/"policy.py", directory/"model.json"


def retain_model(output, name, parent=None, values=None):
    policy, model = model_paths(output, name)
    claim(model.parent)
    if values is None:
        old_policy, old_model = parent
        shutil.copyfile(old_model, model)
        shutil.copyfile(old_policy, policy)
    else:
        model.write_bytes(contact.canonical(values)+b"\n")
        policy.write_text(contact.policy_source(values))
    return dict(artifact=name, **trial.model_identity(policy, model))


def history(decl):
    hist = read(ROOT/decl["historical_edges"]["path"])["experiments"]["contact_original"]
    edges = {}
    for row in hist["episodes"]:
        data = [row[k] for k in ("seed","origin_sha256","target_position")]
        equal(data, edges.setdefault(row["target_sector"], data), "historical stock edge")
    check(set(edges) == {10,41}, "stock edges")
    paired = read(ROOT/decl["historical_recovery"]["path"])["paired_assignments"]["original"]
    winners = [r["episode_id"] for r in paired if r["matched_complete"] and
               r["actual_start"]["target_sector"] == 41 and r["outcomes"]["v3"] is True]
    check(len(winners) == len(set(winners)) == 24, "historical v3 shaft winners")
    return hist, edges, winners


def fixture_sources(decl):
    sources = trial.prior.collect_recovery.fixture_manifest()
    equal(sources, decl["fixture_reference"]["fixture_source_sha256"], "explicit recovery fixture inventory")
    expected = dict(sources)
    del expected["bots/map_audit.py"]
    live = "native/tests/stock_water_replay/live_policy.py"
    hist = read(ROOT/decl["historical_edges"]["path"])["experiments"]["contact_original"]
    expected[live] = hist["provenance"]["fixture_source_sha256"][live]
    here = trial.prior.FIXTURE
    files = [p for pattern in ("*.inc","*.h","*.c","*.py") for p in here.glob(pattern)]
    files += [here.parent/"test_bot_portal_collision.c", ROOT/"bots/lily/protocol.py"]
    current = {str(p.relative_to(ROOT)):motor.digest(p) for p in files}
    equal(current, expected, "original evaluator glob inventory")
    return dict(recovery=sources, evaluator=current)


def tree_files(path):
    files = {}
    for item in sorted(path.rglob("*")):
        check(not item.is_symlink(), "indirect build file")
        if not item.is_dir():
            files[str(item.relative_to(path))] = file_record(item)
    return files


def make_build(output, source, build, map_path, decl):
    work = output/"build"
    claim(work)
    flags = build/"CMakeFiles/sith_engine.dir/flags.make"
    shutil.copyfile(flags, work/"flags.make")
    equal(motor.digest(work/"flags.make"), decl["fixture_reference"]["compiler_flags_sha256"], "declared compiler flags")
    inputs.retain(inputs.declared(decl), work, source, build)
    with inputs.compiler_dependencies() as deps:
        executable, geom, provenance = motor.build_replay(work/"source", build, map_path, work, independent_motor=True)
        inputs.verify_compilation(deps, work, build, decl)
    equal(motor.digest(flags), motor.digest(work/"flags.make"), "compiler flags changed during build")
    provenance.update(geometry_sha256=motor.digest(geom), compiler_flags_sha256=motor.digest(work/"flags.make"))
    trial.prior.collect_recovery.verify_engine(provenance, decl["fixture_reference"])
    equal(motor.digest(executable), provenance["executable_sha256"], "as-built replay")
    compiler = shutil.which(os.environ.get("CC","cc"))
    check(compiler is not None, "missing compiler identity")
    return dict(provenance=provenance, files=tree_files(work),
                compiler=dict(path=compiler, sha256=motor.digest(Path(compiler)),
                              version=subprocess.check_output([compiler,"--version"],text=True).strip()))


def runtime():
    return dict(python=dict(version=sys.version, implementation=platform.python_implementation(),
                            executable=sys.executable, sha256=motor.digest(Path(sys.executable))),
                numpy=np.__version__)


def verify_build_files(output, build, decl):
    files = tree_files(output/"build")
    equal(files, build["files"], "retained build file inventory")
    provenance = build["provenance"]
    trial.prior.collect_recovery.verify_engine(provenance, decl["fixture_reference"])
    expected = dict(inputs.declared(decl))
    for name, key in (("replay","executable_sha256"), ("map.numeric","geometry_sha256"), ("flags.make","compiler_flags_sha256")):
        expected[name] = provenance[key]
    check(set(files) == set(expected) | inputs.GENERATED, "declared build inventory")
    for name, digest in expected.items():
        equal(files[name]["sha256"], digest, "retained build input "+name)


def verify_header(output, decl, digest):
    hdr = read(output/"run.json")
    equal([hdr["run_id"],hdr["declaration_sha256"],hdr["implementation_commit"]],
          [RUN_ID,digest,decl["implementation_commit"]], "run header")
    equal(hdr["fixture_sources"], fixture_sources(decl), "run fixture binding")
    equal({k:hdr[k] for k in ("python","numpy")}, runtime(), "changed experiment runtime")
    build = hdr["build"]
    verify_build_files(output, build, decl)
    return hdr


def assignments(label, bank, ids, models, binding):
    check(len(set(ids)) == len(ids), "duplicate block assignments")
    return [dict(binding, block=label, role=bank["role"], cases_sha256=bank["sha256"],
                 candidate_id=name, model=model, job=bank["jobs"][episode,"baseline" if name=="native" else "every_tick"],
                 work_dir=name+"--"+episode)
            for name, model in models.items() for episode in ids]


def counts_for(results):
    complete = [a["row"] for a in results if a["status"] == "complete"]
    unrun = sum(a["status"] == "unrun" for a in results)
    return dict(assigned=len(results), attempted=len(results)-unrun, completed=len(complete),
                wins=sum(a["physical_success"] is True for a in complete),
                failed=sum(a["physical_success"] is False for a in complete),
                censored=sum(a["status"] == "censored" for a in results),
                invalid=sum(a["status"] == "invalid" for a in results), unrun=unrun)


def dispatch(directory, ledger, workers, attempt):
    """Bound outstanding work; a censored or invalid attempt closes admission."""
    check(1 <= workers <= 4 and ledger, "invalid worker count or empty block")
    names = [a["work_dir"] for a in ledger]
    check(len(set(names)) == len(names) and all(re.fullmatch(r"[a-zA-Z0-9_.-]+",n) and n not in (".","..")
                                                for n in names), "invalid attempt directory")
    claim(directory)
    write(directory/"assignments.json", ledger)
    results = [dict(status="unrun") for _ in ledger]
    pending = {}
    index, stopped = 0, False
    with ThreadPoolExecutor(max_workers=workers) as pool:
        while pending or (index < len(ledger) and not stopped):
            while len(pending) < workers and index < len(ledger) and not stopped:
                assignment = ledger[index]
                work = directory/assignment["work_dir"]
                claim(work)
                write(work/"assignment.json", assignment)
                pending[pool.submit(attempt, assignment, work)] = index
                index += 1
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                i = pending.pop(future)
                try:
                    result = future.result()
                    check(result["status"] in ("complete","censored"), "unknown audit status")
                except Exception as exc:
                    # Invalid evidence is retained and distinguished from an infrastructure censor.
                    work = directory/ledger[i]["work_dir"]
                    result = dict(status="invalid", error=type(exc).__name__, detail=str(exc),
                                  raw={p.name:file_record(p) for p in work.iterdir() if p.is_file() and not p.is_symlink()})
                results[i] = result
                stopped |= result["status"] != "complete"
    counts = counts_for(results)
    # A failure in execute's final publication can raise before audit_attempt.
    # The actual files still decide whether the block receipt may be published.
    if any(r.get("reason") in ("unpublished_process_witness","missing_process_witness")
           or ("raw" in r and ("process.json" not in r["raw"] or "process.json.partial" in r["raw"]))
           for r in results):
        raise BlockStopped(f"{directory.name}: unfinished process publication: {counts}")
    block = dict(assignments_sha256=motor.digest(directory/"assignments.json"), counts=counts, attempts=results,
                 free_bytes_after=shutil.disk_usage(directory).free)
    write(directory/"block.json", block)
    if stopped:
        raise BlockStopped(f"{directory.name}: incomplete block: {counts}")
    return block


def check_model(output, ref):
    policy, model = model_paths(output, ref["artifact"])
    equal(trial.model_identity(policy, model), identity(ref), "measured artifact binding")
    return policy, model


def measured_rows(block, ledger, models):
    equal(len(block["attempts"]), len(ledger), "complete block denominator")
    rows = {name:[] for name in models}
    for a, outcome in zip(ledger, block["attempts"], strict=True):
        equal(outcome["status"], "complete", "required complete block")
        row = outcome["row"]
        equal({k:row[k] for k in a["job"]}, a["job"], "result assignment")
        rows[a["candidate_id"]].append(row)
    return rows


def run_block(output, stage, label, bank, ids, refs, binding, edges, workers):
    """Bind artifacts and historical edge before exposing audited rows to a selector."""
    header = json.loads(trial.prior.checked_bytes(output/"run.json", binding["run_sha256"]))
    provenance = header["build"]["provenance"]
    def verify_replay():
        for name, key in (("replay", "executable_sha256"), ("map.numeric", "geometry_sha256")):
            equal(file_record(output/"build"/name)["sha256"], provenance[key], "block replay/geometry binding")
    verify_replay()
    paths = {name:check_model(output,ref) if ref else (None,None) for name,ref in refs.items()}
    models = {name:identity(ref) if ref else None for name,ref in refs.items()}
    ledger = assignments(label, bank, ids, models, binding)
    directory = output/stage/label
    # The engine permits 2 KiB per observation. Reserve additional room for both
    # control traces, decision journal, attempt metadata and block receipt.
    reserve = sum((int(60/a["job"]["control_dt"])+2)*4096 + 65536 for a in ledger)
    check(shutil.disk_usage(output).free >= reserve, "insufficient free space for next declared block")

    def attempt(a, work):
        policy, model = paths[a["candidate_id"]]
        case = bank["cases"][a["job"]["case"]]
        trial.execute(a, work, case, output/"build/replay", output/"build/map.numeric", policy, model)
        return trial.audit_attempt(a, work, case, policy, model)

    block = dispatch(directory, ledger, workers, attempt)
    verify_replay()
    rows = measured_rows(block, ledger, models)
    trial.match_starts(rows, ids, edges)
    return {"path":str((directory/"block.json").relative_to(output)), "sha256":motor.digest(directory/"block.json")}, rows


def link(output, rel):
    return dict(path=rel, sha256=motor.digest(output/rel))


def open_block(output, stage, label, bank, ids, refs, binding, edges):
    """Verify saved assignment/order, scores' source rows and paired-start evidence at stage boundaries."""
    directory = output/stage/label
    models = {name:identity(ref) if ref else None for name,ref in refs.items()}
    ledger = assignments(label, bank, ids, models, binding)
    receipts = {"assignments.json","block.json"}
    if stage == "train":
        receipts.add("ranking.json")
    require_inventory(directory, {a["work_dir"] for a in ledger}, receipts)
    equal(read(directory/"assignments.json"), ledger, "saved assignment ledger")
    block = read(directory/"block.json")
    equal(block["assignments_sha256"], motor.digest(directory/"assignments.json"), "saved ledger digest")
    rows = measured_rows(block, ledger, models)
    paths = {name:check_model(output, ref) if ref else (None, None) for name,ref in refs.items()}
    for a, recorded in zip(ledger, block["attempts"], strict=True):
        work = directory/a["work_dir"]
        case = bank["cases"][a["job"]["case"]]
        rebuilt = trial.audit_attempt(a, work, case, *paths[a["candidate_id"]])
        equal(recorded, rebuilt, "saved attempt disagrees with raw evidence")
    equal(block["counts"], counts_for(block["attempts"]), "saved block counts")
    trial.match_starts(rows, ids, edges)
    return link(output,str((directory/"block.json").relative_to(output))), rows


def bound(header_binding, predecessor):
    return dict(header_binding, predecessor_sha256=predecessor)


def generation(output, gen, current, bank, ids, binding, edges, workers, *, reconstruct=False):
    label = f"g{gen:02d}"
    parent = check_model(output, current)
    candidates = search.candidate_models(read(parent[1]), gen, binding["declaration_sha256"])
    refs = {}
    for i,c in enumerate(candidates):
        name = c["candidate_id"]
        if reconstruct:
            policy, model = model_paths(output, name)
            expected = contact.canonical(c["model"])+b"\n" if i else parent[1].read_bytes()
            check(model.read_bytes() == expected, "saved candidate bytes or lineage")
            refs[name] = dict(artifact=name, **trial.model_identity(policy,model))
        else:
            refs[name] = retain_model(output,name, parent=parent, values=c["model"] if i else None)
    if reconstruct:
        block, rows = open_block(output,"train",label,bank,ids,refs,binding,edges)
    else:
        block, rows = run_block(output,"train",label,bank,ids,refs,binding,edges,workers)
    result = search.select_generation(candidates, rows, ids)
    result["scores"] = {k:list(v) for k,v in result["scores"].items()}
    ranking = dict(block=block, parent=current, candidates=refs, **result)
    rank_path = "train/"+label+"/ranking.json"
    if reconstruct:
        equal(read(output/rank_path), ranking, "saved generation ranking")
    else:
        write(output/rank_path, ranking)
    return link(output,rank_path), refs[result["selected_id"]]


def train_generations(output, decl, banks, binding, edges, workers, *, reconstruct=False):
    if reconstruct:
        current = dict(artifact="v3", **identity(PARENT))
        check_model(output, current)
    else:
        current = retain_model(output, "v3", parent=(ROOT/PARENT["policy"],ROOT/PARENT["model"]))
        equal(identity(current), identity(PARENT), "retained v3")
    checkpoints = {"v3":current}
    previous = binding["run_sha256"]
    rankings = []
    for gen, ids in enumerate(decl["training_batches"], 1):
        ranking, current = generation(output,gen,current,banks["train"],ids,bound(binding,previous),edges,workers,
                                      reconstruct=reconstruct)
        rankings.append(ranking)
        previous = ranking["sha256"]
        if gen in (4,8):
            checkpoints["g"+str(gen)] = current
    result = dict(**binding, generations=rankings, checkpoints=checkpoints)
    if reconstruct:
        equal(read(output/"training.json"), result, "training receipt")
    else:
        write(output/"training.json", result)
    return result


def development(output, bank, binding, edges, checkpoints, workers, *, reconstruct=False):
    path = output/"selection.json"
    training = link(output,"training.json")
    parent = bound(binding, training["sha256"])
    ids = bank["ids"]
    if reconstruct:
        block, rows = open_block(output,"select","development",bank,ids,checkpoints,parent,edges)
    else:
        block, rows = run_block(output,"select","development",bank,ids,checkpoints,parent,edges,workers)
    pool = [i for i in ids if bank["jobs"][i,"every_tick"]["target_sector"] == 10]
    shaft = [i for i in ids if bank["jobs"][i,"every_tick"]["target_sector"] == 41]
    decision = search.select_development(rows, pool, shaft)
    selection = dict(**binding, block=block, training=training, checkpoints=checkpoints, **decision)
    selected = decision["selected"]
    if reconstruct:
        equal(read(path), selection, "saved development selection")
    else:
        write(path,selection)
    model = checkpoints[selected] if selected else None
    freeze = dict(**binding, selected=selected, model=model, selection=link(output,"selection.json"))
    if reconstruct:
        saved = read(output/"freeze.json")
        trial.time_utc(saved["frozen_at_utc"])
        equal(saved, dict(freeze,frozen_at_utc=saved["frozen_at_utc"]), "selected freeze")
        return saved
    freeze["frozen_at_utc"] = now()
    write(output/"freeze.json",freeze)
    return freeze


def evaluate_blocks(output, banks, context, freeze, opener):
    check(freeze["selected"] in ("g4","g8") and freeze["model"] is not None, "no selected measured checkpoint")
    binding, edges, winners, workers = (context[k] for k in ("binding","edges","winners","workers"))
    claim(output/"evaluate")
    previous = motor.digest(output/"freeze.json")
    blocks = {}
    base = {"v3":dict(artifact="v3", **identity(PARENT)), "selected":freeze["model"]}
    for role in ("sealed", *DIAGNOSTIC):
        bank = banks[role]
        arms = dict(base, native=None) if role=="sealed" else base
        block, _ = opener(output, "evaluate", role, bank, bank["ids"], arms, bound(binding,previous),edges,workers)
        blocks[role] = block
        previous = block["sha256"]
    write(output/"evaluation.json",dict(**binding, freeze=link(output,"freeze.json"), blocks=blocks,
                                        historical_v3_original_shaft_winners=winners))


def run(stage, path, output, workers, source=None, build=None, map_path=None):
    check(type(workers) is int and 1 <= workers <= 4, "expected 1 to 4 workers")
    check(stage in ("train","select","evaluate"), "invalid stage")
    output = canonical_output(RUN_ID, output)
    check(not (output/stage).exists(), "stage already claimed; no retry or resume")
    if stage == "train":
        check(all(p is not None for p in (source,build,map_path)), "train requires --source, --build and --map")
        check(not output.exists(), "run already claimed; no retry or resume")
    else:
        check(all(p is None for p in (source,build,map_path)), "build arguments are train-only")
        stage_inventory(output, stage)
    decl, digest, banks = declaration(path)
    _, edges, winners = history(decl)
    if stage == "train":
        free = shutil.disk_usage(output.parent).free
        check(free >= FREE, "insufficient initial free space (2.5 GiB required)")
        sources = fixture_sources(decl)
        started = now()
        claim(output)
        claim(output/"train")
        claim(output/"models")
        raw_build = make_build(output,source.resolve(),build.resolve(),map_path.resolve(),decl)
        write(output/"run.json",dict(schema=1, run_id=RUN_ID, declaration_sha256=digest,
                                     implementation_commit=decl["implementation_commit"], started_at_utc=started,
                                     initial_free_bytes=free, fixture_sources=sources, build=raw_build,
                                     **runtime()))
    hdr = verify_header(output,decl,digest)
    binding = dict(run_id=RUN_ID, declaration_sha256=digest, run_sha256=motor.digest(output/"run.json"),
                   fixture_source_sha256=hdr["fixture_sources"]["evaluator"][
                       "native/tests/stock_water_replay/evaluate_motor.py"])
    training = train_generations(output,decl,banks,binding,edges,workers,reconstruct=stage!="train")
    if stage == "train":
        return
    if stage == "select":
        claim(output/"select")
    freeze = development(output,banks["development"],binding,edges,training["checkpoints"],workers,reconstruct=stage=="evaluate")
    if stage == "evaluate":
        evaluate_blocks(output,banks,dict(binding=binding,edges=edges,winners=winners,workers=workers),freeze,run_block)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("train","select","evaluate"))
    parser.add_argument("--declaration", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    for key in ("source","build","map"):
        parser.add_argument("--"+key, type=Path)
    args = parser.parse_args(argv)
    try:
        run(args.stage,args.declaration,args.output,args.workers,args.source,args.build,args.map)
    except (OSError,ValueError,KeyError,subprocess.SubprocessError) as exc:
        parser.exit(1, str(exc)+"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

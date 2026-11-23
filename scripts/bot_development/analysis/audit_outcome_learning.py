"""Reconstruct Lily's declared outcome experiment from retained bytes, without a rollout."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re
import shutil
import subprocess

from . import run_outcome_learning as run
from .outcome_rollouts import check, contact, equal, file_record, read
from . import outcome_rollouts as trial
from bots.lily import outcome_search as search
from run import stock_functions  # Pinned fixture module loaded by outcome_rollouts.


class Unfinished(Exception):
    """An expected publication or stage was never completed."""


def unique_fields(pairs):
    obj = dict(pairs)
    check(len(obj) == len(pairs), "duplicate JSON receipt field")
    return obj


class Inventory:
    """Consume evidence in prerequisite order, then reject any unconsumed subtree."""

    def __init__(self, root):
        self.root = root
        self.seen = {root}
        self.pending_publication = None

    def stable(self):
        if self.pending_publication is not None:
            raise Unfinished(f"unfinished publication {self.pending_publication.relative_to(self.root)}")

    def entry(self, path, directory=False):
        self.stable()
        check(not path.is_symlink(), f"indirect evidence inventory: {path.name}")
        if not path.exists():
            return False
        check(path.is_dir() if directory else path.is_file(), f"wrong evidence inventory type: {path.name}")
        self.seen.add(path)
        return True

    def directory(self, path):
        if not self.entry(path, True):
            raise Unfinished(f"missing {path.relative_to(self.root)}")

    def publication(self, path):
        sidecar = path.with_suffix(path.suffix + ".partial")
        partial = self.entry(sidecar)
        if not self.entry(path):
            raise Unfinished(f"unpublished {path.relative_to(self.root)}")
        if partial:
            check(sidecar.read_bytes() == path.read_bytes(), f"conflicting partial receipt: {path.name}")
            self.pending_publication = path
        return json.loads(path.read_bytes(), object_pairs_hook=unique_fields)

    def finish(self):
        def visit(parent):
            for child in parent.iterdir():
                check(child in self.seen and not child.is_symlink(),
                      f"unexpected evidence inventory: {child.relative_to(self.root)}")
                if child.is_dir():
                    visit(child)
        visit(self.root)


def portable_header(root, decl, digest):
    """Verify the measured build and frozen sources, recording the original runtime."""
    hdr = read(root/"run.json")
    check(set(hdr) == {"schema","run_id","declaration_sha256","implementation_commit","started_at_utc",
                       "initial_free_bytes","fixture_sources","build","python","numpy"}, "run header schema")
    equal([hdr["schema"], hdr["run_id"], hdr["declaration_sha256"], hdr["implementation_commit"]],
          [1, run.RUN_ID, digest, decl["implementation_commit"]], "run header identity")
    check(trial.time_utc(hdr["started_at_utc"]) >= trial.time_utc(decl["created_at_utc"]), "run predates declaration")
    check(type(hdr["initial_free_bytes"]) is int and hdr["initial_free_bytes"] >= run.FREE, "initial disk budget")
    equal(hdr["fixture_sources"], run.fixture_sources(decl), "run fixture inventory")
    python, build = hdr["python"], hdr["build"]
    compiler = build["compiler"]
    check(set(build) == {"provenance","compiler","files"} and set(compiler) == {"path","sha256","version"}
          and set(python) == {"version","implementation","executable","sha256"}, "build/runtime schema")
    for obj, fields in ((python, ("implementation", "executable", "version")), (compiler, ("path", "version"))):
        check(all(isinstance(obj[k], str) and obj[k] for k in fields)
              and re.fullmatch("[a-f0-9]{64}", obj["sha256"]), "invalid recorded runtime/toolchain")
    check(isinstance(hdr["numpy"], str) and hdr["numpy"], "missing recorded NumPy version")
    provenance = build["provenance"]
    check(set(provenance) == {*trial.prior.collect_recovery.ENGINE_IDENTITIES,"executable_sha256"},
          "measured fixture provenance schema")
    run.verify_build_files(root, build, decl)
    # These includes are emitted deterministically by the pinned stock builder.
    check((root/"build/stock_functions.inc").read_bytes() == stock_functions(root/"build/source").encode(),
          "stock functions include")
    check((root/"build/AI/jkBotLily.inc").read_bytes() ==
          b'#include_next "AI/jkBotLily.inc"\n#include "bank_drive.inc"\n', "fixture control include")
    return hdr


def model_ref(inv, name, model_bytes, policy_bytes):
    policy, model = run.model_paths(inv.root, name)
    inv.directory(model.parent)
    # retain_model writes model then policy. Only the final unpublished file can
    # be incomplete, and it must be a prefix of the actual expected bytes.
    for path, expected in ((model, model_bytes), (policy, policy_bytes)):
        if not inv.entry(path):
            raise Unfinished(f"missing model artifact {name}/{path.name}")
        actual = path.read_bytes()
        if actual != expected:
            check(len(actual) < len(expected) and expected.startswith(actual), f"changed model bytes: {name}/{path.name}")
            raise Unfinished(f"partial model artifact {name}/{path.name}")
    return dict(artifact=name, model_sha256=trial.prior.sha(model_bytes),
                canonical_sha256=trial.prior.sha(contact.canonical(read(model))),
                policy_sha256=trial.prior.sha(policy_bytes))


def transitions(pairs):
    labels = {(False, True):"gain", (True, False):"regression", (True, True):"both", (False, False):"neither"}
    episodes = {v:[] for v in labels.values()}
    positions = {}
    for p in pairs:
        label = labels[p["v3"], p["selected"]]
        episodes[label].append(p["episode_id"])
        group = positions.setdefault(p["case"], dict.fromkeys(episodes, 0))
        group[label] += 1
    for group in positions.values():
        group["net"] = group["gain"] - group["regression"]
    return dict(counts={k:len(v) for k,v in episodes.items()}, episodes=episodes, by_position=positions)


def transfer(pairs, winners):
    """Score a fully audited evaluation. Duplicates or missing coverage cannot yield a criterion."""
    check(set(pairs) == {"sealed", *run.DIAGNOSTIC}, "evaluation roles")
    for role, rows in pairs.items():
        equal(len(rows), run.COUNTS[role], "paired denominator: "+role)
        check(len({r["episode_id"] for r in rows}) == len(rows)
              and all(type(r[k]) is bool for r in rows for k in ("v3","selected")), "invalid paired evidence")
    sealed = pairs["sealed"]
    pool = [r for r in sealed if r["target_sector"] == 10]
    shaft = [r for r in sealed if r["target_sector"] == 41]
    equal([len(pool),len(shaft), sorted(Counter(r["case"] for r in pool).values()),
           sorted(Counter(r["case"] for r in shaft).values())], [32,16,[4]*8,[4]*4], "sealed position coverage")
    summary = transitions(pool)
    net = summary["counts"]["gain"] - summary["counts"]["regression"]
    positive = sum(g["net"] > 0 for g in summary["by_position"].values())
    sealed_lost = transitions(shaft)["episodes"]["regression"]
    original = {r["episode_id"]:r for r in pairs["original"] if r["target_sector"] == 41}
    check(len(winners) == len(set(winners)) == 24 and set(winners) <= original.keys(), "historical v3 winner coverage")
    baseline_lost = [e for e in winners if not original[e]["v3"]]
    selected_lost = [e for e in winners if not original[e]["selected"]]
    met = net >= 4 and positive >= 3 and not sealed_lost and not selected_lost
    return dict(status="inconclusive" if baseline_lost else ("met" if met else "not_met"),
                sealed_pool_net=net, positive_pool_positions=positive,
                lost_sealed_v3_shaft_winners=sealed_lost, historical_original_v3_shaft_winners=winners,
                lost_original_v3_shaft_winners=selected_lost, original_v3_baseline_discrepancies=baseline_lost,
                thresholds=run.RECIPE["progress_criterion"])


def complete_pairs(rows, ids):
    """Model comparison by assigned position and heading, with native shown separately."""
    indexed = {k:{r["episode_id"]:r for r in role} for k,role in rows.items()}
    pairs = []
    for episode in ids:
        base = indexed["v3"][episode]
        pair = {k:base[k] for k in ("episode_id","case","yaw_deg","target_sector")}
        pair.update({k:group[episode]["physical_success"] for k,group in indexed.items()})
        pairs.append(pair)
    return pairs


def public_attempt(assignment, result):
    entry = dict(candidate_id=assignment["candidate_id"], episode_id=assignment["job"]["episode_id"],
                 status=result["status"])
    if entry["status"] == "unrun":
        return entry
    entry.update(raw=result["raw"], reinferred_decisions=result["reinferred_decisions"])
    if result["status"] == "censored":
        entry["reason"] = result["reason"]
        end = result.get("observed_native_terminal")
        entry["observed_native_terminal"] = end["terminal"] if end else None
    else:
        row = result["row"]
        entry.update({k:row[k] for k in ("physical_success","terminal","physics_steps","control_ticks",
                                        "initial_observation_sha256")})
    # Exact process evidence is bound by raw/process.json, including its timestamps.
    if result["process"] is not None:
        entry["process"] = {k:result["process"][k] for k in ("engine_returncode","worker_returncode","timed_out",
                                                              "started_at_utc","ended_at_utc","elapsed_seconds")}
    return entry


def interrupted_journal(work):
    """A missing observation cannot excuse a malformed, fully written worker record."""
    records = trial.available_stream(work/"decisions.jsonl")
    for tick, row in enumerate(records):
        check(set(row) == {"tick","observation_sha256","quantized"}, "interrupted journal fields")
        equal(row["tick"], tick, "interrupted journal tick")
        q = row["quantized"]
        check(isinstance(row["observation_sha256"],str) and re.fullmatch("[0-9a-f]{64}",row["observation_sha256"])
              and isinstance(q,list) and len(q) == 5 and all(type(n) is int and -100 <= n <= 100 for n in q[:4])
              and type(q[4]) is int and 0 <= q[4] <= 3, "invalid interrupted journal decision")
    return records


def interrupted_controls(assignment, work, case, paths, edge, has_terminal, starts=None):
    """Verify observable physical actions beyond the last buffered decision on interruption."""
    native = trial.available_stream(work/"native.jsonl")
    frames = trial.available_stream(work/"motor.jsonl")
    journal = interrupted_journal(work)
    origin = None
    if (work/"start.json").is_file():
        origin = trial.prior.available_record((work/"start.json").read_bytes())
        if origin is not None:
            equal(run.motor.digest(work/"start.json"), edge[1], "interrupted stock origin")
    job = assignment["job"]
    if native:
        assigned = native.pop(0)
        equal([assigned["event"],assigned["sector"],assigned["seed"],assigned["position"]],
              ["assigned",job["target_sector"],edge[0],edge[2]], "interrupted assigned stock edge")
    if has_terminal:
        native.pop()  # audit_attempt already checked the actual native terminal.
    if not frames and not native and not journal:
        return 0, 0
    decide = None
    if paths[0]:
        identity, source = trial.model_data(*paths)
        equal(identity, assignment["model"], "interrupted model identity")
        namespace = {}
        exec(compile(source,str(paths[0]),"exec"),namespace)
        decide = namespace["decide"]
    owner = "model" if decide else "baseline"
    previous = step = verified = unavailable = 0
    residual = 0.
    dt = run.motor.f32(job["control_dt"])
    duration = job["requested_hold_ms"]
    for tick in range(max((len(frames)+1)//2,len(native),len(journal))):
        check(step < run.motor.MAX_STEPS, "interrupted control exceeds physics budget")
        decision = journal[tick]["quantized"] if tick < len(journal) else None
        actual = native[tick] if tick < len(native) else None
        obs = frames[2*tick] if 2*tick < len(frames) else None
        applied = frames[2*tick+1] if 2*tick+1 < len(frames) else None
        expected = None
        if actual is not None:
            check(type(actual["wet"]) is bool and (tick or actual["wet"]), "invalid interrupted native medium")
        if obs is not None:
            run.motor.physical_record(obs)
            sense = obs["sense"]
            wet = sense["medium"] == "water"
            check(type(sense["on_water_surface"]) is bool and type(sense["supported"]) is bool
                  and sense["medium"] in ("water","air") and (tick or wet)
                  and sense["on_water_surface"] == bool(obs["physics_flags"] & 0x100000)
                  and math.isclose(sense["tick_ms"], dt*1000, abs_tol=.0001), "invalid interrupted physical observation")
            if actual is not None:
                equal(actual["wet"],wet,"interrupted native/observation medium")
            equal([obs["event"],obs["tick"],obs["step"],obs["sense"]["buttons"],obs["goal"]],
                  ["observation",tick,step,previous,{"sector":job["target_sector"],"position":edge[2]}],
                  "interrupted observation identity")
            if tick == 0:
                if origin is not None:
                    run.motor.verify_start(obs,case,job["yaw_deg"],origin)
                with (work/"motor.jsonl").open("rb") as stream:
                    bind_observation(starts, job["episode_id"], trial.prior.sha(stream.readline()))
            if decide and (actual is not None or applied is not None or decision is not None):
                observation = {"state":obs["state"], "lily":{"sense":obs["sense"]}}
                context = {"directive":{"goal":"learned-motor","parameters":{"position":edge[2],"duration_ms":duration}}}
                expected = run.motor.quantized(decide(observation,context),duration)
                if decision is not None:
                    equal(decision, expected, "interrupted frozen decision")
        for event, record in (("input",applied),("control",actual)):
            if record is None:
                continue
            equal([record[k] for k in ("event","tick","step","owner")], [event,tick,step,owner], "interrupted actuation")
            check(type(record["buttons"]) is int and 0 <= record["buttons"] <= (3 if decide else 31)
                  and len(record["axes"]) == 4 and all(type(a) in (float,int) and math.isfinite(a) for a in record["axes"]),
                  "invalid interrupted action")
            if decide:
                check(all(-1.0000001 <= a <= 1.0000001 and abs(a-round(100*a)/100) < 1e-7 for a in record["axes"]),
                      "invalid interrupted quantized action")
            if event == "input":
                equal([record["source_tick"],record["presses"]], [tick,record["buttons"] & ~previous], "interrupted button edges")
            comparable = expected if expected is not None else decision
            if comparable is not None:
                trial.prior.check_censored_control(record,event,tick,step,comparable,previous)
        if actual is not None and applied is not None:
            equal([actual["axes"],actual["buttons"]], [applied["axes"],applied["buttons"]], "interrupted actuation mismatch")
        action = actual if actual is not None else applied
        if action is not None:
            previous = action["buttons"]
            verified += int(expected is not None)
            unavailable += int(decide is not None and expected is None)
        span = dt+residual
        ticks = math.floor(span*run.motor.HZ+.5)
        residual = span-ticks/run.motor.HZ
        step += ticks
    return verified, unavailable


def bind_start(row, job, edges, starts):
    equal({k:row[k] for k in job}, job, "raw result/assignment")
    episode = job["episode_id"]
    trial.match_starts({"arm":[row]}, [episode], edges)
    bind_observation(starts, episode, row["initial_observation_sha256"])


def bind_observation(starts, episode, digest):
    if starts is not None:
        equal(digest, starts.setdefault(episode,digest), "different actual starts")


class Reconstruction:
    def __init__(self, inv, declaration, digest, banks, header, edges, winners):
        self.inv = inv
        self.root = inv.root
        self.declaration = declaration
        self.banks = banks
        self.header = header
        self.edges = edges
        self.winners = winners
        self.binding = dict(run_id=run.RUN_ID, declaration_sha256=digest,
                            run_sha256=run.motor.digest(self.root/"run.json"),
                            fixture_source_sha256=header["fixture_sources"]["evaluator"]["native/tests/stock_water_replay/evaluate_motor.py"])
        self.report = dict(schema=1, experiment="lily-outcome-head-v4", **self.binding, status="inconclusive",
                           models={}, generations=[], blocks={}, selection=None, freeze=None, comparisons={}, criterion=None)
        self.earliest = trial.time_utc(header["started_at_utc"])
        self.last_end = self.earliest
        self.verified_censored_controls = 0
        self.unverifiable_censored_controls = 0

    def attempt(self, directory, assignment, case, paths, starts=None):
        work = directory/assignment["work_dir"]
        if not self.inv.entry(work, True):
            return dict(status="unrun")
        if not (work/"assignment.json").exists() or (work/"assignment.json.partial").exists():
            # Dispatch cannot start until the exclusive claim has been published.
            # A crash between mkdir, publication and unlink can leave only these files.
            names = {p.name for p in work.iterdir()}
            check(names <= {"assignment.json","assignment.json.partial"}, "physical evidence without a published claim")
            raw = {p.name:file_record(p) for p in work.iterdir()}
            expected = (json.dumps(assignment, indent=2, allow_nan=False)+"\n").encode()
            for name in names:
                data = (work/name).read_bytes()
                check(data == expected if name == "assignment.json" else expected.startswith(data),
                      "ambiguous claim contradicts assignment")
            if len(names) == 2:
                equal(raw["assignment.json"], raw["assignment.json.partial"], "conflicting claim publications")
            result = dict(status="censored", row=None, reason="unpublished_attempt_claim", process=None,
                          raw=raw, reinferred_decisions=0, observed_native_terminal=None)
        else:
            result = trial.audit_attempt(assignment, work, case, *paths)
            if "observed_start" in result:
                # A clean but unfinished process publication already passed every stock
                # join and decision replay. Its physical start survives the withheld score.
                job = assignment["job"]
                bind_start(job | result["observed_start"],job,self.edges,starts)
                self.verified_censored_controls += result["reinferred_decisions"]
            elif result["status"] == "censored":
                edge = self.edges[assignment["job"]["target_sector"]]
                verified, unavailable = interrupted_controls(assignment,work,case,paths,edge,
                                                            result.get("observed_native_terminal") is not None, starts)
                self.verified_censored_controls += verified
                self.unverifiable_censored_controls += unavailable
            elif result["status"] == "complete":
                bind_start(result["row"],assignment["job"],self.edges,starts)
        for name in result["raw"]:
            self.inv.entry(work/name)
        if result["process"]:
            start = trial.time_utc(result["process"]["started_at_utc"])
            check(start >= self.earliest, "attempt predates its prerequisite")
            self.last_end = max(self.last_end, trial.time_utc(result["process"]["ended_at_utc"]))
        return result

    def block(self, stage, label, ids, refs, predecessor):
        role = "train" if stage == "train" else label
        bank = self.banks[role]
        directory = self.root/stage/label
        self.inv.directory(directory)
        models = {k:run.identity(v) if v else None for k,v in refs.items()}
        binding = run.bound(self.binding, predecessor)
        ledger = run.assignments(label, bank, ids, models, binding)
        assignment_path = directory/"assignments.json"
        equal(self.inv.publication(assignment_path), ledger, f"fixed assignment ledger: {stage}/{label}")
        paths = {k:run.model_paths(self.root, v["artifact"]) if v else (None,None) for k,v in refs.items()}
        attempts = []
        # Pair every available completion even when another arm is genuinely censored.
        starts = {}
        for a in ledger:
            job = a["job"]
            try:
                result = self.attempt(directory, a, bank["cases"][job["case"]], paths[a["candidate_id"]], starts)
            except (ValueError, KeyError, IndexError, TypeError, OSError) as exc:
                raise ValueError(f"{stage}/{label}/{a['work_dir']}: {exc}") from exc
            attempts.append(result)
        counts = run.counts_for(attempts)
        check(all(a["status"] == "unrun" for a in attempts[counts["attempted"]:]), "gap in ordered attempt inventory")
        for i, result in enumerate(attempts):
            if result.get("reason") == "unpublished_attempt_claim":
                check(i == counts["attempted"]-1, "later attempt after an unfinished assignment claim")
        info = dict(role=role, models=refs, assignments=run.link(self.root, str(assignment_path.relative_to(self.root))),
                    counts=counts, attempts=[public_attempt(a,r) for a,r in zip(ledger,attempts,strict=True)])
        self.report["blocks"][f"{stage}/{label}"] = info
        path = directory/"block.json"
        unfinished = {"unpublished_attempt_claim","unpublished_process_witness","missing_process_witness"}
        if any(r.get("reason") in unfinished for r in attempts):
            check(not path.exists() and not path.with_suffix(".json.partial").exists(),
                  "block publication after an unfinished attempt publication")
        block = self.inv.publication(path)
        free = block["free_bytes_after"]
        check(type(free) is int and free >= 0, "invalid free space witness")
        equal(block, dict(assignments_sha256=info["assignments"]["sha256"], counts=counts, attempts=attempts,
                          free_bytes_after=free), "block receipt disagrees with raw evidence")
        info.update(receipt=run.link(self.root,str(path.relative_to(self.root))), free_bytes_after=free)
        if counts["completed"] != counts["assigned"]:
            check(counts["censored"] > 0, "finished dispatch with unexplained unrun assignments")
            raise Unfinished(f"{stage}/{label} stopped with {counts['censored']} censored, {counts['unrun']} unrun")
        rows = run.measured_rows(block, ledger, models)
        trial.match_starts(rows, ids, self.edges)
        self.earliest = self.last_end
        return info["receipt"], rows

    def train(self):
        self.inv.directory(self.root/"train")
        self.inv.directory(self.root/"models")
        parent = run.PARENT
        policy_bytes = (run.ROOT/parent["policy"]).read_bytes()
        model_bytes = (run.ROOT/parent["model"]).read_bytes()
        current = model_ref(self.inv,"v3",model_bytes,policy_bytes)
        equal(run.identity(current), run.identity(parent), "retained v3 identity")
        self.report["models"]["v3"] = current
        checkpoints = {"v3":current}
        rankings = []
        previous = self.binding["run_sha256"]
        for gen, ids in enumerate(self.declaration["training_batches"], 1):
            label = f"g{gen:02d}"
            parent_policy, parent_model = run.model_paths(self.root, current["artifact"])
            proposals = search.candidate_models(read(parent_model), gen, self.binding["declaration_sha256"])
            refs = {}
            for index, proposal in enumerate(proposals):
                name = proposal["candidate_id"]
                model = proposal["model"]
                data = contact.canonical(model)+b"\n" if index else parent_model.read_bytes()
                export = contact.policy_source(model).encode() if index else parent_policy.read_bytes()
                refs[name] = model_ref(self.inv, name, data, export)
                self.report["models"][name] = refs[name]
            block, rows = self.block("train", label, ids, refs, previous)
            result = search.select_generation(proposals, rows, ids)
            result["scores"] = {k:list(v) for k,v in result["scores"].items()}
            ranking = dict(block=block, parent=current, candidates=refs, **result)
            path = f"train/{label}/ranking.json"
            equal(self.inv.publication(self.root/path), ranking, f"reconstructed ranking: {label}")
            link = run.link(self.root,path)
            self.report["generations"].append(dict(ranking, receipt=link))
            rankings.append(link)
            current = refs[result["selected_id"]]
            previous = link["sha256"]
            if gen in (4,8):
                checkpoints[f"g{gen}"] = current
        training = dict(**self.binding, generations=rankings, checkpoints=checkpoints)
        equal(self.inv.publication(self.root/"training.json"), training, "reconstructed training")
        self.report["training"] = dict(receipt=run.link(self.root,"training.json"), checkpoints=checkpoints)
        return checkpoints

    def select(self, checkpoints):
        self.inv.directory(self.root/"select")
        bank = self.banks["development"]
        ids = bank["ids"]
        training = run.link(self.root,"training.json")
        block, rows = self.block("select","development",ids,checkpoints,training["sha256"])
        pool, shaft = [[i for i in ids if bank["jobs"][i,"every_tick"]["target_sector"] == sector]
                       for sector in (10,41)]
        decision = search.select_development(rows, pool, shaft)
        selection = dict(**self.binding, training=training, block=block, checkpoints=checkpoints, **decision)
        equal(self.inv.publication(self.root/"selection.json"), selection, "reconstructed development selection")
        link = run.link(self.root,"selection.json")
        self.report["selection"] = dict(decision, receipt=link)
        selected = decision["selected"]
        freeze = self.inv.publication(self.root/"freeze.json")
        when = trial.time_utc(freeze["frozen_at_utc"])
        check(when >= self.last_end, "selection freeze precedes measured evidence")
        model = checkpoints[selected] if selected else None
        equal(freeze, dict(**self.binding, selected=selected, model=model, selection=link,
                           frozen_at_utc=freeze["frozen_at_utc"]), "selected checkpoint freeze")
        self.report["freeze"] = dict(freeze, receipt=run.link(self.root,"freeze.json"))
        self.earliest = self.last_end = when
        return model

    def evaluate(self, checkpoints, selected):
        self.inv.directory(self.root/"evaluate")
        freeze = run.link(self.root,"freeze.json")
        previous = freeze["sha256"]
        pairs, blocks = {}, {}
        for role in ("sealed", *run.DIAGNOSTIC):
            arms = dict(v3=checkpoints["v3"], selected=selected)
            if role == "sealed":
                arms["native"] = None
            ids = self.banks[role]["ids"]
            block, rows = self.block("evaluate", role, ids, arms, previous)
            blocks[role] = block
            previous = block["sha256"]
            pairs[role] = complete_pairs(rows, ids)
            self.report["comparisons"][role] = dict(assignments=pairs[role], **transitions(pairs[role]))
        evaluation = dict(**self.binding, freeze=freeze, blocks=blocks, historical_v3_original_shaft_winners=self.winners)
        equal(self.inv.publication(self.root/"evaluation.json"), evaluation, "reconstructed evaluation")
        self.report["evaluation"] = run.link(self.root,"evaluation.json")
        self.report["criterion"] = transfer(pairs,self.winners)
        self.report["status"] = "evaluated"

    def stages(self):
        checkpoints = self.train()
        selected = self.select(checkpoints)
        if selected is None:
            self.report["status"] = "no_selection"
        else:
            self.evaluate(checkpoints,selected)


def register_build(inv, header):
    build = inv.root/"build"
    inv.directory(build)
    for name in header["build"]["files"]:
        p = build/name
        for parent in p.relative_to(build).parents:
            inv.directory(build/parent)
        check(inv.entry(p), "missing retained build file")


def reconstruct(root, declaration, digest, banks, header, edges, winners):
    inv = Inventory(root)
    inv.publication(root/"run.json")
    register_build(inv,header)
    audit = Reconstruction(inv,declaration,digest,banks,header,edges,winners)
    try:
        audit.stages()
        inv.stable()
    except Unfinished as exc:
        audit.report.update(status="inconclusive", criterion=None)
        audit.report["stopped_at"] = str(exc)
    inv.finish()
    report = audit.report
    blocks = report["blocks"]
    def totals(group):
        return {key:sum(b["counts"][key] for b in group) for key in run.counts_for([])}
    report["counts"] = totals(blocks.values())
    report["phases"] = {phase:totals([b for k,b in blocks.items() if k.split("/")[0] == phase])
                        for phase in ("train","select","evaluate")}
    attempts = [a for b in blocks.values() for a in b["attempts"]]
    report["reinferred_decisions"] = sum(a.get("reinferred_decisions",0) for a in attempts)
    report["verified_applied_model_decisions"] = (audit.verified_censored_controls +
        sum(a["reinferred_decisions"] for a in attempts if a["status"] == "complete"))
    report["unverifiable_applied_model_decisions"] = audit.unverifiable_censored_controls
    report["raw_attempt_bytes"] = sum(f["bytes"] for a in attempts for f in a.get("raw",{}).values())
    report["partial_files"] = {str(p.relative_to(root)):file_record(p) for p in sorted(inv.seen)
                               if p.name.endswith(".partial")}
    for path in sorted(inv.seen):
        if path.is_file() and path.parent.parent == root/"models" and path.parent.name not in report["models"]:
            report["partial_files"][str(path.relative_to(root))] = file_record(path)
    report["retained_run_bytes"] = sum(p.stat().st_size for p in inv.seen if p.is_file())
    report["initial_free_bytes"] = header["initial_free_bytes"]
    report["last_recorded_free_bytes"] = next((b["free_bytes_after"] for b in reversed(blocks.values())
                                               if "free_bytes_after" in b),None)
    report["audit_filesystem_free_bytes"] = shutil.disk_usage(root).free
    report["execution_budget"] = dict(train=832,development=96,conditional_sealed=144,conditional_diagnostics=134)
    return report


def bank_coverage(banks, batches):
    """Check the experimental cohort sizes by physical edge, independent of its labels."""
    for role, (pool,shaft) in {"train":(48,16),"development":(24,8),"sealed":(32,16)}.items():
        bank = banks[role]
        targets = [bank["jobs"][e,"every_tick"]["target_sector"] for e in bank["ids"]]
        equal([targets.count(10),targets.count(41)], [pool,shaft], role+" bank allocation")
        for case in bank["cases"].values():
            check((case["wet"],case["dry"]) in (("44","10"),("54","41")), "incorrect wet/dry bank edge")
    ids = [i for batch in batches for i in batch]
    check(len(batches) == 8 and len(ids) == len(set(ids)) == 64 and set(ids) == set(banks["train"]["ids"]),
          "incomplete training schedule")
    for batch in batches:
        targets = [banks["train"]["jobs"][e,"every_tick"]["target_sector"] for e in batch]
        equal(targets, [10]*6+[41]*2, "wrong training batch allocation")


def before_run_header(root, decl, digest):
    """A setup interruption can retain build bytes but cannot have any assignment."""
    inv = Inventory(root)
    for name in ("train","models","build"):
        inv.entry(root/name,True)
    sidecar = root/"run.json.partial"
    partial = inv.entry(sidecar)
    if inv.entry(root/"run.json"):
        check(partial and sidecar.read_bytes() == (root/"run.json").read_bytes(), "conflicting setup receipts")
    build = root/"build"
    available = {}
    if build.is_dir():
        available = run.tree_files(build)
        allowed = {"replay","map.numeric","flags.make","stock_functions.inc","AI/jkBotLily.inc"}
        allowed.update(run.inputs.declared(decl))
        check(available.keys() <= allowed, "unexpected build setup inventory")
        for name in allowed:
            for folder in (build/name).relative_to(build).parents:
                inv.entry(build/folder,True)
        for name in available:
            inv.entry(build/name)
    inv.finish()
    return dict(schema=1, experiment="lily-outcome-head-v4", run_id=run.RUN_ID, declaration_sha256=digest,
                status="inconclusive", stopped_at="run header publication is incomplete", generations=[], models={}, blocks={},
                selection=None, freeze=None, comparisons={}, criterion=None, counts=run.counts_for([]),
                phases={p:run.counts_for([]) for p in ("train","select","evaluate")}, reinferred_decisions=0,
                verified_applied_model_decisions=0, unverifiable_applied_model_decisions=0, raw_attempt_bytes=0,
                retained_run_bytes=sum(p.stat().st_size for p in inv.seen if p.is_file()),
                audit_filesystem_free_bytes=shutil.disk_usage(root).free, available_setup_files=available,
                partial_files={"run.json.partial":file_record(sidecar)} if partial else {},
                execution_budget=dict(train=832,development=96,conditional_sealed=144,conditional_diagnostics=134))


def audit(declaration_path, root):
    check(root.is_dir() and not root.is_symlink(), "missing or indirect run inventory")
    decl, digest, banks = run.declaration(declaration_path)
    bank_coverage(banks, decl["training_batches"])
    _, edges, winners = run.history(decl)
    if not (root/"run.json").exists():
        return before_run_header(root,decl,digest)
    check((root/"run.json").is_file() and not (root/"run.json").is_symlink(), "missing authenticated run header")
    check((root/"build").is_dir() and not (root/"build").is_symlink(), "missing or indirect build inventory")
    hdr = portable_header(root, decl, digest)
    if (root/"run.json.partial").exists():
        return before_run_header(root,decl,digest)
    report = reconstruct(root,decl,digest,banks,hdr,edges,winners)
    build = hdr["build"]
    report["sources"] = dict(implementation_commit=decl["implementation_commit"], frozen=decl["frozen_files_sha256"],
                             fixture=hdr["fixture_sources"], spec=decl["spec"], historical_edges=decl["historical_edges"],
                             historical_recovery=decl["historical_recovery"])
    report["declared_cases"] = {k:{"path":e["path"],"sha256":e["sha256"],"episode_ids":e["episode_ids"]}
                                for k,e in (decl["cases"]|decl["diagnostics"]).items()}
    report["measured_build"] = dict(provenance=build["provenance"], files=build["files"],
                                    compiler={k:build["compiler"][k] for k in ("sha256","version")},
                                    python={k:hdr["python"][k] for k in ("sha256","implementation","version")},
                                    numpy=hdr["numpy"])
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("declaration","run","output"):
        parser.add_argument("--"+name, type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        check(not args.output.resolve().is_relative_to(args.run.resolve()), "audit output must be outside retained run")
        check(not args.output.exists() and not args.output.is_symlink(), "audit output already exists")
        report = audit(args.declaration,args.run)
        trial.write(args.output,report)
    except (OSError, ValueError, TypeError, KeyError, IndexError, subprocess.SubprocessError) as exc:
        parser.exit(1,str(exc)+"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

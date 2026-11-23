"""Offline evidence joins, immutable model lineage and the conditional transfer test."""
from contextlib import contextmanager
from copy import deepcopy
import json
import shutil
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.bot_development.analysis import audit_outcome_learning as audit
from scripts.bot_development.analysis import run_outcome_learning as runner


def bank(role, pool, shaft):
    ids, jobs, cases = [], {}, {}
    for sector, size in ((10, pool), (41, shaft)):
        for i in range(size):
            case = f"{role}-{sector}-{i // 4}"
            cases[case] = dict(dry=str(sector))
            episode = f"{case}-yaw{i % 4}"
            ids.append(episode)
            for arm in ("every_tick", "baseline"):
                jobs[episode, arm] = dict(episode_id=episode, case=case, controller=arm,
                                          target_sector=sector, yaw_deg=i % 4)
    return dict(role=role, sha256="c"*64, ids=ids, jobs=jobs, cases=cases)


def physical(a, work, case, policy, model):
    """A fixture for the already-tested process/actuation oracle, backed by real claims."""
    runner.equal(runner.read(work/"assignment.json"), a, "synthetic assignment")
    job = a["job"]
    name, role = a["candidate_id"], a["role"]
    select = (work/"signal").read_text()
    if select == "contradiction":
        raise ValueError("synthetic raw contradiction")
    raw = {p.name:runner.file_record(p) for p in work.iterdir()}
    if select == "censor":
        return dict(status="censored", row=None, reason="abnormal_process", process=None,
                    raw=raw, reinferred_decisions=0, observed_native_terminal=None)
    shaft = job["target_sector"] == 41
    extra = (select == "improve" and role == "development" and name in ("g4", "g8")
             and job["episode_id"].endswith("10-0-yaw0"))
    extra |= (role == "sealed" and name == "selected"
              and (job["yaw_deg"] == 0 or job["episode_id"].endswith("10-0-yaw1")))
    extra |= select == "improve" and role == "train" and name == "g01-c01" and not shaft
    success = bool(shaft or extra)
    row = dict(job, physical_success=success, terminal="supported_dry" if success else "died", physics_steps=100,
               ownership_complete=True, baseline_assisted=False, owner="baseline" if name=="native" else "model",
               seed=7, origin_sha256="o", target_position=[1, 2, 3], initial_observation_sha256=job["episode_id"],
               initial_quantized=[int(name != "v3"), 0, 0, 0, 0], control_ticks=2)
    if "process.json.partial" in raw:
        return dict(status="censored",row=None,raw=raw,process=runner.read(work/"process.json.partial"),
                    reason="unpublished_process_witness",observed_native_terminal={"terminal":row["terminal"]},
                    observed_start={k:row[k] for k in runner.trial.prior.START},
                    reinferred_decisions=0 if name=="native" else 2)
    return dict(status="complete", row=row, raw=raw, process=None, reinferred_decisions=0 if name=="native" else 2)


def measured(mode):
    def block(root, stage, label, bank_, ids, refs, binding, edges, workers):
        directory = root/stage/label
        directory.mkdir()
        ledger = runner.assignments(label, bank_, ids, {k:runner.identity(v) if v else None for k,v in refs.items()}, binding)
        runner.write(directory/"assignments.json", ledger)
        attempts = []
        for a in ledger:
            work = directory/a["work_dir"]
            work.mkdir()
            runner.write(work/"assignment.json", a)
            (work/"signal").write_text(mode)
            attempts.append(physical(a, work, {}, None, None))
        record = dict(assignments_sha256=runner.motor.digest(directory/"assignments.json"), attempts=attempts,
                      counts=runner.counts_for(attempts), free_bytes_after=456)
        runner.write(directory/"block.json", record)
        return runner.link(root, f"{stage}/{label}/block.json"), runner.measured_rows(record, ledger, refs)
    return block


class EvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        sizes = dict(train=(48,16), development=(24,8), sealed=(32,16), original=(3,24), stress=(8,8), recovery=(24,0))
        cls.banks = {role:bank(role, *s) for role,s in sizes.items()}
        cls.decl = dict(training_batches=[cls.banks["train"]["ids"][i:i+8] for i in range(0,64,8)],
                        progress_criterion=runner.RECIPE["progress_criterion"])
        cls.edges = {k:[7,"o",[1,2,3]] for k in (10,41)}
        cls.winners = cls.banks["original"]["ids"][3:]
        cls.roots = {}
        for mode in ("flat", "improve"):
            root = Path(cls.tmp.name)/mode
            root.mkdir()
            for name in ("models", "train", "select", "build"):
                (root/name).mkdir()
            header = dict(started_at_utc="2020-01-01T00:00:00+00:00", initial_free_bytes=runner.FREE,
                          fixture_sources={"evaluator":{"native/tests/stock_water_replay/evaluate_motor.py":"a"*64}},
                          build=dict(files={}), python={}, numpy="test")
            runner.write(root/"run.json", header)
            binding = dict(run_id=runner.RUN_ID, run_sha256=runner.motor.digest(root/"run.json"),
                           declaration_sha256="d"*64, fixture_source_sha256="a"*64)
            with patch.object(runner, "run_block", measured(mode)):
                training = runner.train_generations(root, cls.decl, cls.banks, binding, cls.edges, 1)
                freeze = runner.development(root, cls.banks["development"], binding, cls.edges, training["checkpoints"], 1)
                if mode == "improve":
                    runner.evaluate_blocks(root, cls.banks, dict(binding=binding, edges=cls.edges, winners=cls.winners, workers=1),
                                           freeze, measured(mode))
            cls.roots[mode] = root

    def result(self, mode):
        root = self.roots[mode]
        with patch.object(runner.trial, "audit_attempt", physical):
            return audit.reconstruct(root, self.decl, "d"*64, self.banks, runner.read(root/"run.json"), self.edges, self.winners)

    @contextmanager
    def changed(self, path, value):
        original = path.read_bytes()
        path.write_bytes(value)
        try:
            yield
        finally:
            path.write_bytes(original)

    def test_complete_selected_and_null_gates(self):
        negative = self.result("flat")
        self.assertEqual((negative["status"], negative["counts"]["completed"]), ("no_selection",928))
        self.assertIsNone(negative["criterion"])
        self.assertEqual(len(negative["generations"]), 8)
        self.assertEqual(len(negative["generations"][3]["candidates"]), 13)
        positive = self.result("improve")
        self.assertEqual((positive["status"], positive["counts"]["completed"]), ("evaluated",1206))
        self.assertEqual(positive["selection"]["selected"], "g4")
        self.assertEqual(positive["generations"][0]["selected_id"], "g01-c01")
        self.assertEqual(positive["generations"][1]["parent"],positive["models"]["g01-c01"])
        self.assertEqual(positive["criterion"]["status"], "met")
        self.assertEqual(positive["reinferred_decisions"], (1206-48)*2)

    def test_null_gate_rejects_even_an_empty_sealed_stage(self):
        root = self.roots["flat"]
        (root/"evaluate").mkdir()
        try:
            with self.assertRaisesRegex(ValueError, "inventory|selection"):
                self.result("flat")
        finally:
            (root/"evaluate").rmdir()

    def test_proposal_incumbent_parent_rank_and_wrong_role(self):
        root = self.roots["flat"]
        candidate = root/"models/g01-c01/model.json"
        bad = runner.read(candidate)
        bad["w2"][0][2] += .075
        incumbent = root/"models/g02-c00/model.json"
        rank = root/"train/g01/ranking.json"
        changed_score = runner.read(rank)
        changed_score["scores"]["g01-c09"][0] += 1
        changed_parent = runner.read(rank)
        changed_parent["parent"] = changed_parent["candidates"]["g01-c01"]
        ledger = root/"select/development/assignments.json"
        wrong_role = runner.read(ledger)
        wrong_role[0]["role"] = "sealed"
        for path, data in ((candidate,runner.contact.canonical(bad)+b"\n"), (incumbent,incumbent.read_bytes()+b" "),
                           (rank,json.dumps(changed_score).encode()),(rank,json.dumps(changed_parent).encode()),
                           (ledger,json.dumps(wrong_role).encode()),(ledger,json.dumps(wrong_role[:-1]).encode())):
            with self.subTest(path=path.name), self.changed(path, data), self.assertRaises(ValueError):
                self.result("flat")

    def test_unledgered_duplicate_and_orphan_model(self):
        root = self.roots["flat"]
        for directory in (root/"train/g01/retry", root/"models/other"):
            directory.mkdir()
            try:
                with self.assertRaisesRegex(ValueError,"inventory"):
                    self.result("flat")
            finally:
                directory.rmdir()

    def test_completed_run_rejects_an_unfinished_predecessor_publication(self):
        root = self.roots["flat"]
        source = root/"train/g01/block.json"
        partial = source.with_suffix(".json.partial")
        shutil.copyfile(source,partial)
        try:
            with self.assertRaisesRegex(ValueError,"inventory"):
                self.result("flat")
        finally:
            partial.unlink()

    def test_freeze_must_reference_the_selected_measured_bytes(self):
        path = self.roots["improve"]/"freeze.json"
        changed = runner.read(path)
        changed["model"] = runner.read(self.roots["improve"]/"training.json")["checkpoints"]["v3"]
        with self.changed(path,json.dumps(changed).encode()), self.assertRaisesRegex(ValueError,"freeze"):
            self.result("improve")

    def test_partial_block_keeps_censor_and_unrun_but_refuses_a_contradiction(self):
        with self.first_block_snapshot(2) as (dest,ledger,read_partial):
            first, second = ledger[:2]
            (dest/first["work_dir"]/"signal").write_text("censor")
            report = read_partial()
            self.assertEqual(report["status"], "inconclusive")
            self.assertIsNone(report["criterion"])
            self.assertEqual([report["counts"][k] for k in ("assigned","attempted","completed","censored","unrun")],
                             [104,2,1,1,102])
            (dest/second["work_dir"]/"signal").write_text("contradiction")
            with self.assertRaisesRegex(ValueError,"contradiction"):
                read_partial()

    @contextmanager
    def first_block_snapshot(self, claimed):
        source = self.roots["flat"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/"build").mkdir()
            (root/"models").mkdir()
            block = root/"train/g01"
            block.mkdir(parents=True)
            shutil.copyfile(source/"run.json",root/"run.json")
            for name in ("v3",*(f"g01-c{n:02d}" for n in range(13))):
                shutil.copytree(source/"models"/name,root/"models"/name)
            ledger_path = block/"assignments.json"
            shutil.copyfile(source/"train/g01/assignments.json",ledger_path)
            ledger = runner.read(ledger_path)
            for a in ledger[:claimed]:
                shutil.copytree(source/"train/g01"/a["work_dir"],block/a["work_dir"])
            def result():
                with patch.object(runner.trial,"audit_attempt",physical):
                    return audit.reconstruct(root,self.decl,"d"*64,self.banks,runner.read(root/"run.json"),self.edges,self.winners)
            yield block,ledger,result

    def test_process_sidecar_is_unscored_and_dispatched_sibling_survives(self):
        with self.first_block_snapshot(2) as (block,ledger,result):
            first = block/ledger[0]["work_dir"]
            status = dict(schema=1, engine_returncode=1,worker_returncode=0,timed_out=None,error=None,
                          started_at_utc="2020-01-01T00:00:00Z",ended_at_utc="2020-01-01T00:00:01Z",elapsed_seconds=1)
            runner.write(first/"process.json",status)
            shutil.copyfile(first/"process.json",first/"process.json.partial")
            report = result()
            self.assertEqual(report["status"],"inconclusive")
            self.assertEqual([report["counts"][k] for k in ("attempted","completed","censored","unrun")],[2,1,1,102])
            attempts = report["blocks"]["train/g01"]["attempts"]
            self.assertEqual(attempts[0]["reason"],"unpublished_process_witness")
            self.assertEqual(attempts[0]["observed_native_terminal"],"died")
            self.assertEqual(attempts[1]["status"],"complete")
            self.assertIsNone(report["criterion"])

    def test_completed_process_sidecar_still_requires_its_historical_seed(self):
        from test_lily_outcome_rollouts import RolloutTests
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assignment,work,case,policy,model,_ = RolloutTests().fixture(root)
            assignment["work_dir"] = work.name
            (work/"assignment.json").write_text(json.dumps(assignment))
            shutil.copyfile(work/"process.json",work/"process.json.partial")
            trace = work/"native.jsonl"
            lines = trace.read_bytes().splitlines(keepends=True)
            assigned = json.loads(lines[0])
            edges = {assigned["sector"]:[assigned["seed"],runner.motor.digest(work/"start.json"),assigned["position"]]}
            runner.write(root/"run.json",{})
            header = dict(started_at_utc="2020-01-01T00:00:00Z",
                          fixture_sources={"evaluator":{"native/tests/stock_water_replay/evaluate_motor.py":"x"}})
            builder = audit.Reconstruction(audit.Inventory(root),{},"d"*64,{},header,edges,[])
            def observed():
                return builder.attempt(root,assignment,case,(policy,model))
            matching = observed()
            self.assertEqual((matching["status"],matching["row"]),("censored",None))
            lines[0] = (json.dumps(dict(assigned,seed=assigned["seed"]+1))+"\n").encode()
            trace.write_bytes(b"".join(lines))
            with self.assertRaisesRegex(ValueError,"stock edge or seed"):
                observed()

    def test_sidecar_and_completed_sibling_must_share_initial_observation(self):
        # The ninth slot is the second candidate's measurement of the first start.
        for sidecar_slot in (0,8):
            with self.subTest(sidecar_slot=sidecar_slot), self.first_block_snapshot(9) as (block,ledger,result):
                work = block/ledger[sidecar_slot]["work_dir"]
                status = dict(schema=1,engine_returncode=1,worker_returncode=0,timed_out=None,error=None,
                              started_at_utc="2020-01-01T00:00:00Z",ended_at_utc="2020-01-01T00:00:01Z",elapsed_seconds=1)
                runner.write(work/"process.json",status)
                shutil.copyfile(work/"process.json",work/"process.json.partial")
                self.assertEqual(result()["counts"]["censored"],1)
                original = physical
                def changed_start(a,path,case,policy,model):
                    evidence = original(a,path,case,policy,model)
                    if path == work:
                        evidence["observed_start"]["initial_observation_sha256"] = "f"*64
                    return evidence
                with patch(__name__+".physical",changed_start), self.assertRaisesRegex(ValueError,"different actual starts"):
                    result()

    def test_process_sidecar_cannot_be_credited_in_self_consistent_complete_block(self):
        with self.first_block_snapshot(104) as (block,ledger,result):
            first = block/ledger[0]["work_dir"]
            status = dict(schema=1,engine_returncode=1,worker_returncode=0,timed_out=None,error=None,
                          started_at_utc="2020-01-01T00:00:00Z",ended_at_utc="2020-01-01T00:00:01Z",elapsed_seconds=1)
            for name in ("process.json","process.json.partial"):
                runner.write(first/name,status)
            record = runner.read(self.roots["flat"]/"train/g01/block.json")
            record["attempts"][0]["raw"] = {p.name:runner.file_record(p) for p in first.iterdir()}
            runner.write(block/"block.json",record)
            with self.assertRaisesRegex(ValueError,"publication"):
                result()

    def test_process_sidecar_alone_checks_its_reported_exit_against_real_trace(self):
        from test_lily_outcome_rollouts import RolloutTests
        with tempfile.TemporaryDirectory() as tmp:
            assignment,work,case,policy,model,proc = RolloutTests().fixture(Path(tmp))
            partial = work/"process.json.partial"
            (work/"process.json").rename(partial)
            def check_sidecar():
                return runner.trial.audit_attempt(assignment,work,case,policy,model)
            observed = check_sidecar()
            self.assertEqual(observed["reason"],"unpublished_process_witness")
            self.assertEqual(observed["observed_native_terminal"]["terminal"],"died")
            self.assertEqual(observed["process"],proc)
            self.assertIsNone(observed["row"])
            partial.write_text(json.dumps(dict(proc,engine_returncode=0)))
            with self.assertRaisesRegex(ValueError,"marker|terminal"):
                check_sidecar()

    def test_unfinished_assignment_must_be_last_slot_and_block_must_be_unpublished(self):
        for slot in (0,1):
            with self.subTest(slot=slot), self.first_block_snapshot(2) as (block,ledger,result):
                work = block/ledger[slot]["work_dir"]
                (work/"signal").unlink()
                (work/"assignment.json").unlink()
                if slot == 0:
                    with self.assertRaisesRegex(ValueError,"claim"):
                        result()
                else:
                    report = result()
                    self.assertEqual(report["counts"]["completed"],1)
                    attempts = [physical(ledger[0],block/ledger[0]["work_dir"],{},None,None),
                                dict(status="censored",row=None,reason="unpublished_attempt_claim",process=None,
                                     raw={},reinferred_decisions=0,observed_native_terminal=None)]
                    attempts.extend(dict(status="unrun") for _ in ledger[2:])
                    runner.write(block/"block.json",dict(assignments_sha256=runner.motor.digest(block/"assignments.json"),
                                                        counts=runner.counts_for(attempts),attempts=attempts,free_bytes_after=5))
                    with self.assertRaisesRegex(ValueError,"publication"):
                        result()

    def test_transfer_thresholds_use_net_position_and_actual_historical_ids(self):
        pairs = {}
        for role in ("sealed",*runner.DIAGNOSTIC):
            b = self.banks[role]
            pairs[role] = []
            for e in b["ids"]:
                job = b["jobs"][e,"every_tick"]
                won = job["target_sector"] == 41
                row = dict(episode_id=e,case=job["case"],yaw_deg=job["yaw_deg"],target_sector=job["target_sector"],
                           v3=won, selected=won)
                pairs[role].append(row)
        for i in (0,4,8,9):
            pairs["sealed"][i]["selected"] = True
        baseline = audit.transfer(pairs, self.winners)
        self.assertEqual((baseline["status"],baseline["sealed_pool_net"],baseline["positive_pool_positions"]),("met",4,3))
        for indices, expected in (((0,1,4,5),"not_met"), ((0,4,8),"not_met")):
            p = deepcopy(pairs)
            for i in range(32):
                p["sealed"][i]["selected"] = i in indices
            self.assertEqual(audit.transfer(p,self.winners)["status"],expected)
        for role, i in (("original",-1),("sealed",-1)):
            p = deepcopy(pairs)
            p[role][i]["selected"] = False
            self.assertEqual(audit.transfer(p,self.winners)["status"],"not_met")
        p = deepcopy(pairs)
        p["original"][-1]["v3"] = False
        self.assertEqual(audit.transfer(p,self.winners)["status"],"inconclusive")

    def test_interrupted_unjournaled_actuation_can_still_be_checked_offline(self):
        from test_lily_outcome_rollouts import RolloutTests
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assignment, work, case, policy, model, proc = RolloutTests().fixture(root)
            (work/"native.jsonl").write_bytes(b"".join((work/"native.jsonl").read_bytes().splitlines(keepends=True)[:-1]))
            (work/"decisions.jsonl").write_bytes(b"")
            (work/"engine.log").write_bytes(b"")
            proc.update(engine_returncode=-9, worker_returncode=-9, timed_out="engine")
            (work/"process.json").write_text(json.dumps(proc))
            assignment["work_dir"] = "attempt"
            (work/"assignment.json").write_text(json.dumps(assignment))
            start = runner.read(work/"start.json")
            self.assertIn("wet_sector",start)
            assigned = json.loads((work/"native.jsonl").read_bytes().splitlines()[0])
            edge = [assigned["seed"],runner.motor.digest(work/"start.json"),assigned["position"]]
            runner.write(root/"run.json",{})
            header = dict(started_at_utc="2020-01-01T00:00:00+00:00",
                          fixture_sources={"evaluator":{"native/tests/stock_water_replay/evaluate_motor.py":"x"}})
            builder = audit.Reconstruction(audit.Inventory(root),{}, "d"*64, {}, header,
                                           {assigned["sector"]:edge}, [])
            result = builder.attempt(root,assignment,case,(policy,model))
            self.assertEqual((result["status"],result["reinferred_decisions"]),("censored",0))
            self.assertEqual(builder.verified_censored_controls,1)
            frames = (work/"motor.jsonl").read_bytes().splitlines()
            action = json.loads(frames[1])
            action["axes"][0] = .71
            frames[1] = json.dumps(action).encode()
            (work/"motor.jsonl").write_bytes(b"\n".join(frames)+b"\n")
            with self.assertRaisesRegex(ValueError,"action|actuation"):
                builder.attempt(root,assignment,case,(policy,model))

    def test_interrupted_medium_and_journal_are_independently_checkable(self):
        from test_lily_outcome_rollouts import RolloutTests
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a,work,case,policy,model,status = RolloutTests().fixture(root)
            assigned,control,_ = (json.loads(line) for line in (work/"native.jsonl").read_bytes().splitlines())
            edge = [assigned["seed"],runner.motor.digest(work/"start.json"),assigned["position"]]
            def controls():
                return audit.interrupted_controls(a,work,case,(policy,model),edge,False)
            def native(wet):
                (work/"native.jsonl").write_text(json.dumps(assigned)+"\n"+json.dumps(dict(control,wet=wet))+"\n")
            journal = work/"decisions.jsonl"
            valid = runner.read(journal)
            native(False)
            with self.assertRaisesRegex(ValueError,"medium"):
                controls()
            native(True)
            # At a later tick each stream is independently plausible, but their media disagree.
            motor = work/"motor.jsonl"
            initial = motor.read_bytes()
            obs,input_ = (json.loads(line) for line in initial.splitlines())
            obs.update(tick=1,step=6,sense=dict(obs["sense"],medium="air"))
            input_.update(tick=1,step=6,source_tick=1)
            motor.write_bytes(initial+(json.dumps(obs)+"\n"+json.dumps(input_)+"\n").encode())
            with (work/"native.jsonl").open("a") as stream:
                stream.write(json.dumps(dict(control,tick=1,step=6,wet=True))+"\n")
            with self.assertRaisesRegex(ValueError,"medium"):
                controls()
            native(True)
            motor.write_bytes(initial)
            journal.write_bytes((json.dumps(valid)+"\nbad later journal line\n").encode())
            with self.assertRaises(ValueError):
                controls()
            journal.write_text(json.dumps(valid)+"\n")
            (work/"motor.jsonl").unlink()
            self.assertEqual(controls(),(0,1))
            for bad in (b"bad json\n",b'{}\n',json.dumps(dict(valid,tick=1)).encode(),
                        json.dumps(dict(valid,observation_sha256="wrong")).encode(),
                        json.dumps(dict(valid,quantized=[101,0,0,0,0])).encode(),
                        json.dumps(dict(valid,quantized=[1,0,0,0,0])).encode()):
                with self.subTest(bad=bad):
                    journal.write_bytes(bad)
                    with self.assertRaises(ValueError):
                        controls()
            journal.write_bytes(b'{"tick"')
            self.assertEqual(controls(),(0,1))

    def test_header_portability_and_generated_includes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build = root/"build"
            (build/"AI").mkdir(parents=True)
            (build/"source/src").mkdir(parents=True)
            for name,content in (("replay",b"exe"),("flags.make",b"flags"),("map.numeric",b"geometry"),
                                 ("source/src/phys.c",b"physics"),("source/src/phys.h",b"physics header"),("stock_functions.inc",b"verified example\n"),
                                 ("AI/jkBotLily.inc",b'#include_next "AI/jkBotLily.inc"\n#include "bank_drive.inc"\n')):
                (build/name).write_bytes(content)
            files = runner.tree_files(build)
            provenance = dict(source_hashes={"src/phys.c":files["source/src/phys.c"]["sha256"]},
                              policy_hash="p",map_sha256="m", executable_sha256=files["replay"]["sha256"],
                              geometry_sha256=files["map.numeric"]["sha256"],compiler_flags_sha256=files["flags.make"]["sha256"])
            compiler = dict(version="offline compiler", path="/foreign/cc", sha256="3"*64)
            python = dict(version="offline interpreter",implementation="CPython",executable="/foreign/python",sha256="1"*64)
            hdr = dict(schema=1,run_id=runner.RUN_ID,declaration_sha256="d",implementation_commit="c",
                       started_at_utc="2025-11-01T00:00:00Z", initial_free_bytes=runner.FREE,
                       fixture_sources={},python=python,numpy="offline NumPy",build=dict(files=files,compiler=compiler,
                                                                                        provenance=provenance))
            runner.write(root/"run.json",hdr)
            decl = dict(implementation_commit="c", created_at_utc="2025-10-31T00:00:00Z", fixture_reference=provenance,
                        project_build_inputs_sha256={p:files[p]["sha256"] for p in ("source/src/phys.c","source/src/phys.h")})
            with (patch.object(runner,"fixture_sources",return_value={}),
                  patch.object(audit,"stock_functions",return_value="verified example\n")):
                self.assertEqual(audit.portable_header(root,decl,"d")["python"],python)
                private_header = build/"source/src/phys.h"
                with self.changed(private_header,b"changed header"):
                    hdr["build"]["files"] = runner.tree_files(build)
                    (root/"run.json").write_text(json.dumps(hdr))
                    with self.assertRaisesRegex(ValueError,"phys.h"):
                        audit.portable_header(root,decl,"d")
                (build/"stock_functions.inc").write_bytes(b"verified example\r\n")
                hdr["build"]["files"] = runner.tree_files(build)
                (root/"run.json").write_text(json.dumps(hdr))
                with self.assertRaisesRegex(ValueError,"stock functions"):
                    audit.portable_header(root,decl,"d")

    def test_setup_interruption_is_zero_attempts_and_rejects_orphan_claims(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("build","models","train"):
                (root/name).mkdir()
            (root/"build/map.numeric").write_text("partial")
            (root/"run.json.partial").write_text("{")
            decl = dict(fixture_reference=dict(source_hashes={}),
                        project_build_inputs_sha256={"source/src/phys.h":"f"*64})
            report = audit.before_run_header(root,decl,"d")
            self.assertEqual((report["status"],report["counts"]["attempted"]),("inconclusive",0))
            (root/"train/an-actual-attempt").mkdir()
            with self.assertRaisesRegex(ValueError,"inventory"):
                audit.before_run_header(root,decl,"d")

    def test_historical_v3_set_is_not_the_legacy_v2_criterion(self):
        decl = {k:{"path":v[0]} for k,v in runner.PRIOR_FILES.items()}
        _,_,winners = runner.history(decl)
        path = runner.ROOT/decl["historical_recovery"]["path"]
        legacy = runner.read(path)["criterion"]["historical_original_shaft_winners"]
        self.assertEqual(len(winners),24)
        self.assertEqual(set(winners)-set(legacy),{"boba-210.147-yaw90","boba-210.147-yaw180",
                                                   "boba-220.237-yaw180","lily-232.797-yaw180"})

    def test_abnormal_process_pairs_first_observation_in_either_ledger_order(self):
        from test_lily_outcome_rollouts import RolloutTests
        for failed_first in (False,True):
            for terminal in (False,True):
                with self.subTest(failed_first=failed_first,terminal=terminal), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    a,work,case,policy,model,proc = RolloutTests().fixture(root)
                    arms = []
                    for name in ("clean","failed"):
                        dest = root/name
                        shutil.copytree(work,dest)
                        arm = dict(a,work_dir=name,candidate_id=name)
                        (dest/"assignment.json").write_text(json.dumps(arm))
                        arms.append(arm)
                    failed = root/"failed"
                    (failed/"process.json").write_text(json.dumps(dict(proc,worker_returncode=7)))
                    if not terminal:
                        raw = (failed/"native.jsonl").read_bytes().splitlines(keepends=True)
                        (failed/"native.jsonl").write_bytes(b"".join(raw[:-1]))
                    if failed_first:
                        arms.reverse()
                    assigned = json.loads((failed/"native.jsonl").read_bytes().splitlines()[0])
                    edges = {assigned["sector"]:[assigned["seed"],runner.motor.digest(work/"start.json"),assigned["position"]]}
                    runner.write(root/"run.json",{})
                    header = dict(started_at_utc="2020-01-01T00:00:00Z",
                                  fixture_sources={"evaluator":{"native/tests/stock_water_replay/evaluate_motor.py":"x"}})
                    def pair():
                        recon = audit.Reconstruction(audit.Inventory(root),{},"d",{},header,edges,[])
                        starts = {}
                        return {arm["candidate_id"]:recon.attempt(root,arm,case,(policy,model),starts) for arm in arms}
                    self.assertEqual(pair()["failed"]["reason"],"abnormal_process")
                    # A harmless lexical change yields different observed bytes. The worker
                    # genuinely saw the changed line and its journal still matches exactly.
                    trace = failed/"motor.jsonl"
                    first,*tail = trace.read_bytes().splitlines(keepends=True)
                    first = b" "+first
                    trace.write_bytes(first+b"".join(tail))
                    journal = failed/"decisions.jsonl"
                    journal.write_text(json.dumps(dict(runner.read(journal),observation_sha256=runner.trial.prior.sha(first)))+"\n")
                    with self.assertRaisesRegex(ValueError,"different actual starts"):
                        pair()

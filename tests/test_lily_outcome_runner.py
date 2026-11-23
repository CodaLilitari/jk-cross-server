"""The outcome ledger controls dispatch, batch coverage and the sealed gate."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from scripts.bot_development.analysis import run_outcome_learning as run


class RunnerTests(unittest.TestCase):
    def test_single_declared_output_and_stage_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            with self.assertRaises(ValueError):
                run.canonical_output("lily-outcome-learning-20261122-01", p)
            run.claim(p/"train")
            with self.assertRaises(FileExistsError):
                run.claim(p/"train")

    def test_wrong_case_role_and_digest_rejected(self):
        good = {"path":"native/tests/stock_water_replay/bank_cases.tsv"}
        with self.assertRaisesRegex(ValueError, "role"):
            run.load_bank("stress", good)
        with self.assertRaisesRegex(ValueError, "identity"):
            run.load_bank("original", dict(good, sha256="0"*64))

    def test_one_censor_stops_dispatch_and_counts_every_assignment(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"block"
            assignments = [{"work_dir":str(i)} for i in range(6)]
            seen = []
            def attempt(a, work):
                self.assertTrue((work/"assignment.json").is_file())
                seen.append(a["work_dir"])
                return dict(status="censored", row=None)
            with self.assertRaises(run.BlockStopped):
                run.dispatch(path, assignments, 1, attempt)
            self.assertEqual(seen, ["0"])
            block = run.read(path/"block.json")
            self.assertEqual(block["counts"], dict(assigned=6, attempted=1, completed=0, wins=0,
                                                  failed=0, censored=1, invalid=0, unrun=5))
            self.assertEqual([a["status"] for a in block["attempts"]], ["censored"]+["unrun"]*5)
            with self.assertRaises(FileExistsError):
                run.dispatch(path, assignments, 1, attempt)
            self.assertEqual(seen, ["0"])

    def test_all_13_candidate_banks_have_identical_order_and_case_job(self):
        spec = {"path":"native/tests/stock_water_replay/bank_cases.tsv"}
        spec["sha256"] = run.motor.digest(run.ROOT/spec["path"])
        import csv
        with (run.ROOT/spec["path"]).open() as f:
            rows = list(csv.DictReader(f, delimiter="\t"))
        spec["episode_ids"] = [j["episode_id"] for j in run.motor.make_jobs(rows, ["every_tick"], True)]
        bank = run.load_bank("original", spec)
        names = [f"g01-c{i:02d}" for i in range(13)]
        ids = spec["episode_ids"][2:10]
        assignments = run.assignments("g01", bank, ids, dict.fromkeys(names, {"model_sha256":"fixed"}), {})
        self.assertEqual([(a["candidate_id"],a["job"]["episode_id"]) for a in assignments],
                         [(n,i) for n in names for i in ids])
        self.assertEqual(len({a["work_dir"] for a in assignments}), 104)

    def test_no_selection_cannot_open_evaluation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            freeze = dict(selected=None, model=None)
            opener = Mock(side_effect=AssertionError("opened held-out bank"))
            with self.assertRaisesRegex(ValueError, "selected"):
                run.evaluate_blocks(root, {}, {}, freeze, opener)
            opener.assert_not_called()
            self.assertFalse((root/"evaluate").exists())

    def test_training_stops_on_first_incomplete_generation_and_keeps_exact_parent_bytes(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            run.claim(output/"models")
            run.claim(output/"train")
            parent = run.ROOT/run.PARENT["model"]
            binding = dict(run_sha256="a"*64, declaration_sha256="b"*64)
            bank = {"ids": ["e"+str(i) for i in range(8)]}
            seen = []
            def interrupted(o, stage, label, b, ids, refs, bind, edges, workers):
                seen.append(label)
                self.assertEqual(list(refs), [f"g01-c{i:02d}" for i in range(13)])
                self.assertEqual((o/"models/g01-c00/model.json").read_bytes(), parent.read_bytes())
                self.assertEqual(ids, bank["ids"])
                self.assertEqual(bind["predecessor_sha256"], binding["run_sha256"])
                raise run.BlockStopped("one genuine censor")
            with patch.object(run,"run_block",interrupted), self.assertRaises(run.BlockStopped):
                run.train_generations(output, {"training_batches":[bank["ids"]]*8}, {"train":bank}, binding, {}, 1)
            self.assertEqual(seen, ["g01"])
            self.assertFalse((output/"training.json").exists())
            self.assertFalse((output/"models/g02-c00").exists())

    def test_inflight_sibling_is_preserved_and_unstarted_tail_stays_unrun(self):
        import threading
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"test"
            both = threading.Barrier(2)
            ledger = [dict(work_dir=str(i)) for i in range(4)]
            def attempt(a, work):
                both.wait(5)
                if a["work_dir"]=="0":
                    return dict(status="censored",row=None)
                import time
                time.sleep(.08)
                return dict(status="complete",row=dict(physical_success=True))
            with self.assertRaises(run.BlockStopped):
                run.dispatch(path, ledger, 2, attempt)
            block = run.read(path/"block.json")
            self.assertEqual([a["status"] for a in block["attempts"]],["censored","complete","unrun","unrun"])
            self.assertEqual((block["counts"]["assigned"],block["counts"]["attempted"],block["counts"]["wins"]),(4,2,1))

    def test_measured_development_freeze_precedes_sealed_then_three_diagnostic_pairs(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            run.write(out/"training.json",{})
            ids = [f"i{i}" for i in range(32)]
            bank = dict(ids=ids, jobs={(i,"every_tick"):dict(target_sector=10 if n<24 else 41) for n,i in enumerate(ids)})
            checkpoints = {k:dict(artifact=k) for k in ("v3","g4","g8")}
            binding = dict(run_sha256="a"*64,declaration_sha256="b"*64)
            blocks = []
            def dev(o,stage,label,b,actual_ids,refs,bind,edges,workers):
                self.assertEqual(actual_ids, ids)
                self.assertEqual(list(refs), ["v3","g4","g8"])
                def row(i, win):
                    return dict(episode_id=i,owner="model",controller="every_tick",ownership_complete=True,
                                baseline_assisted=False,physical_success=win,physics_steps=46,
                                terminal="supported_dry" if win else "died")
                return {}, {k:[row(i,n>=24 or (k=="g4" and n==0)) for n,i in enumerate(ids)] for k in refs}
            with patch.object(run,"run_block",dev):
                freeze = run.development(out,bank,binding,{},checkpoints,1)
            self.assertEqual(freeze["selected"],"g4")
            frozen = run.motor.digest(out/"freeze.json")
            def opened(o,stage,label,b,ids,refs,bind,edges,workers):
                self.assertEqual(run.read(o/"freeze.json")["model"], checkpoints["g4"])
                self.assertEqual(bind["predecessor_sha256"], blocks[-1][2] if blocks else frozen)
                blocks.append((label,list(refs),label+"-digest"))
                return dict(sha256=blocks[-1][2]), {}
            run.evaluate_blocks(out, {b:bank for b in ("sealed",*run.DIAGNOSTIC)},
                                dict(binding=binding,edges={},winners=[],workers=1),freeze,opened)
            self.assertEqual([x[:2] for x in blocks], [("sealed",["v3","selected","native"]),
                             *((k,["v3","selected"]) for k in run.DIAGNOSTIC)])

    def test_run_refuses_orphan_stage_receipts_before_launch(self):
        from unittest.mock import patch
        for stage, names in (("select",("selection.json","freeze.json","selection.json.partial","freeze.json.partial",
                                        "evaluate","previous-select")),
                             ("evaluate",("evaluation.json","evaluation.json.partial","previous-evaluate"))):
            for orphan in names:
                with self.subTest(stage=stage, orphan=orphan), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    for d in ("train","build","models"):
                        (root/d).mkdir()
                    for f in ("run.json","training.json"):
                        run.write(root/f,{})
                    for g in range(1,9):
                        (root/"train"/f"g{g:02d}").mkdir()
                    if stage == "evaluate":
                        (root/"select"/"development").mkdir(parents=True)
                        for f in ("selection.json","freeze.json"):
                            run.write(root/f,{})
                    if "." in orphan:
                        (root/orphan).touch()
                    else:
                        (root/orphan).mkdir()
                    launch = Mock(side_effect=AssertionError("physical launcher reached"))
                    bank = dict(ids=[])
                    hdr = {"fixture_sources":{"evaluator":{"native/tests/stock_water_replay/evaluate_motor.py":"a"}}}
                    with (patch.object(run,"canonical_output",return_value=root),
                          patch.object(run,"declaration",return_value=({},"d",{"development":bank,"sealed":bank})),
                          patch.object(run,"history",return_value=(None,{},[])),
                          patch.object(run,"verify_header",return_value=hdr),
                          patch.object(run,"train_generations",return_value={"checkpoints":{}}),
                          patch.object(run,"open_block",return_value=({},{})),
                          patch.object(run,"development",side_effect=run.development if stage=="select" else None,
                                       return_value={"selected":"g4","model":{}}),
                          patch.object(run,"run_block",launch),
                          self.assertRaisesRegex(ValueError,"inventory")):
                        run.run(stage, root/"decl.json", root, 1)
                    launch.assert_not_called()

    def test_completed_block_refuses_extra_physical_attempt_directory(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            blockdir = root/"select/development"
            blockdir.mkdir(parents=True)
            job = dict(episode_id="e",controller="baseline",case="pose", target_sector=41)
            bank = dict(role="development",sha256="digest",jobs={("e","baseline"):job},cases={"pose":{}})
            refs = {"native":None}
            ledger = run.assignments("development",bank,["e"],refs,{})
            result = dict(status="complete",row=dict(job,seed=1,origin_sha256="o",target_position=[1,2,3],
                                                      initial_observation_sha256="s",physical_success=False))
            (blockdir/ledger[0]["work_dir"]).mkdir()
            run.write(blockdir/"assignments.json",ledger)
            run.write(blockdir/"block.json",dict(attempts=[result],counts=run.counts_for([result]),
                                                assignments_sha256=run.motor.digest(blockdir/"assignments.json")))
            args = (root,"select","development",bank,["e"],refs,{}, {41:[1,"o",[1,2,3]]})
            with patch.object(run.trial,"audit_attempt",return_value=result):
                run.open_block(*args)
                other = blockdir/"foreign--e"
                other.mkdir()
                run.write(other/"assignment.json",dict(ledger[0],candidate_id="foreign"))
                run.write(other/"process.json",dict(engine_returncode=0))
                with self.assertRaisesRegex(ValueError,"inventory"):
                    run.open_block(*args)

    def test_evaluate_rejects_stopped_stage_hidden_inside_model_inventory(self):
        from unittest.mock import patch
        for location in ("models/previous-evaluate", "models/g08-c12/previous-evaluate"):
            with self.subTest(location=location), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                for name in ("build","models","train","select/development"):
                    (root/name).mkdir(parents=True)
                for name in ("run","training","selection","freeze"):
                    run.write(root/(name+".json"),{})
                for g in range(1,9):
                    (root/"train"/f"g{g:02d}").mkdir()
                for name in ["v3", *(f"g{g:02d}-c{i:02d}" for g in range(1,9) for i in range(13))]:
                    (root/"models"/name).mkdir()
                    for member in ("model.json","policy.py"):
                        (root/"models"/name/member).touch()
                run.stage_inventory(root,"evaluate")
                used = root/location/"sealed/selected--e"
                used.mkdir(parents=True)
                run.write(used/"assignment.json",{"job":"sealed"})
                run.write(used/"process.json",{"engine_returncode":0})
                launch = Mock(side_effect=AssertionError("physical launcher reached"))
                hdr = {"fixture_sources":{"evaluator":{"native/tests/stock_water_replay/evaluate_motor.py":"x"}}}
                with (patch.object(run,"canonical_output",return_value=root),
                      patch.object(run,"declaration",return_value=({},"d",{"development":{},"sealed":{"ids":[]}})),
                      patch.object(run,"history",return_value=(None,{},[])),
                      patch.object(run,"verify_header",return_value=hdr),
                      patch.object(run,"train_generations",return_value={"checkpoints":{}}),
                      patch.object(run,"development",return_value={"selected":"g4","model":{}}),
                      patch.object(run,"run_block",launch),
                      self.assertRaisesRegex(ValueError,"inventory")):
                    run.run("evaluate",root/"decl",root,1)
                launch.assert_not_called()

    def test_unfinished_process_publication_blocks_predecessor_and_launch(self):
        from test_lily_outcome_rollouts import RolloutTests
        from unittest.mock import patch
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a,work,case,policy,model,_ = RolloutTests().fixture(root)
            job = a["job"]
            ids = [job["episode_id"]]
            bank = dict(role="development",ids=ids,sha256="a"*64,jobs={(ids[0],"every_tick"):job},cases={job["case"]:case})
            refs = {"g4":dict(artifact="v3",**a["model"])}
            run.write(root/"run.json",{})
            run.write(root/"training.json",{})
            binding = dict(run_id=run.RUN_ID,declaration_sha256="d",run_sha256=run.motor.digest(root/"run.json"),
                           fixture_source_sha256=a["fixture_source_sha256"])
            ledger = run.assignments("development",bank,ids,{"g4":a["model"]},
                                     run.bound(binding,run.motor.digest(root/"training.json")))
            block = root/"select/development"
            block.mkdir(parents=True)
            work = work.rename(block/ledger[0]["work_dir"])
            (work/"assignment.json").unlink()
            run.write(work/"assignment.json",ledger[0])
            result = run.trial.audit_attempt(ledger[0],work,case,policy,model)
            edges = {job["target_sector"]:[result["row"][key] for key in ("seed","origin_sha256","target_position")]}
            run.write(block/"assignments.json",ledger)
            shutil.copyfile(work/"process.json",work/"process.json.partial")
            result["raw"]["process.json.partial"] = result["raw"]["process.json"]
            run.write(block/"block.json",dict(attempts=[result],counts=run.counts_for([result]),
                                             assignments_sha256=run.motor.digest(block/"assignments.json")))
            launch = Mock(side_effect=AssertionError("physical launcher reached"))
            # Publish a self-consistent selection/freeze over this one-row stand-in.
            # The evaluate entry must still re-open the actual predecessor's raw bytes.
            ref = run.link(root,"select/development/block.json")
            hdr = {"fixture_sources":{"evaluator":{"native/tests/stock_water_replay/evaluate_motor.py":a["fixture_source_sha256"]}}}
            with patch.object(run.search,"select_development",return_value={"selected":"g4","policies":{}}):
                with patch.object(run,"run_block",return_value=(ref,{"g4":[result["row"]]})):
                    run.development(root,bank,binding,edges,refs,1)
                with (patch.object(run,"canonical_output",return_value=root),patch.object(run,"stage_inventory"),
                      patch.object(run,"declaration",return_value=({},"d",{"development":bank,"sealed":bank})),
                      patch.object(run,"history",return_value=(None,edges,[])),patch.object(run,"verify_header",return_value=hdr),
                      patch.object(run,"train_generations",return_value={"checkpoints":refs}),
                      patch.object(run,"check_model",return_value=(policy,model)),patch.object(run,"run_block",launch),
                      self.assertRaisesRegex(ValueError,"saved attempt disagrees with raw evidence")):
                    run.run("evaluate",root/"decl",root,1)
            launch.assert_not_called()
            self.assertFalse((root/"evaluate").exists())

    def test_dispatch_leaves_block_unpublished_on_incomplete_process_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            block = Path(tmp)/"block"
            with self.assertRaises(run.BlockStopped):
                run.dispatch(block,[dict(work_dir="arm")],1,lambda a,w:
                             dict(status="censored",row=None,reason="unpublished_process_witness"))
            self.assertFalse((block/"block.json").exists())
            self.assertTrue((block/"arm/assignment.json").is_file())

    def test_project_header_change_rejects_build_before_any_physical_launch(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source,config,out = [root/name for name in ("engine","configured","run")]
            out.mkdir()
            (source/"src/Primitives").mkdir(parents=True)
            (config/"CMakeFiles/sith_engine.dir").mkdir(parents=True)
            flags = config/"CMakeFiles/sith_engine.dir/flags.make"
            flags.write_text("flags")
            header = source/"src/Primitives/rdMath.h"
            header.write_text("expected types")
            decl = dict(project_build_inputs_sha256={"source/src/Primitives/rdMath.h":run.motor.digest(header)},
                        fixture_reference={"source_hashes":{},"compiler_flags_sha256":run.motor.digest(flags)})
            header.write_text("new physics")
            compile_replay = Mock(side_effect=AssertionError("compiler reached changed source"))
            with patch.object(run.motor,"build_replay",compile_replay), self.assertRaisesRegex(ValueError,"rdMath.h"):
                run.make_build(out,source,config,root/"owned.jkl",decl)
            compile_replay.assert_not_called()

    def test_compiler_prerequisites_must_match_declared_project_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work,configured = root/"private",root/"configured"
            project = work/"source/src/math.h"
            configured_header = configured/"generated/globals.h"
            includes = [work/name for name in sorted(run.inputs.GENERATED)]
            for path in [project,configured_header,*includes]:
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(path.name)
            expected = {"source/src/math.h":run.motor.digest(project),
                        "configured/generated/globals.h":run.motor.digest(configured_header)}
            decl = dict(project_build_inputs_sha256=expected,fixture_reference=dict(source_hashes={}))
            deps = root/"deps.mk"
            def emit(paths):
                records = [name+": "+" ".join(str(p) for p in paths) for name in sorted(run.inputs.OBJECTS)]
                deps.write_text("\n".join(records)+"\n")
            paths = [project,configured_header,*includes]
            emit(paths)
            run.inputs.verify_compilation(deps,work,configured,decl)
            extra = configured_header.with_name("extra.h")
            extra.write_text("unbound")
            emit([*paths,extra])
            with self.assertRaisesRegex(ValueError,"unbound external project input"):
                run.inputs.verify_compilation(deps,work,configured,decl)
            emit([project,*includes])
            with self.assertRaisesRegex(ValueError,"declared project/actual"):
                run.inputs.verify_compilation(deps,work,configured,decl)

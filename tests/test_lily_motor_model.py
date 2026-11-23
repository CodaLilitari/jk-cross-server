"""Motor-model contracts; synthetic cases here are unit evidence, not gameplay."""
import copy
import importlib.util
import json
import math
from pathlib import Path
import tempfile
import unittest

from bots.lily.motor_model import FEATURES, OUTPUTS, features, predict, validate_model
from bots.lily.train_motor import dataset, fit, split_episodes
from bots.lily.export_motor_policy import policy_source


def sample(goal=None):
    return {"sense": {"position": [0, 0, 0], "velocity": [.1, .2, -.1],
        "facing": [1, 0, 0], "up": [0, 0, 1], "head_pitch": 20,
        "supported": 0, "medium": "water", "breath_used_ms": 5000,
        "tick_ms": 33.333, "axes": [.5, 0, -.2, .4], "buttons": 1,
        "action_seq": 11, "revision": 0xaaaaaaaa, "owner_sample_id": 7, "owner":"motor", "phase":"running"},
        "state": {"health": 80, "shields": 70, "mana": 300},
        "goal": goal or {"direction": [1, .5, .25], "distance": .3}}


def constant_model():
    return {"schema": 1, "feature_names": list(FEATURES), "output_names": list(OUTPUTS),
        "normalization": {"mean": [0.] * len(FEATURES), "scale": [1.] * len(FEATURES)},
        "w1": [[0.] * len(FEATURES)], "b1": [0.],
        "w2": [[0.] for _ in OUTPUTS], "b2": [.25, -.5, 0., .75, 2., -2.],
        "provenance": {"fixture": "synthetic unit test"}}


class MotorModelTests(unittest.TestCase):
    def test_relative_features_do_not_depend_on_world_rotation(self):
        a = sample()
        b = copy.deepcopy(a)
        rotate = lambda v: [-v[1], v[0], v[2]]
        for name in ("position", "velocity", "facing", "up"):
            b["sense"][name] = rotate(b["sense"][name])
        b["goal"]["direction"] = rotate(b["goal"]["direction"])
        for x, y in zip(features(**{k:a[k] for k in ("sense", "state", "goal")}),
                        features(**{k:b[k] for k in ("sense", "state", "goal")})):
            self.assertAlmostEqual(x, y)

    def test_nonfinite_and_wrong_contract_models_are_rejected(self):
        bad = constant_model(); bad["w1"][0][0] = float("nan")
        with self.assertRaises(ValueError): validate_model(bad)
        bad = constant_model(); bad["feature_names"].reverse()
        with self.assertRaises(ValueError): validate_model(bad)
        bad = constant_model(); bad["normalization"]["scale"][0] = 0
        with self.assertRaises(ValueError): validate_model(bad)

    def test_inference_is_bounded_and_exported_policy_uses_same_weights(self):
        model = constant_model(); row = sample()
        expected = predict(model, features(row["sense"], row["state"], row["goal"]))
        self.assertAlmostEqual(expected[0], math.tanh(.25))
        scope = {}; exec(compile(policy_source(model), "generated-policy", "exec"), scope)
        observation = {"lily": {"sense": row["sense"]}, "state": row["state"]}
        endpoint = [d*.3/math.hypot(*row["goal"]["direction"]) for d in row["goal"]["direction"]]
        context = {"undertaking": None, "directive": {"goal": "learned-motor",
            "parameters": {"position":endpoint, "duration_ms":300}}}
        result = scope["decide"](observation, context)
        self.assertEqual(result["action"], "motor")
        for name, value in zip(OUTPUTS[:4], expected[:4]):
            self.assertAlmostEqual(result["steps"][0][name], value)
        self.assertEqual(result["steps"][0]["buttons"], 1)
        row["sense"]["position"] = list(endpoint)
        self.assertEqual(scope["decide"](observation, context), {"action":"wait"})
        row["sense"]["position"][0] -= .1
        next_goal = scope["decide"](observation, context)["goal"]
        self.assertAlmostEqual(next_goal["distance"], .1)
        self.assertEqual(next_goal["direction"], [1.,0.,0.])
        self.assertEqual(scope["decide"](observation, {"undertaking": {"action_seq": 3}}), {"action": "wait"})
        self.assertEqual(scope["decide"](observation, {"undertaking": None})["action"], "baseline")

    def test_bank_export_uses_frozen_task_target_and_releases_on_latch(self):
        scope = {}
        exec(compile(policy_source(constant_model()), "generated-policy", "exec"), scope)
        row = sample()
        obs = dict(lily={"sense": row["sense"]}, state=row["state"])
        directive = dict(goal="escape-bank", parameters={"position": [-3., 0., 0.]})
        context = dict(directive=directive)
        self.assertEqual(scope["decide"](obs, context), {"action": "baseline"})
        task = dict(task_id="a"*64, position=[.5, 0., 0.], sector=41, budget_seconds=60, status="active")
        context["bank_task"] = task
        action = scope["decide"](obs, context)
        self.assertEqual((action["task_id"], action["goal"]["direction"], action["steps"][0]["duration_ms"]),
                         (task["task_id"], [1., 0., 0.], 550))
        task["status"] = "closed"
        context["undertaking"] = {"action_seq": 7}
        self.assertEqual(scope["decide"](obs, context), {"action": "baseline"})

    def test_dataset_excludes_censored_and_unattributed_controls(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "trace.jsonl"
            records=[]
            def pair(episode, seq=11, success=True):
                common = dict(schema=1, episode_id=episode, policy_hash="a"*64,
                              run_id="unit-run", world_epoch=1, life_epoch=2)
                observation = dict(common, event="observation", **sample())
                observation["goal"].update(position=[1.,0.,0.])
                observation["sense"]["action_seq"] = seq
                records.append(dict(common,event="attempt",action_seq=seq,revision=0xaaaaaaaa,sample_id=7,kind="motor"))
                return observation, dict(common,event="outcome",action_seq=seq,
                                         physical_success=success,status="motor_goal_reached")
            valid,terminal=pair("unit-run/1/2/11")
            records.extend([valid,terminal])
            for idx,field in enumerate(("action_seq","policy_hash","run_id","world_epoch","life_epoch"),12):
                sample_row,terminal = pair(f"unit-run/1/2/{idx}",idx)
                terminal.pop(field)
                records.extend([sample_row,terminal])
            for idx,seq in enumerate((None,True,"0",0),20):
                records.extend(pair(f"invalid-{idx}",seq))
            censored,failed = pair("unit-run/1/2/30",30,None),pair("unit-run/1/2/31",31,False)
            records.extend([*censored,*failed])
            old,end=pair("unit-run/1/2/32",32)
            del old["goal"]["position"]
            records.extend([old,end])
            for field, bad in (("action_seq",12),("revision",1),("owner_sample_id",8),
                               ("owner_sample_id",True),("revision",None)):
                mismatch=copy.deepcopy(valid)
                mismatch["sense"][field]=bad
                records.append(mismatch)
            # Deliberately stale repeated relative goal must be recomputed from
            # the fixed endpoint after movement (distance scaled by two).
            later=copy.deepcopy(valid)
            later["sense"]["position"]=[.6,0.,0.]
            records.append(later)
            path.write_text("\n".join(json.dumps(row) for row in records))
            loaded=dataset([path])
            self.assertEqual([r["episode_id"] for r in loaded], ["unit-run/1/2/11"]*2)
            self.assertAlmostEqual(loaded[0]["features"][3],.5)
            self.assertAlmostEqual(loaded[1]["features"][3],.2)
            self.assertEqual(loaded[0]["target"][-2:], [1.,0.])

    def test_export_order_independent_and_nonfinite_normalization_rejected(self):
        model=constant_model()
        restored=json.loads(json.dumps(model,sort_keys=True))
        self.assertEqual(policy_source(model).encode(),policy_source(restored).encode())
        scope={"__name__":"policy"}
        exec(policy_source(model),scope)
        model["normalization"]["mean"][0]=1e308
        model["normalization"]["scale"][0]=1e-308
        with self.assertRaises(ValueError):
            predict(model,[0.]*len(FEATURES))
        with self.assertRaises(ValueError):
            scope["predict"](model,[0.]*len(FEATURES))

    def test_checked_in_candidate_regenerates_exact_bytes(self):
        lily=Path(__file__).resolve().parents[1]/"bots"/"lily"
        weights=json.loads((lily/"models"/"water_bc_v1.json").read_bytes())
        self.assertEqual((lily/"policies"/"water_bc_v1.py").read_bytes(), policy_source(weights).encode())

    def test_only_tagged_stock_replay_may_use_the_sequence_zero_contract(self):
        sample_row=sample()
        common=dict(schema=1,episode_id="a-yaw0",run_id="stock-water-replay",
                    world_epoch=1,life_epoch=1,policy_hash="b"*64)
        row=dict(common,event="observation",controller="native-baseline",**sample_row)
        row["sense"].update(owner="baseline",phase="running",action_seq=0)
        terminal=dict(common,event="outcome",action_seq=0,status="completed",physical_success=True,
                      criterion="38 consecutive supported dry physics steps")
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"replay.jsonl"
            def count(observed,end):
                path.write_text(json.dumps(observed)+"\n"+json.dumps(end))
                return len(dataset([path]))
            self.assertEqual(count(row,terminal),1)
            self.assertEqual(count(row|{"controller":None},terminal),0)
            self.assertEqual(count(row,terminal|{"run_id":"other"}),0)
            self.assertEqual(count(row,terminal|{"world_epoch":True}),0)
            self.assertEqual(count(row|{"policy_hash":None},terminal),0)
            self.assertEqual(count(row|{"sense":row["sense"]|{"phase":"idle"}},terminal),0)

    def test_holdout_keeps_whole_episodes_separate(self):
        rows = [{"episode_id":str(i//4),"features":[0]*len(FEATURES),"target":[0]*len(OUTPUTS)} for i in range(20)]
        train, held = split_episodes(rows, .4, 17)
        self.assertTrue(train); self.assertTrue(held)
        self.assertFalse({x["episode_id"] for x in train} & {x["episode_id"] for x in held})
        with self.assertRaises(ValueError): split_episodes(rows[:4], .2, 17)

    def test_related_demonstrations_stay_in_one_split(self):
        rows=[{"episode_id":str(i),"split_group":str(i//4)} for i in range(12)]
        train,held=split_episodes(rows,.3,9)
        self.assertFalse({r["split_group"] for r in train}&{r["split_group"] for r in held})
        with self.assertRaises(ValueError):
            split_episodes([*rows,{"episode_id":"0","split_group":"new"}],.3,9)

    @unittest.skipUnless(importlib.util.find_spec("numpy"), "optional training dependency")
    def test_trained_artifact_improves_held_out_action_fit(self):
        rows=[]
        for episode in range(6):
            for index in range(16):
                x = (index-7.5)/7.5
                vector=[0.]*len(FEATURES); vector[0]=x
                rows.append({"episode_id":str(episode),"features":vector,
                             "target":[.6*x,0,0,0,float(x>0),float(x<0)]})
        model, metrics = fit(rows, epochs=80, hidden=8, seed=3)
        validate_model(model)
        self.assertLess(metrics["heldout_axis_mse"], metrics["initial_heldout_axis_mse"])
        self.assertLess(metrics["heldout_axis_mse"], .025)
        self.assertEqual(len(metrics["train_episode_ids"])+len(metrics["heldout_episode_ids"]),6)


if __name__ == "__main__":
    unittest.main()

"""The contact experiment requires two explicitly measured pre-action inputs."""
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from bots.lily import motor_contact, motor_model, train_contact_motor

LILY = Path(__file__).resolve().parents[1] / "bots" / "lily"


def observation(tick, previous):
    return {"event": "observation", "tick": tick, "step": tick * 6,
            "goal": {"sector": 41, "position": [1., 0., .2]}, "sector": 54,
            "physics_flags": 0x100000, "state": {"health": 90, "shields": 0, "mana": 400},
            "sense": {"position": [0, 0, 0], "velocity": [.2, .1, 0], "facing": [1, 0, 0],
                      "up": [0, 0, 1], "head_pitch": 0, "medium": "water", "supported": False,
                      "tick_ms": 40, "breath_used_ms": 1, "on_water_surface": True, "buttons": previous}}


def network():
    hidden = 32
    width = len(motor_contact.FEATURES)
    model = {"schema": 2, "feature_names": list(motor_contact.FEATURES),
             "output_names": list(motor_model.OUTPUTS),
             "normalization": {"mean": [0.] * width, "scale": [1.] * width},
             "w1": [[0.] * width for _ in range(hidden)], "b1": [0.] * hidden,
             "w2": [[0.] * hidden for _ in range(6)], "b2": [0.] * 6}
    model["w1"][0][-2:] = [1., -1.]
    model["w2"][0][0] = 1.
    return model


class ContactMotorTests(unittest.TestCase):
    def test_two_added_observations_and_standalone_policy_parity(self):
        model = network()
        scope = {}
        exec(motor_contact.policy_source(model), scope)
        for previous in (0, 1, 2, 3):
            row = observation(1, previous)
            sense, state = row["sense"], row["state"]
            goal = motor_model.remaining_goal(sense["position"], row["goal"]["position"])
            values = motor_contact.features(sense, state, goal)
            self.assertEqual(values, motor_model.features(sense, state, goal) + [1., float(previous & 1)])
            expected = motor_contact.predict(model, values)
            self.assertAlmostEqual(expected[0], math.tanh(math.tanh(1. - (previous & 1))))
            obs = {"state": state, "lily": {"sense": sense}}
            ctx = {"directive": {"goal": "learned-motor", "parameters": {"position": row["goal"]["position"]}}}
            step = scope["decide"](obs, ctx)["steps"][0]
            self.assertEqual([step[k] for k in motor_model.OUTPUTS[:4]], expected[:4])
            self.assertEqual(step["buttons"], 3)
            self.assertEqual(scope["ABI_VERSION"], 1)
            for name, bad in (("on_water_surface", 1), ("buttons", True), ("buttons", 32)):
                for missing in (True, False):
                    broken = copy.deepcopy(obs)
                    if missing:
                        del broken["lily"]["sense"][name]
                    else:
                        broken["lily"]["sense"][name] = bad
                    with self.assertRaisesRegex(ValueError, name):
                        scope["decide"](broken, ctx)

    def test_frozen_experimental_weights_regenerate_the_standalone_policy(self):
        model_path = LILY / "models" / "water_contact_v2.json"
        policy_path = LILY / "policies" / "water_contact_v2.py"
        model = json.loads(model_path.read_bytes())
        self.assertEqual(motor_contact.canonical(model) + b"\n", model_path.read_bytes())
        self.assertEqual(motor_contact.policy_source(model).encode(), policy_path.read_bytes())
        self.assertEqual(model["provenance"]["train_samples"], 3431)
        self.assertEqual(len(model["provenance"]["training_sources"]), 22)
        self.assertEqual((model["provenance"]["hidden"], model["provenance"]["seed"]), (32, 23))

    def test_rejects_wrong_dimensions_and_unphysical_parameters(self):
        for field, bad in (("b1", [0.] * 31), ("w1", [[0.] * 15] * 32),
                           ("b2", [float("nan")] * 6), ("schema", 1)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                motor_contact.policy_source(network() | {field: bad})

    def test_pose_identities_come_from_immutable_original_split(self):
        split = train_contact_motor.original_split()
        self.assertEqual(len(split["train_episode_ids"]), 22)
        self.assertEqual(len(split["train_split_groups"]), 7)
        self.assertEqual(set(split["heldout_split_groups"]), {"lily-232.797", "pool-100"})
        self.assertFalse(set(split["train_episode_ids"]) & set(split["heldout_episode_ids"]))
        self.assertEqual(hashlib.sha256((LILY/"models"/"water_bc_v1.json").read_bytes()).hexdigest(),
                         train_contact_motor.V1_FILE_SHA256)

    def test_missing_history_cannot_be_replaced_with_current_label(self):
        obs = [observation(0, 0), observation(1, 1)]
        inputs = [dict(event="input", tick=i, step=i * 6, owner="baseline", source_tick=i,
                       axes=[.25, 0., 0., 0.], buttons=mask, presses=mask)
                  for i, mask in enumerate((1, 2))]
        control = [dict(row, event="control", wet=True) for row in inputs]
        native = [dict(event="assigned", **obs[0]["goal"]), *control,
                  dict(event="terminal", terminal="supported_dry", ticks=2, step=42,
                       sector=41, health=90., dry_steps=38)]
        def read():
            frames = [part for pair in zip(obs, inputs) for part in pair]
            return train_contact_motor.baseline_rows(frames, native)
        rows = read()
        self.assertEqual([r["features"][-1] for r in rows], [0., 1.])
        self.assertEqual([r["target"][-2:] for r in rows], [[1., 0.], [0., 1.]])
        obs[1]["sense"]["buttons"] = 2
        with self.assertRaises(ValueError): read()
        obs[1]["sense"]["buttons"] = 1
        obs[1]["sense"]["on_water_surface"] = False
        with self.assertRaises(ValueError): read()
        obs[1]["sense"]["on_water_surface"] = True
        inputs[1]["owner"] = "model"
        with self.assertRaises(ValueError): read()
        inputs[1]["owner"] = "baseline"
        native[-1]["terminal"] = "sim_timeout"
        with self.assertRaises(ValueError): read()

    def test_training_loader_binds_source_hashes_and_skips_development_files(self):
        obs = observation(0, 0)
        applied = dict(event="input", tick=0, step=0, owner="baseline", source_tick=0,
                       axes=[0.] * 4, buttons=2, presses=2)
        native = [dict(event="assigned", **obs["goal"]), dict(applied, event="control", wet=True),
                  dict(event="terminal", terminal="supported_dry", ticks=1, step=42,
                       sector=41, health=90., dry_steps=38)]
        split = dict(train_episode_ids=["a-yaw0"], train_split_groups=["a"], train_samples=1,
                     heldout_split_groups=["b"], heldout_episode_ids=["b-yaw0"])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            loc = root / "a-yaw0-baseline"
            loc.mkdir()
            def trace(name, records):
                data = b"".join(json.dumps(r).encode() + b"\n" for r in records)
                (loc / name).write_bytes(data)
                return hashlib.sha256(data).hexdigest()
            orig = dict(episode_id="a-yaw0", case="a", yaw_deg=0, controller="baseline",
                        native_sha256=trace("native.jsonl", native))
            current = dict(orig, motor_sha256=trace("motor.jsonl", [obs, applied]),
                           ownership_complete=True, physical_success=True, terminal="supported_dry")
            development = dict(current, episode_id="b-yaw0", case="b")
            ref = root / "reference.json"
            ref.write_text(json.dumps({"episodes": [orig]}))
            def collect(records):
                (root / "receipt.json").write_text(json.dumps({"episodes": records}))
                with mock.patch.object(train_contact_motor, "REFERENCE", ref), mock.patch.object(
                        train_contact_motor, "original_split", return_value=split):
                    return train_contact_motor.training_rows(root)
            rows, provenance = collect([development, current])
            self.assertEqual(len(rows), 1)
            self.assertEqual(provenance["development_split_groups"], ["b"])
            self.assertEqual([x["episode_id"] for x in provenance["training_sources"]], ["a-yaw0"])
            for records in ([current, current], [development], [dict(current, case="b")],
                            [dict(current, yaw_deg=True)], [dict(current, native_sha256="0"*64)],
                            [dict(current, motor_sha256="0"*64)], [dict(current, ownership_complete=False)]):
                with self.subTest(records=records), self.assertRaises(ValueError):
                    collect(records)

    @unittest.skipUnless(importlib.util.find_spec("numpy"), "optional training dependency")
    def test_fixed_optimizer_receives_only_training_inputs(self):
        row = {"features": [1.] * 17, "target": [0.] * 6}
        with mock.patch.object(train_contact_motor, "training_rows", return_value=([row], {})), mock.patch.object(
                train_contact_motor, "fit_weights", return_value=({}, None, None)) as optimizer:
            model = train_contact_motor.fit(Path("unused"))
        x, y, evaluation = optimizer.call_args.args
        self.assertEqual((x.shape, y.shape, evaluation.shape), ((1, 17), (1, 6), (0, 17)))
        self.assertEqual(optimizer.call_args.kwargs, {"hidden": 32, "epochs": 200, "seed": 23, "learning_rate": .01})
        self.assertEqual(model["provenance"]["button_threshold"], .5)

    def test_contact_is_required_even_for_goal_reached_wait(self):
        row = observation(0, 0)
        del row["sense"]["buttons"]
        ctx = {"directive": {"goal": "learned-motor", "parameters": {"position": [0, 0, 0]}}}
        with self.assertRaisesRegex(ValueError, "buttons"):
            motor_contact.motor_action(network(), {"state": row["state"], "lily": {"sense": row["sense"]}}, ctx)


if __name__ == "__main__":
    unittest.main()

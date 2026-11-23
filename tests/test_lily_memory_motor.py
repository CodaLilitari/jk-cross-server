"""Catch lost carry, time-dependent decay, corrupt state and export drift."""
import copy
import importlib
import importlib.util
import json
import math
from pathlib import Path
import tarfile
import unittest

from bots.lily import motor_contact as contact
from test_lily_contact_motor import observation


def g4_model():
    root = Path(__file__).resolve().parents[1]
    with tarfile.open(root/"qa/lily-outcome-candidates.tar.gz") as archive:
        return json.load(archive.extractfile("models/g04-c11/model.json"))


@unittest.skipUnless(importlib.util.find_spec("numpy"),"memory search uses optional NumPy")
class MemoryMotorTests(unittest.TestCase):
    def setUp(self):
        for name in ("motor_memory", "memory_search"):
            self.assertIsNotNone(importlib.util.find_spec("bots.lily."+name), "memory contract is not implemented")
        self.m = importlib.import_module("bots.lily.motor_memory")
        self.s = importlib.import_module("bots.lily.memory_search")
        self.base = g4_model()
        self.model = self.s.initial_model(self.base, "carried")

    def test_zero_residual_reproduces_g4_outputs_and_export(self):
        scope = {}
        exec(self.m.policy_source(self.model), scope)
        memory = [0.]*4
        for i in range(15):
            values = [math.sin(i*.2+j)*1.5 for j in range(17)]
            predicted, memory = self.m.step(self.model, values, memory, 40)
            self.assertEqual(predicted, contact.predict(self.base, values))
            self.assertEqual(scope["step"](scope["MODEL"], values, memory, 40),
                             self.m.step(self.model, values, memory, 40))
        self.assertLess(len(self.m.policy_source(self.model).encode()), 128*1024)
        self.assertEqual(scope["STATE_VERSION"], 1)

    def test_scalar_decay_and_elapsed_time_semigroup(self):
        residual = self.model["residual"]
        residual["w"] = [[0.]*17 for _ in range(4)]
        residual["b"] = [.2, -.3, .7, -.8]
        x, previous = [0.]*17, [.6, -.6, .2, -.1]
        _, full = self.m.step(self.model, x, previous, 40)
        _, half = self.m.step(self.model, x, previous, 20)
        _, halves = self.m.step(self.model, x, half, 20)
        for n, rho in enumerate((.3, .75, .93, .98)):
            self.assertAlmostEqual(full[n], rho*previous[n]+(1-rho)*math.tanh(residual["b"][n]), places=14)
            self.assertAlmostEqual(full[n], halves[n], places=14)

    def test_identical_current_features_can_produce_different_controls(self):
        self.model["residual"]["o"] = [[8., 0., 0., 0.] for _ in range(6)]
        x = [0.]*17
        left, _ = self.m.step(self.model, x, [-1., 0., 0., 0.], 40)
        right, _ = self.m.step(self.model, x, [1., 0., 0., 0.], 40)
        self.assertGreater(max(abs(a-b) for a,b in zip(left, right)), .1)
        instant = self.s.without_history(self.model)
        self.assertEqual(instant["residual"], self.model["residual"])
        self.assertEqual(self.m.step(instant, x, [-1.,0.,0.,0.], 40),
                         self.m.step(instant, x, [1.,0.,0.,0.], 40))

    def test_explicit_state_wait_holds_and_rejects_wrong_identity(self):
        row = observation(0, 0)
        obs = {"state":row["state"], "lily":{"sense":row["sense"]}}
        ctx = {"directive":{"goal":"learned-motor", "parameters":{
            "position":row["goal"]["position"], "duration_ms":40}}}
        start = self.m.initial_state(self.model)
        result = self.m.motor_action(self.model, obs, dict(ctx, state=start))
        self.assertNotEqual(result["state"]["memory"], start["memory"])
        self.assertEqual(start["memory"], [0.,0.,0.,0.])
        wait = copy.deepcopy(ctx)
        wait["directive"]["parameters"]["position"] = row["sense"]["position"]
        wait["state"] = result["state"]
        self.assertEqual(self.m.motor_action(self.model, obs, wait), {"action":"wait", "state":result["state"]})
        for state in (dict(start, memory=[0.]*3), dict(start, memory=[float("nan")]*4),
                      dict(start, memory=[1.01]*4), dict(start, model_sha256="00"*32),
                      dict(start, schema=True), dict(start, extra=1)):
            with self.subTest(state=state), self.assertRaises(ValueError):
                self.m.motor_action(self.model, obs, dict(ctx, state=state))
        with self.assertRaises(ValueError):
            self.m.motor_action(self.model, obs, dict(ctx, undertaking={"goal":"escape-bank"}))
        bad = copy.deepcopy(self.model)
        bad["base"]["b2"][0] += .01
        with self.assertRaises(ValueError): self.m.canonical(bad)
        bad = copy.deepcopy(self.model)
        bad["residual"]["o"][0][0] = 1001.
        with self.assertRaises(ValueError): self.m.policy_source(bad)


if __name__ == "__main__":
    unittest.main()

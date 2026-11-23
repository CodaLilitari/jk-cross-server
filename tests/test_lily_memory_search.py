"""Outcome ranking protects retained anchors before rewarding additional skill."""
import copy
import importlib
import importlib.util
import math
import unittest

from test_lily_memory_motor import g4_model
from test_lily_outcome_search import row


@unittest.skipUnless(importlib.util.find_spec("numpy"),"memory search uses optional NumPy")
class MemorySearchTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("bots.lily.memory_search"), "paired search is not implemented")
        self.s = importlib.import_module("bots.lily.memory_search")

    def test_antithetic_directions_match_between_arms_and_preserve_base(self):
        base = g4_model()
        recurrent = self.s.initial_model(base, "carried")
        static = self.s.initial_model(base, "instant")
        self.assertEqual(recurrent["residual"], static["residual"])
        original = copy.deepcopy(recurrent)
        for generation in (1, 5, 8):
            one = self.s.candidate_models(recurrent, generation, "12"*32)
            two = self.s.candidate_models(static, generation, "12"*32)
            self.assertEqual(len(one), 9)
            self.assertEqual(one[0]["model"], recurrent)
            for i in range(1,9):
                self.assertEqual(one[i]["model"]["base"], base)
                for key in ("w", "b", "o"):
                    self.assertEqual(one[i]["model"]["residual"][key], two[i]["model"]["residual"][key])
                self.assertEqual(two[i]["model"]["residual"]["a"], static["residual"]["a"])
            for i in (1,3,5,7):
                for key in ("b", "a"):
                    for plus, minus, center in zip(one[i]["model"]["residual"][key], one[i+1]["model"]["residual"][key], recurrent["residual"][key]):
                        self.assertAlmostEqual(plus+minus, 2*center, places=14)
        self.assertEqual(original, recurrent)
        with self.assertRaises(ValueError): self.s.candidate_models(recurrent, True, "12"*32)
        with self.assertRaises(ValueError): self.s.candidate_models(recurrent, 1, "xx"*32)

    def batch(self):
        anchors = [f"a{i}" for i in range(8)]
        pool = [f"p{i}" for i in range(6)]
        shaft = anchors + ["s0", "s1"]
        ids = anchors+pool+["s0", "s1"]
        models = self.s.candidate_models(self.s.initial_model(g4_model(), "carried"), 1, "12"*32)
        names = [m["candidate_id"] for m in models]
        evaluations = {n:[row(e,"supported_dry",100) if e in anchors else row(e,"sim_timeout",9000) for e in ids] for n in names}
        refs = {name:[row(e,"supported_dry",100) for e in ids] for name in ("v3","g4")}
        return models, evaluations, ids, anchors, pool, shaft, refs

    def test_losing_retained_anchor_cannot_buy_many_pool_wins(self):
        models, evaluations, ids, anchors, pool, shaft, refs = self.batch()
        names = list(evaluations)
        evaluations[names[1]] = [row(e,"supported_dry",38) if e != anchors[0] else row(e,"sim_timeout",9000) for e in ids]
        evaluations[names[2]][ids.index("s0")] = row("s0","supported_dry",100)
        result = self.s.select_generation(models,evaluations,ids,anchors,pool,shaft,refs)
        self.assertFalse(result["candidates"][names[1]]["eligible"])
        self.assertEqual(result["selected_id"], names[2])
        self.assertEqual(result["candidates"][names[1]]["lost_retained_anchors"], [anchors[0]])
        evaluations[names[2]][0]["physical_success"] = None
        with self.assertRaises(ValueError): self.s.select_generation(models,evaluations,ids,anchors,pool,shaft,refs)

    def test_full_qualification_and_deterministic_null_or_time_tie(self):
        pool, shaft = [f"p{i}" for i in range(24)], [f"s{i}" for i in range(8)]
        ids = pool+shaft
        rows = {n:[row(e,"supported_dry",100) for e in ids] for n in ("v3","g4","static","recurrent","no_history")}
        rows["static"][-1] = row(shaft[-1],"sim_timeout",9000)
        rows["recurrent"][-1] = row(shaft[-1],"sim_timeout",9000)
        self.assertIsNone(self.s.select_open(rows,pool,shaft)["selected"])
        rows["recurrent"][-1] = row(shaft[-1],"supported_dry",100)
        self.assertEqual(self.s.select_open(rows,pool,shaft)["selected"], "recurrent")
        rows["static"][-1] = row(shaft[-1],"supported_dry",100)
        self.assertEqual(self.s.select_open(rows,pool,shaft)["selected"], "static")
        rows["recurrent"][0]["physics_steps"] = 99
        self.assertEqual(self.s.select_open(rows,pool,shaft)["selected"], "recurrent")


if __name__ == "__main__":
    unittest.main()

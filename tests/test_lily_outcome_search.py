"""Pin the outcome experiment's proposals and its two selection rules without rollouts."""
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import unittest

from bots.lily import motor_contact

if importlib.util.find_spec("numpy"):
    import numpy as np
    from bots.lily.outcome_search import (
        candidate_models, head, score_episodes, select_development, select_generation,
    )

MODEL = Path(__file__).resolve().parents[1] / "bots/lily/models/water_recovery_v3.json"
DECLARATION = "ca" * 32
V3_FILE = "e08532a4c1a2f7b0fa88417456d177cedd03c67d26555c4a5be1f4d80b599043"
V3_CANONICAL = "25cd7e67f73a747ee49a257556c068a7aeadd21605466080be3ce96bed74120e"
V3_EXPORT = "f849e6bae2e41e86a3ed70b6df00d6365c1803da9973fbaae6e1db8d26650d51"


def row(episode, terminal="died", steps=43):
    return dict(episode_id=episode, terminal=terminal, physics_steps=steps,
                physical_success=terminal == "supported_dry", owner="model", controller="every_tick",
                ownership_complete=True, baseline_assisted=False)


@unittest.skipUnless(importlib.util.find_spec("numpy"), "outcome search uses NumPy")
class ProposalTests(unittest.TestCase):
    def setUp(self):
        self.parent = json.loads(MODEL.read_bytes())

    def test_full_tensor_antithetic_pairs_preserve_v3_and_freeze_encoder(self):
        self.assertEqual(hashlib.sha256(MODEL.read_bytes()).hexdigest(), V3_FILE)
        self.assertEqual(hashlib.sha256(motor_contact.canonical(self.parent)).hexdigest(), V3_CANONICAL)
        self.assertEqual(hashlib.sha256(motor_contact.policy_source(self.parent).encode()).hexdigest(), V3_EXPORT)
        original = copy.deepcopy(self.parent)
        center = np.asarray([w + [b] for w, b in zip(original["w2"], original["b2"])])
        np.testing.assert_array_equal(head(self.parent), center)
        cube = np.random.Generator(np.random.PCG64(41023)).standard_normal((8, 6, 6, 33))
        for generation in (8, 1, 5, 2, 7, 3, 6, 4, 1):
            candidates = candidate_models(self.parent, generation, DECLARATION)
            self.assertEqual([c["candidate_id"] for c in candidates],
                             [f"g{generation:02d}-c{i:02d}" for i in range(13)])
            self.assertEqual(candidates[0]["model"], original)
            scales = np.array([.18] * 4 + [.65] * 2) / math.sqrt(33)
            if generation > 4:
                scales *= .5
            for i, c in enumerate(candidates[1:]):
                direction, polarity = divmod(i, 2)
                sign = 1 if polarity == 0 else -1
                expected = center + sign * cube[generation - 1, direction] * scales[:, None]
                model = c["model"]
                np.testing.assert_array_equal(head(model), expected)
                self.assertEqual(np.count_nonzero(expected != center), 198)
                self.assertEqual(model.keys(), original.keys())
                for key in ("schema", "feature_names", "output_names", "normalization", "w1", "b1"):
                    self.assertEqual(model[key], original[key])
                p = model["provenance"]
                self.assertEqual((p["generation"], p["direction"], p["sign"], p["seed"]),
                                 (generation, direction, sign, 41023))
                self.assertEqual((p["axis_scale"], p["button_scale"]), (scales[0], scales[4]))
                self.assertEqual(p["parent_canonical_sha256"], V3_CANONICAL)
                self.assertEqual(p["declaration_sha256"], DECLARATION)
                self.assertEqual(p["v3"], dict(file_sha256=V3_FILE, canonical_sha256=V3_CANONICAL,
                                              export_sha256=V3_EXPORT))
                self.assertTrue(p["method"])
                self.assertTrue(p["frozen_encoder"])
                self.assertLess(len(json.dumps(p)), 2048)
                self.assertNotIn("correction_sources", p)
        self.assertEqual(self.parent, original)

    def test_descendant_binds_actual_parent_and_supplies_standalone_export(self):
        first = candidate_models(self.parent, 1, DECLARATION)[1]["model"]
        second = candidate_models(first, 2, DECLARATION)
        self.assertEqual(second[0]["model"], first)
        child = second[1]["model"]
        self.assertEqual(child["provenance"]["parent_canonical_sha256"],
                         hashlib.sha256(motor_contact.canonical(first)).hexdigest())
        reference = candidate_models(self.parent, 2, DECLARATION)[1]["model"]
        np.testing.assert_allclose(head(child) - head(first), head(reference) - head(self.parent),
                                   atol=1e-14, rtol=0)
        exported = {}
        exec(motor_contact.policy_source(child), exported)
        self.assertEqual(exported["MODEL"], child)
        values = [i / 17 for i in range(17)]
        self.assertEqual(exported["predict"](exported["MODEL"], values), motor_contact.predict(child, values))

    def test_invalid_generation_declaration_or_v3_start_cannot_generate_proposals(self):
        for g, declaration in ((0, DECLARATION), (9, DECLARATION), (True, DECLARATION),
                               (1, "x" * 64), (1, "00" * 31)):
            with self.subTest(g=g, declaration=declaration), self.assertRaises(ValueError):
                candidate_models(self.parent, g, declaration)
        self.parent["w2"][0][0] += .01
        with self.assertRaises(ValueError):
            candidate_models(self.parent, 1, DECLARATION)
        self.parent["w1"][0][0] += .01
        with self.assertRaises(ValueError):
            candidate_models(self.parent, 2, DECLARATION)


@unittest.skipUnless(importlib.util.find_spec("numpy"), "outcome search uses NumPy")
class OutcomeTests(unittest.TestCase):
    def test_missed_landing_charges_full_budget_even_for_an_early_death(self):
        ids = ["a", "b", "c"]
        losses = [row("a", "sim_timeout", 9000), row("c", steps=2), row("b", steps=1)]
        self.assertEqual(score_episodes(losses, ids), (0, -27000))
        slow = [row("b", "supported_dry", 9000), *losses[:2]]
        self.assertEqual(score_episodes(slow, ids), (1, -27000))
        self.assertGreater(score_episodes(slow, ids), score_episodes(losses, ids))
        slow[0]["physics_steps"] = 8999
        self.assertEqual(score_episodes(slow, ids), (1, -26999))

    def test_rejects_missing_extra_and_duplicate_assignments(self):
        for ids, rows in (([], []), (["a", "b"], [row("a")]), (["a"], [row("a"), row("b")]),
                          (["a", "b"], [row("a"), row("a")]), (["a", "a"], [row("a")])):
            with self.subTest(ids=ids, rows=rows), self.assertRaises(ValueError):
                score_episodes(rows, ids)

    def test_censors_contradictions_and_wrong_ownership_cannot_score(self):
        with self.assertRaises(ValueError):
            score_episodes([None], ["a"])
        for changes in (dict(physical_success=None), dict(terminal="unknown"),
                        dict(terminal="unavailable"), dict(terminal="sim_timeout", physics_steps=8999),
                        dict(terminal="supported_dry"), dict(physical_success=True),
                        dict(terminal="supported_dry", physical_success=True, physics_steps=37),
                        dict(ownership_complete=False), dict(ownership_complete=1),
                        dict(baseline_assisted=True), dict(baseline_assisted=0), dict(owner="baseline"),
                        dict(controller="hold550"), dict(physical_success=0), dict(physics_steps=True),
                        dict(physics_steps=43.0), dict(physics_steps=0), dict(physics_steps=9001)):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                score_episodes([dict(row("a"), **changes)], ["a"])

    def test_generation_uses_declared_order_and_retains_all_scores(self):
        candidates = [dict(candidate_id=f"g03-c{i:02d}") for i in range(13)]
        ids = [f"start-{i}" for i in range(8)]
        evaluations = {c["candidate_id"]: [row(e) for e in ids] for c in reversed(candidates)}
        result = select_generation(candidates, evaluations, ids)
        self.assertEqual(result["selected_id"], "g03-c00")
        self.assertEqual(result["scores"], {key: (0, -72000) for key in evaluations})
        for key in ("g03-c05", "g03-c11"):
            evaluations[key][0] = row(ids[0], "supported_dry", 42)
        self.assertEqual(select_generation(candidates, evaluations, ids)["selected_id"], "g03-c05")
        evaluations["g03-c11"][0]["physics_steps"] = 41
        self.assertEqual(select_generation(candidates, evaluations, ids)["selected_id"], "g03-c11")
        for changed in (dict(evaluations, extra=[]), {k: v for k, v in evaluations.items() if k != "g03-c11"}):
            with self.assertRaises(ValueError):
                select_generation(candidates, changed, ids)
        with self.assertRaises(ValueError):
            select_generation([*candidates, candidates[0]], evaluations, ids)
        with self.assertRaises(ValueError):
            select_generation(candidates[::-1], evaluations, ids)
        with self.assertRaises(ValueError):
            select_generation(candidates[:-1], {c["candidate_id"]: evaluations[c["candidate_id"]]
                                               for c in candidates[:-1]}, ids)

    def test_development_preserves_individual_shafts_and_requires_strict_improvement(self):
        pool = [f"pool-{i}" for i in range(24)]
        shaft = [f"shaft-{i}" for i in range(8)]

        def rows(wins):
            return [row(e, "supported_dry") if e in wins else row(e) for e in reversed(pool + shaft)]

        evaluations = dict(v3=rows([pool[0], shaft[0]]), g4=rows(pool[:5] + [shaft[1]]),
                           g8=rows(pool[:2] + [shaft[0]]))
        result = select_development(evaluations, pool, shaft)
        self.assertEqual(result["selected"], "g8")
        self.assertEqual(result["policies"]["g4"], dict(pool_wins=5, shaft_wins=1,
                                                       shaft_regressions=shaft[:1], eligible=False))
        self.assertTrue(result["policies"]["g8"]["eligible"])
        evaluations["g4"] = rows(pool[:2] + shaft[:1])
        self.assertEqual(select_development(evaluations, pool, shaft)["selected"], "g4")
        evaluations["g8"] = rows(pool[:3] + shaft[:1])
        self.assertEqual(select_development(evaluations, pool, shaft)["selected"], "g8")
        evaluations["g8"] = evaluations["g4"] = rows(pool[:1] + shaft)
        self.assertIsNone(select_development(evaluations, pool, shaft)["selected"])
        evaluations["g4"] = evaluations["g8"] = rows(pool + shaft[1:])
        self.assertIsNone(select_development(evaluations, pool, shaft)["selected"])
        with self.assertRaises(ValueError):
            select_development(evaluations, pool, [pool[0], *shaft[1:]])
        with self.assertRaises(ValueError):
            select_development(dict(evaluations, native=[]), pool, shaft)
        evaluations["g4"] = evaluations["g4"][:-1]
        with self.assertRaises(ValueError):
            select_development(evaluations, pool, shaft)

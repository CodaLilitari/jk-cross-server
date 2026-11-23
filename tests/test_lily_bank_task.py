import unittest

from bots.lily.bank_task import BankTask, bank_parameters, bank_verdict


class BankVerdictTest(unittest.TestCase):
    def test_terminal_and_ownership_are_independent(self):
        for terminal, physical in (
            ("supported_dry", True), ("died", False), ("sim_timeout", False),
            *((name, None) for name in ("sampled_dry", "budget_elapsed", "control_lost", "fence_changed",
                                        "directive_ended", "restarted", "unavailable", "invalid_evidence")),
        ):
            for arm, wet, assisted, complete, attribution in (
                ("baseline", False, False, True, "baseline"), ("candidate", True, False, True, "candidate"),
                ("candidate", True, True, True, "assisted"), ("candidate", False, True, True, "no_wet_takeover"),
                ("candidate", False, False, False, "unknown"), ("baseline", False, False, False, "unknown"),
            ):
                with self.subTest(terminal=terminal, attribution=attribution):
                    result = bank_verdict(terminal=terminal, controller=arm, wet_takeover=wet,
                                          baseline_assisted=assisted, ownership_complete=complete)
                    self.assertEqual(result, dict(terminal=terminal, physical_success=physical, attribution=attribution,
                                                  controller_success=physical if attribution in ("baseline", "candidate") else None))

    def test_invalid_classifier_input_is_rejected(self):
        base = dict(terminal="supported_dry", controller="baseline", wet_takeover=False,
                    baseline_assisted=False, ownership_complete=True)
        for k, v in (("terminal", "motor_goal_reached"), ("controller", "mlp"), ("ownership_complete", 1),
                     ("wet_takeover", None), ("baseline_assisted", 0)):
            with self.assertRaises(ValueError):
                bank_verdict(**dict(base, **{k:v}))

    def test_bounded_assignment_requires_valid_finite_typed_fields(self):
        base = {"position": [0, 0, 100], "sector": 0}
        self.assertEqual(bank_parameters(base, [0, 0, 0]), dict(base, budget_seconds=60))
        for change in ({"sector": False}, {"sector": -1}, {"position": [0, 0, 101]},
                       {"position": [0, 0, 10**400]}, {"position": [True, 0, 0]},
                       {"budget_seconds": 0}, {"budget_seconds": 61}, {"budget_seconds": True},
                       {"budget_seconds": float("nan")}, {"duration_ms": 500}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                bank_parameters(dict(base, **change), [0, 0, 0])

    def test_dry_proxy_needs_distinct_samples_continuity_and_nearness(self):
        task = BankTask(dict(position=[0, 0, 0], budget_seconds=5), 1.)
        sense = dict(medium="air", supported=True, position=[4, 4, 4], sample_id=1)
        def update(i, clock, **change):
            sense.update(sample_id=i, **change)
            return task.observe(sense, clock)
        self.assertIsNone(update(1, 1.))
        self.assertIsNone(update(2, 1.3, position=[0, 0, 0]))
        self.assertIsNone(update(2, 1.6))
        self.assertIsNone(update(3, 1.7))
        self.assertIsNone(update(4, 1.9, medium="water"))
        self.assertIsNone(update(5, 2., medium="air"))
        self.assertIsNone(update(6, 2.125))
        self.assertIsNone(update(7, 2.25))
        self.assertEqual(update(8, 2.375), "sampled_dry")

    def test_clock_gap_or_regression_cannot_prove_budget(self):
        for untrusted in (None, .5):
            task = BankTask(dict(position=[0, 0, 0], budget_seconds=1), 1.)
            sense = dict(medium="water", supported=False, position=[0, 0, 0], sample_id=1)
            self.assertIsNone(task.observe(sense, untrusted))
            self.assertIsNone(task.observe(dict(sense, sample_id=2), 15.))

    def test_cached_stock_clock_cannot_shorten_the_supported_interval(self):
        task = BankTask(dict(position=[0, 0, 0], budget_seconds=5), 0.)
        sense = dict(medium="water", supported=False, position=[0, 0, 0])
        # Rich samples at 0, .08, .16, .24, .32, .40 see cached 5 Hz stock state.
        for index, clock in enumerate((0., 0., 0., .2, .2, .4), 1):
            if index >= 3:  # First supported dry observation is at .16 seconds.
                sense.update(medium="air", supported=True)
            self.assertIsNone(task.observe(dict(sense, sample_id=index), clock))
        self.assertEqual(task.observe(dict(sense, sample_id=7), .6), "sampled_dry")

    def test_budget_starts_after_a_new_clock_publication(self):
        task = BankTask(dict(position=[0, 0, 0], budget_seconds=1), 0.)
        sense = dict(medium="water", supported=False, position=[0, 0, 0])
        for index, clock in enumerate((0., .2, 1.), 1):
            self.assertIsNone(task.observe(dict(sense, sample_id=index), clock))
        self.assertEqual(task.observe(dict(sense, sample_id=4), 1.2), "budget_elapsed")

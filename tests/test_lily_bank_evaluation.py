import csv
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1] / "native/tests/stock_water_replay"
sys.path.insert(0, str(HERE))


class BankEvaluation(unittest.TestCase):
    def test_stock_support_streak_resets_on_wrong_bank_or_detachment(self):
        # The compiled helper below is the same predicate used after each stock move.
        program = """
#include <assert.h>
#include "bank_oracle.h"
int main(void) {
    int streak = 0;
    for (int i=0;i<37;i++) assert(!bank_supported_step(&streak,41,41,41,1));
    assert(!bank_supported_step(&streak,41,10,10,1));
    for (int i=0;i<37;i++) assert(!bank_supported_step(&streak,41,41,41,1));
    assert(!bank_supported_step(&streak,41,41,-1,1));
    assert(!bank_supported_step(&streak,41,41,10,1));
    assert(!bank_supported_step(&streak,41,41,41,0));
    for (int i=0;i<37;i++) assert(!bank_supported_step(&streak,41,41,41,1));
    assert(bank_supported_step(&streak,41,41,41,1));
}
"""
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "oracle"
            built = subprocess.run(["cc", "-I", str(HERE), "-x", "c", "-", "-o", exe],
                                   input=program, text=True, capture_output=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            subprocess.run([exe], check=True)

    def setUp(self):
        self.digest = "abcd1234" * 8
        self.revision = int(self.digest[:8], 16)
        self.fence = dict(run_id="ab", world_epoch=1, life_epoch=1)
        self.attempt = dict(self.fence, event="attempt", kind="motor", action_seq=8,
                            revision=self.revision, sample_id=11, policy_hash=self.digest, task_id="one")
        self.assignment = dict(episode_id="example-yaw0", controller="candidate",
                               target_sector=41, split="holdout", directive_id="example-yaw0")
        self.start = dict(self.fence, event="bank_start", task_id="one", directive_id="example-yaw0",
                          policy_hash=self.digest, sector=41, position=[1,2,3], budget_seconds=60)
        self.header = dict(event="assigned", sector=41, position=[1, 2, 3], seed=123)

    def tick(self, i, owner, wet=True):
        motor = owner == "motor"
        return dict(event="control", tick=i, owner=owner, wet=wet,
                    world_epoch=1, life_epoch=1, sample_id=11 if motor else 0,
                    action_seq=8 if motor else 0, revision=self.revision if motor else 0,
                    axes=[0, 0, 0, 0], buttons=0, step=i*6)

    def terminal(self, n, kind="supported_dry"):
        return dict(event="terminal", terminal=kind, ticks=n, step=9000 if kind=="sim_timeout" else 38,
                    sector=41, health=90, dry_steps=38 if kind=="supported_dry" else 0,
                    first_breath_step=None)

    def score(self, events, actions=None):
        from evaluate_bank import score_trial
        if actions is None:
            actions = [self.attempt]
        code = 1 if any(r.get("terminal")=="sim_timeout" for r in events) else 0
        return score_trial(self.assignment, [self.header, *events], [self.start, *actions], code,
                           baseline_digest="f"*64, candidate_digest=self.digest, fence=self.fence)[0]

    def test_baseline_rescue_and_dry_only_motor(self):
        events = [self.tick(0,"baseline"), self.tick(1,"motor"), self.terminal(2)]
        result = self.score(events)
        self.assertTrue(result["physical_success"])
        self.assertEqual(result["attribution"], "assisted")
        self.assertIsNone(result["controller_success"])
        events[1]["wet"] = False
        self.assertEqual(self.score(events)["attribution"], "no_wet_takeover")

    def test_unknown_tick_and_mismatched_revision_block_controller_credit(self):
        for events, actions in [
            ([self.tick(1,"motor"), self.terminal(2)], [self.attempt]),
            ([self.tick(0,"motor"), self.terminal(1)], [dict(self.attempt, revision=1)]),
            ([self.tick(0,"motor"), self.terminal(1)], [dict(self.attempt, life_epoch=2)]),
        ]:
            result = self.score(events, actions)
            self.assertEqual(result["attribution"], "unknown")
            self.assertIsNone(result["controller_success"])
            self.assertEqual(result["control_ticks"]["unknown"], 1)

    def test_private_motor_successes_do_not_override_native_terminal(self):
        actions = [self.attempt] + [dict(event="outcome",physical_success=True)] * 37
        result = self.score([self.tick(0,"motor"), self.terminal(1,"sim_timeout")],actions)
        self.assertIs(result["physical_success"], False)
        self.assertIs(result["controller_success"], False)
        self.assertEqual(result["elapsed_sim_seconds"], 60)
        self.assertIsNone(self.score([self.tick(0,"motor")], actions)["physical_success"])

    def test_matrix_ids_work_in_deployed_directive_parser(self):
        from evaluate_bank import assignments
        from bots.lily.runtime import IDENT
        with (HERE/"bank_cases.tsv").open() as f:
            ids = [job.get("directive_id", "") for job in assignments(list(csv.DictReader(f, delimiter="\t")))
                   if job["controller"] == "candidate"]
        self.assertTrue(all(IDENT.fullmatch(i) for i in ids))
        self.assertEqual(len(set(ids)), 27)

    def test_cli_records_every_assignment_if_build_inputs_are_missing(self):
        from evaluate_bank import main
        import json
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            out = root/"run"
            self.assertEqual(main(["--source",str(root),"--build",str(root),"--map",str(root/"missing"),
                                   "--output",str(out)]), 1)
            report = json.loads((out/"receipt.json").read_text())
            self.assertEqual(len(report["episodes"]), 54)
            self.assertTrue(all(r["terminal"] == "unavailable" for r in report["episodes"]))
            self.assertEqual(report["summary"]["holdout"]["candidate"]["assigned"], 5)

    def test_startup_failure_stays_in_assigned_denominator(self):
        from evaluate_bank import assignments, summarize, unavailable
        with (HERE/"bank_cases.tsv").open() as f:
            jobs = assignments(list(csv.DictReader(f, delimiter="\t")))
        self.assertEqual(len(jobs), 54)
        self.assertEqual(sum(job["split"]=="holdout" for job in jobs), 10)
        rows = [unavailable(job, "fixture_setup_failed") for job in jobs]
        summary = summarize(rows)
        for arm in ("candidate","baseline"):
            self.assertEqual(summary["all"][arm]["assigned"], 27)
            self.assertEqual(summary["all"][arm]["censored"], 27)
            self.assertEqual(summary["all"][arm]["attribution_eligible"], 0)
            self.assertEqual(summary["holdout"][arm]["assigned"], 5)

"""Post-run reporting must preserve strict rejection and never manufacture a scored row."""
import importlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from test_lily_recovery_evaluation import one_loss, write_rows


@unittest.skipUnless(importlib.util.find_spec("numpy"), "frozen memory search uses NumPy")
class MemoryFailureReportTests(unittest.TestCase):
    def setUp(self):
        self.diagnostic = importlib.import_module("scripts.bot_development.analysis.report_memory_failure")

    def test_reproduce_only_exact_heading_exception_without_scoring(self):
        d = self.diagnostic
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            job, case, _ = one_loss(work)
            a = {"job": job}
            d.run.write(work / "assignment.json", a)
            d.run.write(work / "process.json", {})
            bank = {"cases": {case["case"]: case}}
            edges = {job["target_sector"]: [19, d.run.motor.digest(work / "start.json"), [1, 0, 0]]}
            frames = [json.loads(line) for line in (work / "motor.jsonl").read_text().splitlines()]
            frames[0]["sense"]["facing"] = [0, 1, 0]
            write_rows(work / "motor.jsonl", frames)
            result = d.reproduce_invalid(a, work, bank, (None,None), edges)
            self.assertEqual(set(result), {"status","error","detail","raw"})
            self.assertEqual(result["detail"], "incorrect_initial_heading")
            self.assertEqual(len(result["raw"]), 8)
            frames[0]["sector"] = -4
            write_rows(work / "motor.jsonl", frames)
            with self.assertRaisesRegex(ValueError, "incorrect_initial_actor"):
                d.reproduce_invalid(a, work, bank, (None,None), edges)

    def test_matching_message_from_other_site_is_never_recoverable(self):
        d = self.diagnostic
        try:
            raise ValueError(d.HEADING_ERROR)
        except ValueError as exc:
            self.assertFalse(d.expected_heading_error(exc, Path("/abandoned"), from_partial=True))
            self.assertFalse(d.expected_heading_error(exc, Path("/abandoned")))

    def test_changed_invalid_receipt_or_free_witness_is_rejected(self):
        d = self.diagnostic
        raw = {"assignment.json": {"sha256":"aa"*32, "bytes":100}}
        attempts = [dict(status="invalid", error="ValueError", detail=d.HEADING_ERROR, raw=raw), dict(status="unrun")]
        counts = d.run.old.counts_for(attempts)
        receipt = dict(attempts=attempts, counts=counts, assignments_sha256="ledger", free_bytes_after=0)
        self.assertEqual(d.verify_sealed_receipt(receipt, "ledger", attempts), counts)
        for changed in [dict(free_bytes_after=True), dict(counts=dict(counts, wins=1)),
                        dict(attempts=[dict(attempts[0], raw={}), attempts[1]])]:
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                d.verify_sealed_receipt(dict(receipt, **changed), "ledger", attempts)

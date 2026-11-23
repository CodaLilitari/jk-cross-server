"""Supplement the failed frozen memory audit with its verified prefix and two rejected claims.

This post-run diagnostic applies only to the preserved experiment identified below. It does
not execute a game, change an adjudication, or issue a successful frozen-auditor report.
"""
import argparse
from hashlib import sha256
import os
import time
from pathlib import Path
import traceback

from . import audit_memory_learning as strict
from . import run_memory_learning as run


DECLARATION = "77ef88dcfa3f94c2095a4fbd397cbfd3c6b11fafe8b55f387503df24b66b5b4d"
HEADER = "526aab01427067bfd5677f9fb446007cba549d3505dfcabb6c9a4c0df6815c48"
SEALED_BLOCK = "bcd7f88663bb6dffbffd53e75eacb6baa91b8732cb39950d9a0c56828dc99263"
RAW_INVENTORY = "88a9389d73cd97c174f4bc738c36057d3a31b2ebb30e893fca52b132a5027ed5"
CLAIMS = tuple("v3--outcome-sealed-pool-01-yaw" + yaw for yaw in ("-45", "45"))
HEADING_ERROR = "incorrect_initial_heading"
AUDITOR = "scripts/bot_development/analysis/audit_memory_learning.py"
COMPLETE_BLOCKS = ["calibration", *(f"{arm}-g{gen:02d}" for gen in range(1, 9)
                                    for arm in ("s", "r")), "open"]


def expected_heading_error(exc, work, *, from_partial=False):
    """Only recognize the exact frozen throw site, claim and (for the top level) partial-block call."""
    if type(exc) is not ValueError or exc.args != (HEADING_ERROR,):
        return False
    frames = [frame for frame, _ in traceback.walk_tb(exc.__traceback__)]
    required = [run.trial.audit_attempt, run.trial.available_witnesses, run.motor.verify_start, run.motor.check]
    if from_partial:
        required.insert(0, run.audit_partial_block)
    tail = frames[-len(required):]
    return ([f.f_code for f in tail] == [fn.__code__ for fn in required]
            and all(f.f_locals.get("work") == work for f in tail[:-2])
            and (not from_partial or tail[0].f_locals["label"] == "sealed"))


def reproduce_invalid(assignment, work, bank, paths, edges):
    run.old.require_inventory(work, set(), run.legacy.BASE_RAW | run.legacy.MODEL_RAW)
    run.equal(run.read(work / "assignment.json"), assignment, "mismatched invalid attempt claim")
    job = assignment["job"]
    try:
        run.trial.audit_attempt(assignment, work, bank["cases"][job["case"]], *paths, edge=edges[job["target_sector"]])
    except ValueError as exc:
        if not expected_heading_error(exc, work):
            raise
        return dict(status="invalid", error=type(exc).__name__, detail=str(exc),
                    raw={p.name:run.file_record(p) for p in sorted(work.iterdir())})
    raise ValueError("Frozen validator no longer rejects the recorded invalid claim")


def verify_sealed_receipt(recorded, ledger_digest, attempts):
    free = recorded["free_bytes_after"]
    run.check(type(free) is int and free >= 0, "invalid free-space witness")
    counts = run.old.counts_for(attempts)
    run.equal(recorded, dict(assignments_sha256=ledger_digest, counts=counts, attempts=attempts,
                             free_bytes_after=free),
              "published sealed receipt differs from both strict rejections and unrun ledger")
    return counts


def sealed_block(experiment):
    root = experiment.output
    directory = root / "blocks" / "sealed"
    bank = experiment.banks["sealed"]
    # Both the open block's model references and the freeze were reconstructed by perform().
    refs = run.transfer_arms(experiment.report["freeze"], experiment.report["blocks"]["open"]["models"])
    models = {name:run.old.identity(ref) if ref else None for name, ref in refs.items()}
    paths = {name:run.check_model(root, ref) for name, ref in refs.items() if ref is not None}
    binding = run.old.bound(experiment.binding, run.motor.digest(root / "freeze.json"))
    ledger = run.old.assignments("sealed", bank, bank["ids"], models, binding)
    run.equal([len(ledger), [a["work_dir"] for a in ledger[:2]]], [288, list(CLAIMS)], "unexpected sealed order")
    run.old.require_inventory(directory, set(CLAIMS), {"assignments.json", "block.json"})
    run.equal(run.read(directory / "assignments.json"), ledger, "sealed ledger differs from frozen derivation")
    receipt = directory / "block.json"
    run.equal(run.motor.digest(receipt), SEALED_BLOCK, "changed published sealed block bytes")
    recorded = run.read(receipt)
    attempts = []
    public = []
    for index, assignment in enumerate(ledger):
        if index < len(CLAIMS):
            work = directory / assignment["work_dir"]
            result = reproduce_invalid(assignment, work, bank, paths[assignment["candidate_id"]], experiment.edges)
        else:
            result = dict(status="unrun")
        attempts.append(result)
        public.append(dict(candidate_id=assignment["candidate_id"], episode_id=assignment["job"]["episode_id"], **result))
    counts = verify_sealed_receipt(recorded, run.motor.digest(directory / "assignments.json"), attempts)
    experiment.evidence.tree(directory)
    return dict(role=bank["role"], models=refs, receipt=run.old.link(root, "blocks/sealed/block.json"),
                counts=counts, attempts=public)


class ReportingExperiment(run.Experiment):
    """Emit progress only after the unchanged frozen block operation returned successfully."""
    def block(self, label, bank, ids, refs, predecessor):
        result = super().block(label, bank, ids, refs, predecessor)
        print(f"Reconstructed {label}: {self.report['blocks'][label]['counts']['completed']} complete", flush=True)
        return result


def reconstruct(root, declaration):
    started_at, started_clock = run.now(), time.monotonic()
    run.check(root.is_dir() and root.absolute() == root.resolve(), "indirect run root")
    decl, digest, banks = run.declaration(declaration)
    run.equal([digest, decl["run_id"], len(decl["frozen_files_sha256"]), run.motor.digest(root / "run.json")],
              [DECLARATION, run.RUN_ID, 71, HEADER], "outside the documented failed run")
    experiment = ReportingExperiment(root, decl, digest, banks, audit=True)
    try:
        experiment.perform()
    except ValueError as exc:
        if not expected_heading_error(exc, root / "blocks" / "sealed" / CLAIMS[0], from_partial=True):
            raise
    else:
        raise ValueError("Frozen audit did not reproduce its documented failure")

    report = experiment.report
    run.equal(list(report["blocks"]), COMPLETE_BLOCKS, "failure occurred outside the expected prefix")
    run.equal([len(report["generations"]), report["freeze"]["selected"], report["criterion"]],
              [16, "static", None], "incomplete or unexpected open selection")
    for label, block in report["blocks"].items():
        n = 160 if label == "open" else 144
        run.equal([block["counts"]["completed"], block["counts"]["assigned"]], [n, n], "incomplete prefix " + label)
    report["blocks"]["sealed"] = sealed_block(experiment)
    experiment.evidence.finish()
    files = run.old.tree_files(root)
    inventory_digest = sha256(run.memory.json_bytes(files)).hexdigest()
    run.equal(inventory_digest, RAW_INVENTORY, "changed raw inventory since independent preservation")

    strict.incomplete_report(report, "Frozen offline reconstruction rejects the first sealed starting heading.")
    counts = report["counts"]
    run.equal([counts[key] for key in ("assigned","attempted","completed","invalid","censored","unrun")],
              [2896,2610,2608,2,0,286], "supplemental accounting mismatch")
    run.equal(report["reinferred_decisions"], 1120070, "unexpected completed-prefix inference count")
    helper = Path(__file__).resolve()
    transcript = "qa/lily-memory-strict-audit.txt"
    transcript_digest = run.motor.digest(run.ROOT / transcript)
    run.equal(transcript_digest, "75de40840c0f047173f1b1a3f106e93ea19bd5ded3ea3965d8fa36eda7761c7d",
              "changed frozen CLI failure record")
    report.update(title="Post-run supplemental reconstruction of the stopped protected memory experiment",
                  report_kind="post_run_supplemental_reconstruction", preregistered_reporter=False,
                  original_auditor_failed=True, original_cli_failed=True, original_cli_output_absent=True,
                  frozen_audit=dict(module=AUDITOR, source_sha256=decl["frozen_files_sha256"][AUDITOR],
                                    cli_exit_code=1, cli_output_written=False, transcript=transcript,
                                    transcript_sha256=transcript_digest,
                                    cli_error="Memory reconstruction failed: " + HEADING_ERROR,
                                    rejection_reproduced_on=CLAIMS[0]),
                  supplemental_reporter=dict(path=helper.relative_to(run.ROOT).as_posix(), sha256=run.motor.digest(helper),
                                             started_at_utc=started_at, finished_at_utc=run.now(),
                                             elapsed_seconds=time.monotonic()-started_clock),
                  completed_prefix_blocks=COMPLETE_BLOCKS, historical_diagnostic_attempts=0,
                  unreached_historical_budget=run.execution_budget(True)["diagnostics"],
                  raw_inventory_sha256=inventory_digest, retained_files=len(files),
                  retained_bytes=sum(f["bytes"] for f in files.values()))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--declaration", type=Path, default=run.ROOT / run.DECLARATION)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        output = args.output.absolute()
        root = args.run.absolute()
        run.check(output.parent.resolve() == output.parent and not output.is_relative_to(root.resolve()),
                  "supplemental output must be outside the retained run, under a direct parent")
        if os.path.lexists(output) or os.path.lexists(output.with_suffix(output.suffix + ".partial")):
            raise FileExistsError("supplemental output already exists")
        report = reconstruct(root, args.declaration)
        run.write(output, report)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, "Supplemental report failed: " + str(exc) + "\n")
    print("Supplemental prefix reconstructed; frozen CLI failed.", report["counts"], flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

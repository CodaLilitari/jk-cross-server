"""Refit the contact motor once on the declared original and successful native recovery rows."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from . import motor_contact, motor_model, train_contact_motor, train_motor
from .train_motor import fit_weights

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "native/tests/stock_water_replay"
sys.path.insert(0, str(FIXTURE))
import collect_recovery

DECLARATION = ROOT / "qa/lily-recovery-declaration.json"
DECLARATION_SHA256 = "156e35ea59eb2fc681a1c9e5ca83d44c3a349c202607da359d2b0f6b92600e54"
ORIGINAL_ROWS_SHA256 = "54c5c99552b9e5ee928502522f5582932081d18fa98b8b07d035dc67f9f2f79d"
ORIGINAL_FIELDS = ("train_samples", "training_sources", "train_split_groups", "development_split_groups",
                   "development_episode_ids", "original_model_file_sha256", "baseline_reference_file_sha256")


def ordered_hash(rows):
    data = json.dumps(rows, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(data).hexdigest()


def original_rows(directory, declaration):
    """Verify recollection against both frozen source identities and ordered numeric rows."""
    data = collect_recovery.MODEL.read_bytes()
    if hashlib.sha256(data).hexdigest() != declaration["v2_model_sha256"]:
        raise ValueError("Frozen contact v2 model digest mismatch.")
    frozen = json.loads(data)["provenance"]
    rows, source = train_contact_motor.training_rows(directory)
    if (source["source_receipt_file_sha256"] != declaration["reference_receipt_sha256"]
            or not collect_recovery.same({k: source[k] for k in ORIGINAL_FIELDS},
                                         {k: frozen[k] for k in ORIGINAL_FIELDS})):
        raise ValueError("Original contact training split, source identities or receipt changed.")
    if len(rows) != frozen["train_samples"] or ordered_hash(rows) != ORIGINAL_ROWS_SHA256:
        raise ValueError("Original ordered training rows changed.")
    return rows, dict(source, v2_source_receipt_file_sha256=frozen["source_receipt_file_sha256"])


def correction_rows(directory, job, cap):
    """Consume one fully adjudicated assignment. Tick counts are unknown for censored evidence."""
    k = job["handoff_tick"]
    source = {key: job[key] for key in ("episode_id", "case", "handoff_tick", "teacher_start_tick",
                                        "physical_success", "terminal", "ownership_complete", "raw_sha256")}
    if job["physical_success"] is None:
        return [], dict(source, reason=job["reason"], control_ticks=None, samples=0,
                        excluded=dict(model_prefix=None, failed_or_censored_suffix=None,
                                      after_cap=0, remaining_goal=0))

    n = job["control_ticks"]
    excluded = dict(model_prefix=min(n, k), failed_or_censored_suffix=0, after_cap=0, remaining_goal=0)
    rows = []
    if job["physical_success"] is False:
        excluded["failed_or_censored_suffix"] = max(0, n-k)
    elif n > k:
        if (job["physical_success"] is not True or job["terminal"] != "supported_dry"
                or job["ownership_complete"] is not True or job["baseline_assisted"] is not True
                or job["handoff_reached"] is not True or job["teacher_start_tick"] != k):
            raise ValueError("Missing complete successful teacher ownership.")
        work, hashes = directory / job["work_dir"], job["raw_sha256"]
        if set(hashes) != set(collect_recovery.RAW_FILES):
            raise ValueError("Incomplete recovery evidence inventory.")
        frames = train_contact_motor.read_trace(work/"motor.jsonl", hashes["motor.jsonl"])
        native = train_contact_motor.read_trace(work/"native.jsonl", hashes["native.jsonl"])
        end = min(k+cap, n)
        excluded["after_cap"] = n-end
        for tick in range(k, end):
            obs, control = frames[2*tick], native[tick+1]
            sense = obs["sense"]
            if control["owner"] != "baseline" or sense["buttons"] != frames[2*tick-1]["buttons"]:
                raise ValueError("Unbound native teacher label or preceding applied mask.")
            remaining = motor_model.remaining_goal(sense["position"], native[0]["position"])
            if remaining is None:
                excluded["remaining_goal"] += 1
                continue
            buttons = control["buttons"]
            rows.append({"features": motor_contact.features(sense, obs["state"], remaining),
                         "target": motor_model.vector(control["axes"], 4) +
                                   [float(bool(buttons & 1)), float(bool(buttons & 2))]})
    return rows, dict(source, control_ticks=n, samples=len(rows), excluded=excluded)


def training_rows(original_directory, recovery_directory, declaration_path):
    original_directory, recovery_directory, declaration_path = map(
        Path, (original_directory, recovery_directory, declaration_path))
    data = declaration_path.read_bytes()
    if hashlib.sha256(data).hexdigest() != DECLARATION_SHA256:
        raise ValueError("Changed precollection declaration.")
    declaration = json.loads(data)
    receipt = recovery_directory / "receipt.json"
    receipt_sha256 = collect_recovery.digest(receipt)
    jobs = collect_recovery.assess_recovery(recovery_directory, original_directory, declaration_path)
    if collect_recovery.digest(receipt) != receipt_sha256 or collect_recovery.digest(declaration_path) != DECLARATION_SHA256:
        raise ValueError("Collection receipt or declaration changed during recovery audit.")
    original, original_source = original_rows(original_directory, declaration)
    corrections, sources = [], []
    cap = declaration["training_contract"]["maximum_teacher_ticks_per_run"]
    for job in sorted(jobs, key=lambda j: (j["case"], j["handoff_tick"])):
        if job["case"] not in original_source["train_split_groups"]:
            raise ValueError("Recovery assignment outside the original training split.")
        rows, source = correction_rows(recovery_directory, job, cap)
        corrections.extend(rows)
        sources.append(source)
    combined = original + corrections
    provenance = dict(original=original_source, correction_sources=sources,
                      original_samples=len(original), correction_samples=len(corrections), train_samples=len(combined),
                      original_rows_sha256=ORIGINAL_ROWS_SHA256, correction_rows_sha256=ordered_hash(corrections),
                      ordered_rows_sha256=ordered_hash(combined), declaration_sha256=DECLARATION_SHA256,
                      collection_receipt_sha256=receipt_sha256,
                      reference_receipt_sha256=declaration["reference_receipt_sha256"],
                      v2_model_sha256=declaration["v2_model_sha256"], v2_policy_sha256=declaration["v2_policy_sha256"])
    return combined, provenance


def fit(original_directory, recovery_directory, declaration_path):
    rows, provenance = training_rows(original_directory, recovery_directory, declaration_path)
    if not provenance["correction_samples"]:
        raise ValueError("No eligible correction rows. No fit performed.")
    import numpy as np
    x = np.asarray([row["features"] for row in rows], dtype=float)
    y = np.asarray([row["target"] for row in rows], dtype=float)
    weights, _, _ = fit_weights(x, y, x[:0], epochs=200, hidden=32, seed=23, learning_rate=.01)
    files = [Path(module.__file__).resolve() for module in (train_contact_motor, train_motor, motor_contact, motor_model)]
    files.append(Path(__file__).resolve())
    provenance.update(method="supervised_behavior_cloning", optimizer="Adam", initialization="fresh",
                      epochs=200, hidden=32, seed=23, learning_rate=.01, batch_size=128, button_threshold=.5,
                      normalization="combined training rows only", sample_weight=1, evaluation_samples=0,
                      numpy_version=np.__version__,
                      training_code_sha256={str(path.relative_to(ROOT)): collect_recovery.digest(path) for path in files})
    return motor_contact.validate_model({"schema": 2, "feature_names": list(motor_contact.FEATURES),
                                         "output_names": list(motor_model.OUTPUTS), **weights,
                                         "provenance": provenance})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original_directory", type=Path)
    parser.add_argument("recovery_directory", type=Path)
    parser.add_argument("declaration_path", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise ValueError("Output already exists.")
        model = fit(args.original_directory, args.recovery_directory, args.declaration_path)
        data = motor_contact.canonical(model) + b"\n"
        with args.output.open("xb") as stream:
            stream.write(data)
        print(json.dumps({"model_file_sha256": hashlib.sha256(data).hexdigest()}))
    except (OSError, ImportError, KeyError, TypeError, ValueError) as exc:
        parser.exit(1, f"Recovery motor training: {exc}\n")


if __name__ == "__main__":
    main()

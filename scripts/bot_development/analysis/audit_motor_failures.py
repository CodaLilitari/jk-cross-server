#!/usr/bin/env python3
"""Audit frozen contact-policy timeouts against matched stock bank traces (NumPy/SciPy)."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

import numpy as np
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from bots.lily import motor_contact, motor_model

MODEL = ROOT / "bots/lily/models/water_contact_v2.json"
TRANSITION = re.compile(rb"^TRANSITION sec [\d.]+ sector (\d+)->(\d+)", re.M)
DEFINITIONS = {
    "time": "First and last five seconds of each individual arm, capped at trajectory length; stress input tick is 40 ms (125 ticks per five seconds). Final-five comparisons refer to different task phases for successes/timeouts.",
    "surface_jump_edges": "Count of ticks with a witnessed fresh jump press and SITH_PF_ONWATERSURFACE before input. This does not by itself prove a jump impulse or supported landing.",
    "sectors": "Distinct sectors sampled at stock player control ticks. Sector 44 is the demonstrator pool exit approach and 10 the assigned dry target. Sub-control-tick sector transitions are not included.",
    "distance_to_training_tracks": "For each pre-input 3D actor position, minimum Euclidean distance in native game units to any pre-input training baseline position in the same region (pool-90 and pool-110 for pool). Each 5-s value is the median of those per-tick minimum distances.",
    "median_normalized_features_to_training": "Per-tick Euclidean distance to nearest demonstrated 17-feature vector in the same region, scaled by the frozen contact model training stds; median in five-second window. This is a descriptive reference, not a calibrated out-of-distribution threshold.",
    "neutral_inputs": "All four applied axes and button mask equal zero.",
    "ever_target_supported_at_control_tick": "At least one pre-input sample in assigned sector with supported=true. This indicator is separate from the 150 Hz terminal oracle.",
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def receipt(directory, expected_cases, expected_model):
    data = (directory / "receipt.json").read_bytes()
    report = json.loads(data)
    if (report["scope"] != "matrix" or report["cases_sha256"] != expected_cases
            or report["provenance"]["model_sha256"] != expected_model):
        raise ValueError(f"Receipt does not identify the requested frozen model and case matrix in {directory}")
    indexed = {}
    for row in report["episodes"]:
        key = (row["episode_id"], row["controller"])
        if key in indexed or not all(re.fullmatch(r"[\w.-]+", value) for value in key):
            raise ValueError(f"Duplicate or invalid episode identity: {key}")
        indexed[key] = row
    return indexed, digest(data)


def frame_pairs(path, expected_hash):
    data = path.read_bytes()
    if digest(data) != expected_hash:
        raise ValueError(f"Motor trace digest mismatch in {path.parent.name}")
    lines = data.splitlines()
    if not lines or len(lines) % 2:
        raise ValueError(f"Incomplete motor trace in {path.parent.name}")
    frames = []
    for tick in range(len(lines) // 2):
        observed, applied = map(json.loads, lines[2*tick:2*tick+2])
        if (observed["event"] != "observation" or applied["event"] != "input"
                or observed["tick"] != tick or applied["tick"] != tick or observed["step"] != applied["step"]):
            raise ValueError(f"Unpaired observation/input in {path.parent.name} at tick {tick}")
        frames.append((observed, applied))
    return frames


def observation_arrays(frames):
    positions, features = [], []
    for observed, _ in frames:
        sense = observed["sense"]
        goal = motor_model.remaining_goal(sense["position"], observed["goal"]["position"])
        if goal is None:
            raise ValueError("An exact zero-distance goal has no motor feature direction")
        features.append(motor_contact.features(sense, observed["state"], goal))
        positions.append(sense["position"])
    return np.asarray(positions), np.asarray(features)


def training_trees(directory, model):
    """Group same-map baseline samples by their bank before measuring nearest distances."""
    sources = model["provenance"]["training_sources"]
    regions = {"pool": [], "shaft": []}
    for source in sources:
        episode = source["episode_id"]
        frames = frame_pairs(directory / f"{episode}-baseline" / "motor.jsonl", source["motor_sha256"])
        regions["pool" if episode.startswith("pool-") else "shaft"].append(observation_arrays(frames))
    scale = model["normalization"]["scale"]
    trees = {}
    for region, samples in regions.items():
        positions, features = zip(*samples)
        trees[region] = cKDTree(np.concatenate(positions)), cKDTree(np.concatenate(features) / scale)
    return trees


def rounded(value):
    return round(float(value), 4)


def summarize(frames, record, trees, scale, exit_sector):
    positions, features = observation_arrays(frames)
    surfaces = np.asarray([obs["sense"]["on_water_surface"] for obs, _ in frames])
    sectors = np.asarray([obs["sector"] for obs, _ in frames])
    supported = np.asarray([obs["sense"]["supported"] for obs, _ in frames])
    presses = np.asarray([bool(applied["presses"] & 1) for _, applied in frames])
    controls = np.asarray([applied["axes"] + [applied["buttons"]] for _, applied in frames])
    assigned_goal = frames[0][0]["goal"]
    window = max(1, round(5000 / frames[0][0]["sense"]["tick_ms"]))
    tail = slice(-window, None)
    xy = positions[tail, :2]
    world_distance = trees[0].query(positions)[0]
    feature_distance = trees[1].query(features[tail] / scale)[0]
    return {
        "terminal": record["terminal"],
        "sectors": sorted(set(sectors.tolist())),
        "jump_edges": int(presses.sum()),
        "surface_jump_edges": int(np.sum(surfaces & presses)),
        "exit_sector_surface_jump_edges": int(np.sum(surfaces & presses & (sectors == exit_sector))),
        "ever_target_supported_at_control_tick": bool(np.any(supported & (sectors == assigned_goal["sector"]))),
        "first_breath_step": record["first_breath_step"],
        "final_goal_distance": rounded(np.linalg.norm(positions[-1] - assigned_goal["position"])),
        "first5s_median_distance_to_training_tracks": rounded(np.median(world_distance[:window])),
        "last5s": {
            "neutral_inputs": int(np.sum(np.all(controls[tail] == 0, axis=1))),
            "distinct_inputs": len(np.unique(controls[tail], axis=0)),
            "jump_held_ticks": sum(bool(applied["buttons"] & 1) for _, applied in frames[tail]),
            "surface_contact_ticks": int(surfaces[tail].sum()),
            "fresh_jump_edges": int(presses[tail].sum()),
            "horizontal_net": rounded(np.linalg.norm(xy[-1] - xy[0])),
            "horizontal_path": rounded(np.linalg.norm(np.diff(xy, axis=0), axis=1).sum()),
            "median_distance_to_training_tracks": rounded(np.median(world_distance[tail])),
            "median_normalized_features_to_training": rounded(np.median(feature_distance)),
        },
    }


def audit(directories):
    model = motor_contact.validate_model(json.loads(MODEL.read_bytes()))
    trees = training_trees(directories["original_v1"], model)
    receipts, hashes = {}, {}
    case_hashes = {"original": digest((ROOT / "native/tests/stock_water_replay/bank_cases.tsv").read_bytes()),
                   "stress": digest((ROOT / "qa/lily-motor-stress-cases.tsv").read_bytes())}
    model_hashes = {"v1": digest((MODEL.parent / "water_bc_v1.json").read_bytes()), "contact": digest(MODEL.read_bytes())}
    for label, directory in directories.items():
        matrix, version = label.split("_")
        receipts[label], hashes[label] = receipt(directory, case_hashes[matrix], model_hashes[version])
    result = {"schema": 1, "definitions": DEFINITIONS, "source_receipts": hashes,
              "cases": {}, "physics_transition_check": {}}
    counts = {}
    for matrix in ("original", "stress"):
        v1, contact = matrix + "_v1", matrix + "_contact"
        episodes = sorted(name for (name, arm), row in receipts[contact].items()
                          if arm == "every_tick" and (name.startswith("pool-") if matrix == "original"
                                                      else row["terminal"] == "sim_timeout"))
        counts[matrix] = len(episodes)
        for episode in episodes:
            region = "pool" if "pool" in episode else "shaft"
            result["cases"][episode] = {}
            result["physics_transition_check"][episode] = {}
            for role, label, arm in (("v2", contact, "every_tick"), ("v1", v1, "every_tick"),
                                     ("baseline", v1, "baseline")):
                row = receipts[label][episode, arm]
                trial = directories[label] / f"{episode}-{arm}"
                frames = frame_pairs(trial / "motor.jsonl", row["motor_sha256"])
                result["cases"][episode][role] = summarize(
                    frames, row, trees[region], model["normalization"]["scale"], 44 if region == "pool" else 54)
                log = (trial / "engine.log").read_bytes()
                events = TRANSITION.findall(log)
                result["physics_transition_check"][episode][role] = {
                    "engine_log_sha256": digest(log), "lines": len(events),
                    "transition_sectors": sorted({int(number) for pair in events for number in pair}),
                }
    stress = "nine" if counts["stress"] == 9 else str(counts["stress"])
    original = "three" if counts["original"] == 3 else str(counts["original"])
    result["scope"] = (f"All {stress} contact stress timeouts plus all {original} original pool trials; "
                       "both matched comparison arms for each.")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    labels = ("original_v1", "original_contact", "stress_v1", "stress_contact")
    for label in labels:
        parser.add_argument("--" + label.replace("_", "-"), required=True, type=Path,
                            help="Private evaluation directory containing receipt.json and raw trial subdirectories")
    parser.add_argument("--output", required=True, type=Path, help="Destination for the compact JSON audit")
    args = parser.parse_args()
    try:
        result = audit({label: getattr(args, label) for label in labels})
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"Motor failure audit: {exc}\n")


if __name__ == "__main__":
    main()

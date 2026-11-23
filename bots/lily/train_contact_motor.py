"""One fixed contact/history imitation fit on the frozen v1 training pose groups."""
import argparse
import hashlib
import json
from pathlib import Path

from . import motor_contact, motor_model
from .train_motor import fit_weights

ROOT = Path(__file__).resolve().parents[2]
V1_PATH = ROOT / "bots/lily/models/water_bc_v1.json"
V1_FILE_SHA256 = "eb514ebc9ebd34021be306ab97070177bcadc5f1c16c78f361a9c06f69bae3da"
REFERENCE = ROOT / "qa/lily-bank-task.json"
ON_WATER_SURFACE = 0x100000  # SITH_PF_ONWATERSURFACE


def original_split():
    data = V1_PATH.read_bytes()
    if hashlib.sha256(data).hexdigest() != V1_FILE_SHA256:
        raise ValueError("Original v1 model identity changed.")
    return json.loads(data)["provenance"]


def bounded_bytes(path, limit):
    if path.stat().st_size > limit:
        raise ValueError(f"Evidence file exceeds its bound: {path.name}")
    return path.read_bytes()


def read_trace(path, expected):
    data = bounded_bytes(path, 64 * 1024 * 1024)
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f"Evidence digest mismatch: {path.name}")
    return [json.loads(line) for line in data.splitlines()]


def baseline_rows(frames, native):
    """Join a successful stock replay to its alternating before-state and applied inputs."""
    if len(native) < 3 or len(frames) != 2 * (len(native) - 2):
        raise ValueError("Incomplete baseline motor evidence.")
    start, end = native[0], native[-1]
    goal_position = motor_model.vector(start["position"], 3)
    if (start.get("event") != "assigned" or type(start.get("sector")) is not int
            or end.get("event") != "terminal" or end.get("terminal") != "supported_dry"
            or end.get("sector") != start["sector"] or end.get("dry_steps") != 38
            or motor_model.number(end["health"]) <= 0 or type(end.get("ticks")) is not int
            or end["ticks"] != len(native) - 2 or type(end.get("step")) is not int
            or not 38 <= end["step"] <= 9000):
        raise ValueError("Missing successful stock bank landing.")
    rows, previous, last_step = [], 0, -1
    for tick, control in enumerate(native[1:-1]):
        observed, applied = frames[2 * tick:2 * tick + 2]
        if (observed.get("event"), applied.get("event"), control.get("event")) != ("observation", "input", "control"):
            raise ValueError("Observation/control ordering mismatch.")
        step = control.get("step")
        if (type(step) is not int or not last_step < step < end["step"] or (tick == 0 and step != 0)
                or type(applied.get("source_tick")) is not int or applied["source_tick"] != tick
                or any(type(r.get("tick")) is not int or r["tick"] != tick
                       or type(r.get("step")) is not int or r["step"] != step for r in (observed, applied, control))
                or applied.get("owner") != "baseline" or control.get("owner") != "baseline"):
            raise ValueError("Input is not bound to this baseline control tick.")
        last_step = step
        goal, sense = observed["goal"], observed["sense"]
        flags = observed.get("physics_flags")
        history = motor_contact.contact_history(sense)
        if (type(flags) is not int or not 0 <= flags <= 0xffffffff
                or bool(flags & ON_WATER_SURFACE) != bool(history[0])
                or type(control.get("wet")) is not bool or control["wet"] != (sense["medium"] == "water")
                or sense["buttons"] != previous or goal.get("sector") != start["sector"]
                or motor_model.vector(goal["position"], 3) != goal_position):
            raise ValueError("Observation disagrees with native contact, applied history or assigned goal.")
        axes = motor_model.vector(applied["axes"], 4)
        buttons = applied.get("buttons")
        if (axes != motor_model.vector(control["axes"], 4) or any(abs(x) > 1 for x in axes)
                or type(buttons) is not int or not 0 <= buttons <= 31 or type(control.get("buttons")) is not int
                or buttons != control["buttons"] or type(applied.get("presses")) is not int
                or applied["presses"] != (buttons & ~previous)):
            raise ValueError("Recorded axes, buttons or rising edges disagree with applied inputs.")
        previous = buttons
        remaining = motor_model.remaining_goal(sense["position"], goal_position)
        if remaining is not None:
            rows.append({"features": motor_contact.features(sense, observed["state"], remaining),
                         "target": axes + [float(bool(buttons & 1)), float(bool(buttons & 2))]})
    return rows


def training_rows(directory):
    split = original_split()
    receipt_bytes = bounded_bytes(directory / "receipt.json", 16 * 1024 * 1024)
    receipt = json.loads(receipt_bytes)
    reference_bytes = REFERENCE.read_bytes()
    historical = {r["episode_id"]: r for r in json.loads(reference_bytes)["episodes"] if r["controller"] == "baseline"}
    expected = set(split["train_episode_ids"])
    selected = {}
    for run in receipt["episodes"]:
        name = run["episode_id"]
        if name not in expected or run["controller"] != "baseline":
            continue
        if name in selected:
            raise ValueError(f"Duplicate training episode: {name}")
        selected[name] = run
    if set(selected) != expected:
        raise ValueError("Incomplete original training episode set.")
    rows, sources = [], []
    for name in sorted(expected):
        run, old = selected[name], historical[name]
        if (old["case"] not in split["train_split_groups"] or run.get("case") != old["case"]
                or type(run.get("yaw_deg")) is not int or run["yaw_deg"] != old["yaw_deg"]
                or run.get("ownership_complete") is not True or run.get("physical_success") is not True
                or run.get("terminal") != "supported_dry" or run.get("native_sha256") != old["native_sha256"]):
            raise ValueError(f"Recollection disagrees with original successful baseline: {name}")
        location = directory / (name + "-baseline")
        native = read_trace(location / "native.jsonl", old["native_sha256"])
        observations = read_trace(location / "motor.jsonl", run["motor_sha256"])
        actual = baseline_rows(observations, native)
        rows.extend(actual)
        sources.append(dict(episode_id=name, split_group=old["case"], yaw_deg=old["yaw_deg"], samples=len(actual),
                            native_sha256=old["native_sha256"], motor_sha256=run["motor_sha256"]))
    if len(rows) != split["train_samples"]:
        raise ValueError("Unexpected number of baseline training samples.")
    return rows, {"train_samples": len(rows), "train_split_groups": split["train_split_groups"],
                  "development_split_groups": split["heldout_split_groups"],
                  "development_episode_ids": split["heldout_episode_ids"], "training_sources": sources,
                  "original_model_file_sha256": V1_FILE_SHA256,
                  "baseline_reference_file_sha256": hashlib.sha256(reference_bytes).hexdigest(),
                  "source_receipt_file_sha256": hashlib.sha256(receipt_bytes).hexdigest()}


def fit(directory):
    import numpy as np
    rows, provenance = training_rows(directory)
    x = np.asarray([r["features"] for r in rows], dtype=float)
    y = np.asarray([r["target"] for r in rows], dtype=float)
    weights, _, _ = fit_weights(x, y, x[:0], epochs=200, hidden=32, seed=23, learning_rate=.01)
    provenance.update(method="supervised_behavior_cloning", epochs=200, hidden=32, seed=23,
                      learning_rate=.01, batch_size=128, button_threshold=.5,
                      intended_use="Unpromoted synchronous stock-input bank experiment.")
    return {"schema": 2, "feature_names": list(motor_contact.FEATURES),
            "output_names": list(motor_model.OUTPUTS), **weights, "provenance": provenance}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="Private independent-motor evaluation directory")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise ValueError("Output already exists.")
        data = motor_contact.canonical(fit(args.directory)) + b"\n"
        with args.output.open("xb") as stream:
            stream.write(data)
        print(json.dumps({"model_file_sha256": hashlib.sha256(data).hexdigest()}))
    except (OSError, KeyError, ValueError, TypeError, ImportError) as exc:
        parser.exit(1, f"Contact motor training: {exc}\n")


if __name__ == "__main__":
    main()

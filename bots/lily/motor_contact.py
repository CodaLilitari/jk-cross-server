"""Fixture-only motor policy with measured water contact and preceding applied jump."""
import argparse
import hashlib
import inspect
import json
import math
from pathlib import Path

from . import motor_model
from .motor_model import OUTPUTS, dot, features as base_features, number, remaining_goal, vector

FEATURES = motor_model.FEATURES + ("on_water_surface", "previous_applied_jump")


def contact_history(sense):
    surface = sense.get("on_water_surface")
    buttons = sense.get("buttons")
    if type(surface) is not bool:
        raise ValueError("on_water_surface must be an observed boolean.")
    if type(buttons) is not int or not 0 <= buttons <= 31:
        raise ValueError("buttons must contain the preceding applied button mask.")
    return [float(surface), float(bool(buttons & 1))]


def features(sense, state, goal):
    return base_features(sense, state, goal) + contact_history(sense)


def validate_model(model):
    if not isinstance(model, dict) or type(model.get("schema")) is not int or model["schema"] != 2:
        raise ValueError("Expected a schema-2 contact motor model.")
    if model.get("feature_names") != list(FEATURES) or model.get("output_names") != list(OUTPUTS):
        raise ValueError("Unexpected contact observation/action contract.")
    try:
        width = len(FEATURES)
        means = vector(model["normalization"]["mean"], width)
        scales = vector(model["normalization"]["scale"], width)
        if any(abs(x) > 1e6 for x in means) or any(not 1e-12 <= x <= 1e6 for x in scales):
            raise ValueError("Invalid motor normalization.")
        if len(model["w1"]) != 32 or len(model["w2"]) != len(OUTPUTS):
            raise ValueError("Expected a 17-input, 32-hidden, 6-output network.")
        parameters = vector(model["b1"], 32) + vector(model["b2"], len(OUTPUTS))
        for row in model["w1"]:
            parameters.extend(vector(row, width))
        for row in model["w2"]:
            parameters.extend(vector(row, 32))
        if any(abs(x) > 1e6 for x in parameters):
            raise ValueError("Motor parameters exceed their supported magnitude.")
    except (KeyError, TypeError) as exc:
        raise ValueError("Malformed contact motor network.") from exc
    return model


def predict(model, values):
    validate_model(model)
    norm = model["normalization"]
    inputs = [number((x - m) / s) for x, m, s in
              zip(vector(values, len(FEATURES)), norm["mean"], norm["scale"])]
    hidden = [math.tanh(number(dot(row, inputs) + bias)) for row, bias in zip(model["w1"], model["b1"])]
    logits = [dot(row, hidden) + bias for row, bias in zip(model["w2"], model["b2"])]
    return [math.tanh(x) for x in logits[:4]] + [1. / (1. + math.exp(-max(-40., min(40., x)))) for x in logits[4:]]


def motor_action(model, observation, context):
    directive = context.get("directive") or {}
    if directive.get("goal") != "learned-motor" or context.get("undertaking"):
        raise ValueError("Contact motor requires an independent learned-motor decision.")
    params = directive.get("parameters") or {}
    sense = observation["lily"]["sense"]
    goal = remaining_goal(sense["position"], params["position"], tolerance=.001)
    if goal is None:
        contact_history(sense)
        return {"action": "wait"}
    if goal["distance"] > 100:
        raise ValueError("Learned-motor endpoint must be within 100 game units.")
    duration = params.get("duration_ms", 550)
    if type(duration) is not int or not 1 <= duration <= 600:
        raise ValueError("Motor duration must be 1..600 ms.")
    values = predict(model, features(sense, observation["state"], goal))
    step = dict(zip(OUTPUTS[:4], values[:4]))
    step.update(duration_ms=duration, buttons=int(values[4] >= .5) | (int(values[5] >= .5) << 1))
    return {"action": "motor", "skill": "learned-motor", "steps": [step],
            "goal": {"direction": goal["direction"], "distance": goal["distance"]}}


def canonical(model):
    validate_model(model)
    return json.dumps(model, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def policy_source(model):
    data = canonical(model)
    pieces = ['"""Experimental contact/history bank policy for the synchronous stock-input fixture."""',
              "import math", "ABI_VERSION = 1", "FEATURES = " + repr(FEATURES),
              "OUTPUTS = " + repr(OUTPUTS), "MODEL_SHA256 = " + repr(hashlib.sha256(data).hexdigest()),
              "MODEL = " + repr(json.loads(data))]
    for function in (motor_model.number, motor_model.vector, motor_model.unit, motor_model.dot,
                     motor_model.remaining_goal, motor_model.features):
        pieces.append(inspect.getsource(function))
    pieces.append("base_features = features")
    for function in (contact_history, features, validate_model, predict, motor_action):
        pieces.append(inspect.getsource(function))
    pieces.append("validate_model(MODEL)\n\ndef decide(observation, context):\n    return motor_action(MODEL, observation, context)\n")
    source = "\n\n".join(pieces)
    if len(source.encode()) > 128 * 1024:
        raise ValueError("Export exceeds the policy source-size bound.")
    compile(source, "experimental-contact-motor", "exec")
    return source


def main(argv=None):
    parser = argparse.ArgumentParser(description="Export a standalone fixture policy from frozen contact weights.")
    parser.add_argument("model", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.model.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("Contact motor model is too large.")
        source = policy_source(json.loads(args.model.read_bytes()))
        with args.output.open("xb") as stream:
            stream.write(source.encode("utf-8"))
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Contact motor export: {exc}\n")


if __name__ == "__main__":
    main()

"""Small, inspectable motor-network inference; no training dependency at runtime."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

FEATURES = ("goal_forward", "goal_right", "goal_up", "goal_distance",
            "velocity_forward", "velocity_right", "velocity_up", "head_pitch",
            "supported", "water", "breath", "control_interval", "health", "shields", "mana")
OUTPUTS = ("forward", "strafe", "turn", "pitch", "jump_probability", "duck_probability")


def number(value):
    if type(value) in (int, float):
        try:
            numeric = float(value)
            if math.isfinite(numeric):
                return numeric
        except OverflowError:
            pass
    raise ValueError("Expected a finite motor-model number.")


def vector(value, count):
    if not isinstance(value, (list, tuple)) or len(value) != count:
        raise ValueError("Wrong motor-model vector shape.")
    return [number(x) for x in value]


def unit(value):
    value = vector(value, 3)
    length = number(math.hypot(*value))
    if length < 1e-8:
        raise ValueError("A direction must have nonzero length.")
    return [x/length for x in value]


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def remaining_goal(position, endpoint, tolerance=1e-8):
    """World-space direction and remaining distance to a fixed world endpoint."""
    origin, end = vector(position, 3), vector(endpoint, 3)
    delta = [number(target - start) for start, target in zip(origin, end)]
    distance = number(math.hypot(*delta))
    if distance <= tolerance:
        return None
    return {"position": end, "direction": [x / distance for x in delta], "distance": distance}


def features(sense, state, goal):
    """Physical state plus a relative goal, measured before the labeled input moves.

    Goals use a world-space direction and remaining distance in game units. The
    lateral basis matches JK's facing x up convention. Position itself is omitted
    so a translated/rotated approach does not acquire a different identity.
    """
    facing, up = unit(sense["facing"]), unit(sense["up"])
    right = unit([facing[1]*up[2]-facing[2]*up[1],
                  facing[2]*up[0]-facing[0]*up[2],
                  facing[0]*up[1]-facing[1]*up[0]])
    direction = unit(goal["direction"])
    distance = number(goal["distance"])
    if distance <= 0:
        raise ValueError("Motor goal distance must be positive.")
    velocity = vector(sense["velocity"], 3)
    supported = sense["supported"]
    if supported not in (False, True, 0, 1) or sense["medium"] not in ("air", "water"):
        raise ValueError("Invalid physical support/medium.")
    clip = lambda x, scale=1.: max(-2., min(2., number(x)/scale))
    return [dot(direction, facing), dot(direction, right), dot(direction, up), clip(distance, 2.),
            clip(dot(velocity, facing), 2.), clip(dot(velocity, right), 2.), clip(dot(velocity, up), 2.),
            clip(sense["head_pitch"], 80.), float(bool(supported)), float(sense["medium"] == "water"),
            clip(sense["breath_used_ms"], 20000.), clip(sense["tick_ms"], 100.),
            clip(state["health"], 100.), clip(state["shields"], 200.), clip(state["mana"], 400.)]


def validate_model(model):
    if not isinstance(model, dict) or model.get("schema") != 1:
        raise ValueError("Expected motor-model schema 1.")
    if model.get("feature_names") != list(FEATURES) or model.get("output_names") != list(OUTPUTS):
        raise ValueError("Motor observation/action contract differs.")
    try:
        normalization = model["normalization"]
        means = vector(normalization["mean"], len(FEATURES))
        scale = vector(normalization["scale"], len(FEATURES))
        if any(abs(x) > 1e6 for x in means) or any(not 1e-12 <= x <= 1e6 for x in scale):
            raise ValueError("Normalization is outside the bounded physical feature contract.")
        hidden = len(model["b1"])
        if not 1 <= hidden <= 128 or len(model["w1"]) != hidden or len(model["w2"]) != len(OUTPUTS):
            raise ValueError("Motor network exceeds its supported shape.")
        parameters = vector(model["b1"], hidden) + vector(model["b2"], len(OUTPUTS))
        for row in model["w1"]:
            parameters.extend(vector(row, len(FEATURES)))
        for row in model["w2"]:
            parameters.extend(vector(row, hidden))
        if any(abs(x) > 1e6 for x in parameters):
            raise ValueError("Motor weight magnitude is excessive.")
    except (KeyError, TypeError) as exc:
        raise ValueError("Malformed motor network.") from exc
    return model


def canonical(model):
    validate_model(model)
    return json.dumps(model, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(model):
    return hashlib.sha256(canonical(model)).hexdigest()


def load_model(path):
    path = Path(path)
    if path.stat().st_size > 2*1024*1024:
        raise ValueError("Motor model is too large.")
    return validate_model(json.loads(path.read_text(encoding="utf-8")))


def predict(model, values):
    validate_model(model)
    values = vector(values, len(FEATURES))
    norm = model["normalization"]
    inputs = [number((x-m)/s) for x,m,s in zip(values,norm["mean"],norm["scale"])]
    hidden = [math.tanh(number(dot(row, inputs)+bias)) for row,bias in zip(model["w1"],model["b1"])]
    logits = [dot(row, hidden)+bias for row,bias in zip(model["w2"],model["b2"])]
    return [math.tanh(x) for x in logits[:4]] + [1./(1.+math.exp(-max(-40.,min(40.,x)))) for x in logits[4:]]

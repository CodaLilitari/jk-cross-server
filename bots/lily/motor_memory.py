"""Fixture-only frozen G4 controller with a four-unit, explicit leaky memory residual."""
import hashlib
import inspect
import json
import math

from . import motor_model, motor_contact
from .motor_model import OUTPUTS, dot, number, remaining_goal, vector
from .motor_contact import FEATURES, contact_history, features, validate_model as validate_contact_model

BASE_SHA256 = "83b5d06e4d110d0354c74b74512bbb89f2229d7ae708fc1d4ffac6f816838cf2"
STATE_VERSION = 1


def json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def validate_model(model):
    try:
        if (not isinstance(model, dict) or set(model) != {"schema","base","mode","residual","provenance"}
                or type(model["schema"]) is not int or model["schema"] != 3
                or model["mode"] not in ("carried", "instant") or not isinstance(model["provenance"], dict)):
            raise ValueError("Expected a schema-3 explicit-memory model.")
        validate_contact_model(model["base"])
        if hashlib.sha256(json_bytes(model["base"])).hexdigest() != BASE_SHA256:
            raise ValueError("Memory model requires the exact frozen G4 base.")
        residual = model["residual"]
        if set(residual) != {"w","b","a","o"} or len(residual["w"]) != 4 or len(residual["o"]) != 6:
            raise ValueError("Expected a 17-to-4-to-6 memory residual.")
        values = vector(residual["b"],4) + vector(residual["a"],4)
        for row in residual["w"]:
            values.extend(vector(row,17))
        for row in residual["o"]:
            values.extend(vector(row,4))
        if any(abs(x) > 1000 for x in values):
            raise ValueError("Residual parameter exceeds 1000.")
        json_bytes(model)
    except (KeyError, TypeError) as exc:
        raise ValueError("Malformed memory model.") from exc
    return model


def canonical(model):
    validate_model(model)
    return json_bytes(model)


def initial_state(model, model_sha256=None):
    identity = model_sha256 or hashlib.sha256(canonical(model)).hexdigest()
    return dict(schema=STATE_VERSION, model_sha256=identity, memory=[0.,0.,0.,0.])


def validate_state(model, state, model_sha256=None):
    expected = model_sha256 or hashlib.sha256(canonical(model)).hexdigest()
    if (not isinstance(state, dict) or set(state) != {"schema","model_sha256","memory"}
            or type(state["schema"]) is not int or state["schema"] != STATE_VERSION
            or state["model_sha256"] != expected):
        raise ValueError("Wrong memory state schema or model identity.")
    memory = vector(state["memory"],4)
    if any(abs(x) > 1 for x in memory):
        raise ValueError("Memory state is outside [-1,1].")
    return dict(schema=STATE_VERSION, model_sha256=expected, memory=[x if x else 0. for x in memory])


def step(model, values, memory, tick_ms, validated=False):
    """One pure update; validated is reserved for an already frozen exported model."""
    if not validated:
        validate_model(model)
    values, memory = vector(values,17), vector(memory,4)
    dt = number(tick_ms)
    if not 0 < dt <= 600 or any(abs(m) > 1 for m in memory):
        raise ValueError("Invalid memory interval or previous state.")
    base, residual = model["base"], model["residual"]
    norm = base["normalization"]
    inputs = [number((x-m)/s) for x,m,s in zip(values,norm["mean"],norm["scale"])]
    hidden = [math.tanh(number(dot(row,inputs)+bias)) for row,bias in zip(base["w1"],base["b1"])]
    logits = [dot(row,hidden)+bias for row,bias in zip(base["w2"],base["b2"])]
    current = [math.tanh(number(dot(row,values)+bias)) for row,bias in zip(residual["w"],residual["b"])]
    if model["mode"] == "carried":
        retention = [(.995/(1.+math.exp(-max(-40.,min(40.,a)))))**(dt/40.) for a in residual["a"]]
        current = [rho*previous+(1.-rho)*u for rho,previous,u in zip(retention,memory,current)]
    current = [x if x else 0. for x in current]
    logits = [value+dot(row,current) for value,row in zip(logits,residual["o"])]
    outputs = [math.tanh(x) for x in logits[:4]] + [1./(1.+math.exp(-max(-40.,min(40.,x)))) for x in logits[4:]]
    return outputs, current


def motor_action(model, observation, context, model_sha256=None, validated=False):
    identity = model_sha256 or hashlib.sha256(canonical(model)).hexdigest()
    state = validate_state(model, context.get("state", initial_state(model,identity)), identity)
    directive = context.get("directive") or {}
    if directive.get("goal") != "learned-motor" or context.get("undertaking"):
        raise ValueError("Memory policy requires an independent learned-motor decision.")
    params = directive.get("parameters") or {}
    sense = observation["lily"]["sense"]
    contact_history(sense)
    goal = remaining_goal(sense["position"], params["position"], tolerance=.001)
    if goal is None:
        return {"action":"wait", "state":state}
    if goal["distance"] > 100:
        raise ValueError("Memory endpoint exceeds 100 game units.")
    duration = params.get("duration_ms",550)
    if type(duration) is not int or not 1 <= duration <= 600:
        raise ValueError("Memory motor duration must be 1..600 ms.")
    outputs, carried = step(model, features(sense,observation["state"],goal), state["memory"], sense["tick_ms"], validated)
    action = dict(zip(OUTPUTS[:4],outputs[:4]))
    action.update(duration_ms=duration, buttons=int(outputs[4]>=.5)|(int(outputs[5]>=.5)<<1))
    next_state = dict(schema=STATE_VERSION,model_sha256=identity,memory=carried)
    return dict(action="motor",skill="learned-motor",steps=[action],state=next_state,
                goal={"direction":goal["direction"],"distance":goal["distance"]})


def policy_source(model):
    data = canonical(model)
    pieces = ['"""Frozen experimental explicit-memory policy; measured contact fixture only."""',
              "import math\nimport json\nimport hashlib", "ABI_VERSION = 1", "STATE_VERSION = 1",
              "FEATURES = "+repr(FEATURES), "OUTPUTS = "+repr(OUTPUTS),
              "BASE_SHA256 = "+repr(BASE_SHA256), "MODEL_SHA256 = "+repr(hashlib.sha256(data).hexdigest()),
              "MODEL = "+repr(json.loads(data))]
    for function in (motor_model.number,motor_model.vector,motor_model.unit,motor_model.dot,
                     motor_model.remaining_goal,motor_model.features):
        pieces.append(inspect.getsource(function))
    pieces.append("base_features = features")
    for function in (contact_history,features):
        pieces.append(inspect.getsource(function))
    pieces.append(inspect.getsource(motor_contact.validate_model).replace("def validate_model(","def validate_contact_model(",1))
    for function in (json_bytes,validate_model,canonical,initial_state,validate_state,step,motor_action):
        pieces.append(inspect.getsource(function))
    pieces.append("validate_model(MODEL)\n\ndef decide(observation, context):\n    return motor_action(MODEL, observation, context, MODEL_SHA256, True)\n")
    source = "\n\n".join(pieces)
    if len(source.encode()) > 128*1024:
        raise ValueError("Memory export exceeds 128 KiB.")
    compile(source,"experimental-memory-motor","exec")
    return source

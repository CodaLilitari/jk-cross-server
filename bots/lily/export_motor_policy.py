"""Export a self-contained, hot-reloadable Lily policy with immutable weights."""
from __future__ import annotations

import argparse
import inspect
import json
from pathlib import Path

from . import motor_model


def policy_source(model):
    model=json.loads(motor_model.canonical(model))
    # Exact inference code travels with the weights; the worker needs no NumPy
    # and no import of this checkout. Revisions are ordinary trusted local code.
    pieces=["\"\"\"Learned movement candidate; use a learned-motor directive with a goal.\"\"\"",
            "import math", "ABI_VERSION = 1", "FEATURES = "+repr(motor_model.FEATURES),
            "OUTPUTS = "+repr(motor_model.OUTPUTS),
            "MODEL_SHA256 = "+repr(motor_model.digest(model)),
            "MODEL = "+repr(model)]
    for name in ("number","vector","unit","dot","remaining_goal","features","validate_model","predict"):
        pieces.append(inspect.getsource(getattr(motor_model,name)))
    pieces.append('''
validate_model(MODEL)

def decide(observation, context):
    directive = context.get("directive") or {}
    task = context.get("bank_task")
    if directive.get("goal") == "escape-bank" and (not task or task["status"] != "active"):
        return {"action": "baseline"}
    if context.get("undertaking"):
        return {"action": "wait"}
    if directive.get("goal") == "escape-bank":
        params = task
    elif directive.get("goal") == "learned-motor":
        params = directive.get("parameters") or {}
    else:
        return {"action": "baseline"}
    sense = observation["lily"]["sense"]
    goal = remaining_goal(sense["position"], params["position"], tolerance=.001)
    if goal is None:
        return {"action": "wait"}
    if goal["distance"] > 100:
        raise ValueError("Learned-motor endpoint must be within 100 game units.")
    duration = params.get("duration_ms", 550)
    if type(duration) is not int or not 1 <= duration <= 600:
        raise ValueError("Motor duration must be 1..600 ms.")
    values = predict(MODEL, features(sense, observation["state"], goal))
    buttons = (1 if values[4] >= .5 else 0) | (2 if values[5] >= .5 else 0)
    step = dict(zip(OUTPUTS[:4], values[:4]))
    step.update(duration_ms=duration, buttons=buttons)
    result = {"action": "motor", "skill": "learned-motor", "steps": [step],
              "goal": {"direction": goal["direction"], "distance": goal["distance"]}}
    if directive["goal"] == "escape-bank":
        result["task_id"] = task["task_id"]
    return result
''')
    source="\n\n".join(pieces)+"\n"
    compile(source,"lily-learned-motor","exec")
    if len(source.encode())>128*1024:
        raise ValueError("Export exceeds the policy source-size bound; use a smaller hidden layer.")
    return source


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        model=motor_model.load_model(args.model)
        args.output.write_bytes(policy_source(model).encode("utf-8"))
        print(json.dumps({"model_sha256":motor_model.digest(model),"policy":str(args.output)}))
        return 0
    except (OSError,ValueError) as exc:
        parser.exit(1,"Motor export: "+str(exc)+"\n")


if __name__ == "__main__":
    raise SystemExit(main())

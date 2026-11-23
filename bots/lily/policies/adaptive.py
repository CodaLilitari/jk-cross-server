"""ABI-1 route selector and ordinary-input forward stride / sidestep skills."""
import math

ABI_VERSION = 1
STATE_VERSION = 1


def unit(vector):
    length = math.hypot(*vector)
    return [n / length for n in vector] if length > .001 else [0., 1., 0.]


def motor(skill, sense, distance=.04):
    if type(distance) not in (int, float) or not .001 <= distance <= 100:
        distance = .04
    x, y, _ = unit(sense["facing"])
    if skill == "sidestep":
        # Right basis in Sith coordinates (forward cross up).
        direction = unit([y, -x, 0.])
        steps = [{"duration_ms": 200, "strafe": .85}, {"duration_ms": 100, "strafe": .4}]
    else:
        direction = unit([x, y, 0.])
        steps = [{"duration_ms": 220, "forward": .9}, {"duration_ms": 90, "forward": .45}]
    return {"action": "motor", "skill": skill, "steps": steps, "goal": {"direction": direction, "distance": distance}}


def decide(observation, context):
    if context["undertaking"]:
        return {"action": "wait"}
    directive = context["directive"] or {}
    goal = directive.get("goal", "explore")
    params = directive.get("parameters", {})
    lily = observation["lily"]
    sense = lily["sense"]
    if goal == "baseline":
        return {"action": "baseline"}
    skills = context["skills"]
    skill = params.get("skill")
    if goal == "motor" and skill in ("forward-probe", "sidestep"):
        return motor(skill, sense, params.get("distance", .04))
    choices = (lily.get("offers") or {}).get("choices", [])
    # A nearby peer makes an evasive movement useful even on a mapped level.
    # Try at most one probe between committed routes when choices are available.
    nearby = any(math.dist(sense["position"], peer["position"]) < 1.
                 for peer in sense.get("peers", []))
    poor_routes = bool(choices) and all(context["routes"][str(c["node"])]["probability"] < .4 for c in choices)
    probe = goal == "explore" and not context["state"].get("just_probed") and (nearby or poor_routes)
    if choices and goal != "motor" and not probe:
        def score(offer):
            evidence = context["routes"][str(offer["node"])]
            utility = 2 * math.atan(offer["utility"])
            cost = math.log1p(max(0., offer["cost"])) * .25
            if goal == "resource" and offer["class"] == "item":
                utility += 2
            if goal == "route" and params.get("node") == offer["node"]:
                utility += 8
            # A small repeat-target bonus dampens switching after interruption.
            repeat = .15 if context["state"].get("last_target") == offer["position"] else 0
            return utility - cost + 4 * evidence["probability"] - .12 * (evidence["mean_seconds"] or 0) + repeat
        choice = max(choices, key=score)
        return {"action": "route", "node": choice["node"], "state": {"last_target": choice["position"]}}
    names = ("forward-probe", "sidestep")
    # Unknown alternatives get a chance after enough observations of the winner.
    def skill_score(name):
        evidence = skills[name]
        evasion = .25 if nearby and name == "sidestep" else 0.
        return evidence["probability"] + .35 / math.sqrt(1 + evidence["attempts"]) + evasion

    move = motor(max(names, key=skill_score), sense, params.get("distance", .04))
    move["state"] = {"just_probed": True}
    return move

"""Physical bank outcomes and the conservative live stopping rule."""
import hashlib
import json
import math
import sys


TERMINALS = {
    "supported_dry": True, "died": False, "sim_timeout": False,
    "sampled_dry": None, "budget_elapsed": None, "control_lost": None,
    "fence_changed": None, "directive_ended": None, "restarted": None,
    "unavailable": None, "invalid_evidence": None,
}


def bank_verdict(*, terminal: str, controller: str, wet_takeover: bool,
                 baseline_assisted: bool, ownership_complete: bool) -> dict:
    if (type(terminal) is not str or terminal not in TERMINALS or controller not in ("baseline", "candidate")
            or any(type(v) is not bool for v in (wet_takeover, baseline_assisted, ownership_complete))):
        raise ValueError("Invalid bank outcome or ownership")
    if not ownership_complete:
        attribution = "unknown"
    elif controller == "baseline":
        attribution = "baseline"
    elif not wet_takeover:
        attribution = "no_wet_takeover"
    elif baseline_assisted:
        attribution = "assisted"
    else:
        attribution = "candidate"
    physical = TERMINALS[terminal]
    return dict(terminal=terminal, physical_success=physical, attribution=attribution,
                controller_success=physical if attribution in ("candidate", "baseline") else None)


def bank_id(environment, fence, directive_id):
    identity = [environment, fence["run_id"], fence["world_epoch"], fence["life_epoch"], directive_id]
    return hashlib.sha256(json.dumps(identity, separators=(",", ":")).encode()).hexdigest()


def finite_number(value):
    return type(value) in (int, float) and -sys.float_info.max <= value <= sys.float_info.max


def bank_parameters(params, origin):
    position = params.get("position")
    sector = params.get("sector")
    budget = params.get("budget_seconds", 60)
    if (set(params) - {"position", "sector", "budget_seconds"} or type(position) is not list or len(position) != 3
            or not all(finite_number(v) for v in position) or math.dist(position, origin) > 100
            or type(sector) is not int or not 0 <= sector <= 0x7fffffff
            or not finite_number(budget) or not 1 <= budget <= 60):
        raise ValueError("Invalid bank assignment")
    return dict(position=list(position), sector=sector, budget_seconds=budget)


class BankTask:
    """A sparse observation can end live steering but cannot certify a landing."""
    def __init__(self, record, start_clock):
        self.record = record
        self.outcome = None
        self.wet_takeover = False
        # Stock state and rich sense have different publication cadences. The
        # clock present at assignment (or first dry sense) may precede it.
        self.start_clock = None
        self.last_clock = start_clock
        self.last_sample = self.dry_since = self.dry_clock = None

    def context(self):
        fields = ("task_id", "position", "sector", "budget_seconds")
        return dict(status="closed" if self.outcome else "active",
                    **{k: self.record[k] for k in fields if k in self.record})

    def observe(self, sense, clock):
        if sense["sample_id"] == self.last_sample:
            return None
        self.last_sample = sense["sample_id"]
        if not finite_number(clock) or self.last_clock is None or clock < self.last_clock:
            # A discontinuous clock cannot establish elapsed simulation time for this task.
            self.start_clock = self.dry_since = self.dry_clock = self.last_clock = None
            return None
        if self.start_clock is None and clock > self.last_clock:
            self.start_clock = clock
        if clock - self.last_clock > .25:
            self.dry_since = self.dry_clock = None
        self.last_clock = clock
        if self.start_clock is not None and clock - self.start_clock >= self.record["budget_seconds"]:
            return "budget_elapsed"
        if (sense["medium"] == "air" and sense["supported"]
                and math.dist(sense["position"], self.record["position"]) <= .15):
            if self.dry_clock is None:
                self.dry_clock = clock
            elif self.dry_since is None and clock > self.dry_clock:
                self.dry_since = clock
            if self.dry_since is not None and clock - self.dry_since >= .25:
                return "sampled_dry"
        else:
            self.dry_since = self.dry_clock = None
        return None

"""Deterministic output-head proposals and selection from audited stock water outcomes."""
from copy import deepcopy
import hashlib
import json
import math
import re

import numpy as np

from . import motor_contact


V3_FILE_SHA256 = "e08532a4c1a2f7b0fa88417456d177cedd03c67d26555c4a5be1f4d80b599043"
V3_CANONICAL_SHA256 = "25cd7e67f73a747ee49a257556c068a7aeadd21605466080be3ce96bed74120e"
V3_EXPORT_SHA256 = "f849e6bae2e41e86a3ed70b6df00d6365c1803da9973fbaae6e1db8d26650d51"
# Canonical v3 JSON after removing exactly w2, b2 and provenance.
V3_FROZEN_SHA256 = "78e9dc7439c67fbe72396d87322f1b2f4a21baec5543c18d369421fa55ceebfb"
DIRECTION_SEED = 41023
STEP_BUDGET = 9000


def head(model):
    """Return an independent 6-by-33 array, with each output's bias in its last column."""
    motor_contact.validate_model(model)
    return np.column_stack((model["w2"], model["b2"]))


def candidate_models(incumbent, generation, declaration_sha256):
    """Construct one complete ordered generation before observing any of its outcomes."""
    if type(generation) is not int or not 1 <= generation <= 8:
        raise ValueError("Expected generation 1 through 8")
    if not isinstance(declaration_sha256, str) or not re.fullmatch("[0-9a-f]{64}", declaration_sha256):
        raise ValueError("Expected a lowercase hexadecimal SHA-256 declaration digest")
    parent_sha256 = hashlib.sha256(motor_contact.canonical(incumbent)).hexdigest()
    if generation == 1 and parent_sha256 != V3_CANONICAL_SHA256:
        raise ValueError("Generation 1 requires the exact v3 checkpoint")
    frozen = {key: value for key, value in incumbent.items() if key not in ("w2", "b2", "provenance")}
    frozen_bytes = json.dumps(frozen, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if hashlib.sha256(frozen_bytes).hexdigest() != V3_FROZEN_SHA256:
        raise ValueError("Incumbent has changed v3's frozen fields")

    center = head(incumbent)
    rng = np.random.Generator(np.random.PCG64(DIRECTION_SEED))
    directions = rng.standard_normal((8, 6, 6, 33))[generation - 1]
    axis_scale = .18 / math.sqrt(33)
    button_scale = .65 / math.sqrt(33)
    if generation > 4:
        axis_scale *= .5
        button_scale *= .5
    scales = np.array([axis_scale] * 4 + [button_scale] * 2)[:, None]
    provenance = dict(method="elitist antithetic output-head search",
                      v3=dict(file_sha256=V3_FILE_SHA256, canonical_sha256=V3_CANONICAL_SHA256,
                              export_sha256=V3_EXPORT_SHA256),
                      parent_canonical_sha256=parent_sha256, declaration_sha256=declaration_sha256,
                      generation=generation, seed=DIRECTION_SEED, axis_scale=axis_scale,
                      button_scale=button_scale,
                      frozen_encoder="v3 schema, feature_names, output_names, normalization, w1 and b1")
    prefix = f"g{generation:02d}-c"
    candidates = [dict(candidate_id=prefix + "00", model=incumbent)]
    for direction, noise in enumerate(directions):
        delta = noise * scales
        for sign in (1, -1):
            values = center + sign * delta
            model = deepcopy(frozen)
            model.update(w2=values[:, :-1].tolist(), b2=values[:, -1].tolist(),
                         provenance=deepcopy(dict(provenance, direction=direction, sign=sign)))
            motor_contact.validate_model(model)
            candidates.append(dict(candidate_id=f"{prefix}{len(candidates):02d}", model=model))
    return candidates


def _assignment_ids(ids):
    if isinstance(ids, (str, bytes)):
        raise ValueError("Expected a collection of episode IDs")
    ids = tuple(ids)
    if not ids or any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("Expected nonempty, unique episode IDs")
    return ids


def _winning_steps(rows, expected_ids):
    """Validate every assignment and return the duration of each supported-dry landing."""
    pending = set(expected_ids)
    wins = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Expected an audited episode record")
        episode = row.get("episode_id")
        if not isinstance(episode, str) or episode not in pending:
            raise ValueError(f"Unexpected or repeated episode {episode!r}")
        pending.remove(episode)
        if (row.get("controller") != "every_tick" or row.get("owner") != "model"
                or row.get("ownership_complete") is not True or row.get("baseline_assisted") is not False):
            raise ValueError(f"{episode}: exclusive every-tick model ownership required")
        terminal, steps = row.get("terminal"), row.get("physics_steps")
        if type(steps) is not int or not 1 <= steps <= STEP_BUDGET:
            raise ValueError(f"{episode}: invalid physics-step count")
        success = terminal == "supported_dry"
        if terminal not in ("supported_dry", "died", "sim_timeout") or row.get("physical_success") is not success:
            raise ValueError(f"{episode}: missing or contradictory physical outcome")
        if (success and steps < 38) or (terminal == "sim_timeout" and steps != STEP_BUDGET):
            raise ValueError(f"{episode}: step count disagrees with terminal")
        if success:
            wins[episode] = steps
    if pending:
        raise ValueError(f"Missing episodes: {sorted(pending)}")
    return wins


def score_episodes(rows, expected_ids):
    """Return (wins, negative charged physics steps) for an exact set of audited assignments."""
    ids = _assignment_ids(expected_ids)
    wins = _winning_steps(rows, ids)
    charged = sum(wins.values()) + STEP_BUDGET * (len(ids) - len(wins))
    return len(wins), -charged


def select_generation(candidates, evaluations, expected_ids):
    """Rank all 13 candidates on the same batch, retaining their declared order on ties."""
    ids = _assignment_ids(expected_ids)
    if len(ids) != 8:
        raise ValueError("A generation requires eight assignments")
    names = [c.get("candidate_id") for c in candidates]
    if len(names) != 13 or not isinstance(names[0], str) or not re.fullmatch(r"g0[1-8]-c00", names[0]):
        raise ValueError("Expected a complete declared generation beginning with the incumbent")
    prefix = names[0][:-2]
    if names != [f"{prefix}{i:02d}" for i in range(13)] or set(evaluations) != set(names):
        raise ValueError("Candidate order or evaluation identities disagree with the declared generation")
    scores = {name: score_episodes(evaluations[name], ids) for name in names}
    return dict(selected_id=max(names, key=scores.__getitem__), scores=scores)


def select_development(evaluations, pool_ids, shaft_ids):
    """Select the checkpoint with a strict pool gain that preserves every v3 shaft win."""
    pool_ids, shaft_ids = _assignment_ids(pool_ids), _assignment_ids(shaft_ids)
    ids = _assignment_ids(pool_ids + shaft_ids)
    if (len(pool_ids), len(shaft_ids)) != (24, 8) or set(evaluations) != {"v3", "g4", "g8"}:
        raise ValueError("Development requires v3, g4 and g8 on 24 pool and eight shaft assignments")
    winners = {name: set(_winning_steps(evaluations[name], ids)) for name in ("v3", "g4", "g8")}
    policies = {}
    for name, wins in winners.items():
        regressions = [e for e in shaft_ids if e in winners["v3"] and e not in wins]
        policies[name] = dict(pool_wins=len(wins.intersection(pool_ids)), shaft_wins=len(wins.intersection(shaft_ids)),
                              shaft_regressions=regressions, eligible=not regressions)
    best_pool = policies["v3"]["pool_wins"]
    selected = None
    for name in ("g4", "g8"):
        measured = policies[name]
        if measured["eligible"] and measured["pool_wins"] > best_pool:
            selected, best_pool = name, measured["pool_wins"]
    return dict(selected=selected, policies=policies)

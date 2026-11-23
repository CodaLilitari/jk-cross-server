"""Paired outcome search with a protected anchor set and explicit state ablation."""
from copy import deepcopy
import hashlib
import math
import re

import numpy as np

from . import motor_memory as memory
from . import outcome_search as old


def initial_model(base, mode):
    rng = np.random.Generator(np.random.PCG64(541123))
    retention = [.30,.75,.93,.98]
    model = dict(schema=3,base=deepcopy(base),mode=mode,
                 residual=dict(w=(rng.standard_normal((4,17))/math.sqrt(17)).tolist(), b=[0.]*4,
                               a=[math.log(r/(.995-r)) for r in retention],o=[[0.]*4 for _ in range(6)]),
                 provenance=dict(method="protected leaky residual",initialization_seed=541123))
    return memory.validate_model(model)


def without_history(model):
    memory.validate_model(model)
    if model["mode"] != "carried":
        raise ValueError("No-history intervention requires a carried parent.")
    result = deepcopy(model)
    result["mode"] = "instant"
    result["provenance"] = dict(method="same-weight no-history intervention",parent_canonical_sha256=hashlib.sha256(memory.canonical(model)).hexdigest())
    return result


def candidate_models(incumbent, generation, declaration_sha256):
    memory.validate_model(incumbent)
    if type(generation) is not int or not 1 <= generation <= 8:
        raise ValueError("Expected generation 1..8.")
    if not isinstance(declaration_sha256,str) or not re.fullmatch("[a-f0-9]{64}",declaration_sha256):
        raise ValueError("Expected declaration SHA256.")
    if generation == 1 and incumbent != initial_model(incumbent["base"],incumbent["mode"]):
        raise ValueError("Generation one requires the exact zero-residual initialization.")
    rng = np.random.Generator(np.random.PCG64(541124))
    directions = rng.standard_normal((8,4,100))[generation-1]
    center = incumbent["residual"]
    factor = .5 if generation >= 5 else 1.
    scales = np.array([.15/math.sqrt(17)]*68+[.12]*4+[.35]*4+[.30/2]*16+[.90/2]*8)*factor
    flat = np.concatenate((np.asarray(center["w"]).ravel(),center["b"],center["a"],np.asarray(center["o"]).ravel()))
    prefix = ("r" if incumbent["mode"] == "carried" else "s")+f"-g{generation:02d}-c"
    candidates = [dict(candidate_id=prefix+"00",model=incumbent)]
    parent = hashlib.sha256(memory.canonical(incumbent)).hexdigest()
    for index, noise in enumerate(directions):
        for sign in (1,-1):
            values = flat + sign*scales*noise
            model = deepcopy(incumbent)
            model["residual"] = dict(w=values[:68].reshape(4,17).tolist(),b=values[68:72].tolist(),
                                     a=values[72:76].tolist() if incumbent["mode"]=="carried" else deepcopy(center["a"]),
                                     o=values[76:].reshape(6,4).tolist())
            model["provenance"] = dict(method="paired antithetic residual search",seed=541124,generation=generation,
                                        direction=index,sign=sign,scale_factor=factor,declaration_sha256=declaration_sha256,
                                        parent_canonical_sha256=parent)
            memory.validate_model(model)
            candidates.append(dict(candidate_id=prefix+f"{len(candidates):02d}",model=model))
    return candidates


def select_generation(candidates,evaluations,ids,anchors,pool,shaft,references):
    ids, anchors, pool, shaft = [old._assignment_ids(v) for v in (ids,anchors,pool,shaft)]
    names = [c["candidate_id"] for c in candidates]
    if (len(ids),len(anchors),len(pool),len(shaft)) != (16,8,6,10) or set(pool)&set(shaft) or set(ids)!=set(pool)|set(shaft) or not set(anchors)<=set(shaft):
        raise ValueError("Expected eight protected anchors, six pool and two rotating shaft starts.")
    if (len(names)!=9 or not re.fullmatch(r"[sr]-g0[1-8]-c00",names[0])
            or names != [names[0][:-2]+f"{n:02d}" for n in range(9)] or set(evaluations)!=set(names)
            or set(references)!={"v3","g4"}):
        raise ValueError("Incomplete declared candidate/reference set.")
    wins = {n:old._winning_steps(evaluations[n],ids) for n in names}
    refs = {n:old._winning_steps(references[n],ids) for n in ("v3","g4")}
    protected = set(anchors)&wins[names[0]].keys()&refs["v3"].keys()
    ranks = {}
    for name in names:
        lost = [e for e in anchors if e in protected and e not in wins[name]]
        score = [-sum(e in refs["v3"] and e not in wins[name] for e in shaft),
                 -sum(e in refs["g4"] and e not in wins[name] for e in pool),
                 *old.score_episodes(evaluations[name],ids)]
        ranks[name] = dict(eligible=not lost,lost_retained_anchors=lost,score=score)
    eligible = [n for n in names if ranks[n]["eligible"]]
    return dict(selected_id=max(eligible,key=lambda n:ranks[n]["score"]),candidates=ranks)


def select_open(evaluations,pool,shaft):
    pool,shaft = old._assignment_ids(pool),old._assignment_ids(shaft)
    ids = old._assignment_ids(pool+shaft)
    if (len(pool),len(shaft))!=(24,8) or set(evaluations)!={"v3","g4","static","recurrent","no_history"}:
        raise ValueError("Open regression requires five frozen arms on 24 pool/eight shaft starts.")
    policies = {}
    for name,rows in evaluations.items():
        wins = old._winning_steps(rows,ids)
        policies[name] = dict(pool_wins=sum(e in wins for e in pool),shaft_wins=sum(e in wins for e in shaft),
                              charged_steps=-old.score_episodes(rows,ids)[1],qualified=len(wins)==32)
    eligible = [n for n in ("static","recurrent") if policies[n]["qualified"]]
    selected = min(eligible,key=lambda n:policies[n]["charged_steps"]) if eligible else None
    return dict(selected=selected,policies=policies)

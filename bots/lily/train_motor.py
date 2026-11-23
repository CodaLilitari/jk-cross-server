"""Fit a compact motor policy to outcome-qualified applied-control episodes.

This is behavior cloning, not a competitive-strength or online-RL claim. NumPy
is needed only by fit(); exported inference uses the Python standard library.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import re

from .motor_model import FEATURES, OUTPUTS, canonical, features, remaining_goal, vector


def attribution(row, outcome, attempt):
    """Return the trace producer only for an unambiguous native control sample."""
    if not outcome or outcome.get("physical_success") is not True:
        return None
    policy_hash = row.get("policy_hash")
    if (not isinstance(policy_hash, str) or not re.fullmatch("[0-9a-f]{64}", policy_hash)
            or outcome.get("policy_hash") != policy_hash):
        return None
    run = row.get("run_id")
    if not isinstance(run, str) or not run or run != outcome.get("run_id"):
        return None
    for name in ("world_epoch", "life_epoch"):
        value = row.get(name)
        if type(value) is not int or not 1 <= value <= 0xffffffff or type(outcome.get(name)) is not int or outcome[name] != value:
            return None
    sense = row.get("sense")
    if not isinstance(sense, dict):
        return None
    seq = sense.get("action_seq")
    if (type(seq) is not int or not 0 <= seq <= 0xffffffff or type(outcome.get("action_seq")) is not int
            or outcome["action_seq"] != seq or sense.get("phase") != "running"):
        return None
    if seq == 0:
        if (row.get("controller") == "native-baseline" and run == "stock-water-replay"
                and outcome.get("controller", "native-baseline") == "native-baseline"
                and sense.get("owner") == "baseline" and outcome.get("status") == "completed"
                and outcome.get("criterion") == "38 consecutive supported dry physics steps"):
            return "stock-water-replay"
        return None
    if not attempt or any(attempt.get(k) != row.get(k) for k in ("run_id","policy_hash","episode_id")):
        return None
    for key in ("world_epoch","life_epoch"):
        if type(attempt.get(key)) is not int or attempt[key] != row[key]:
            return None
    revision = int(policy_hash[:8],16) or 1
    if (type(attempt.get("action_seq")) is not int or attempt["action_seq"] != seq
            or type(attempt.get("revision")) is not int or attempt["revision"] != revision
            or type(sense.get("revision")) is not int or sense["revision"] != revision
            or type(attempt.get("sample_id")) is not int or not 1 <= attempt["sample_id"] <= 0xffffffff
            or type(sense.get("owner_sample_id")) is not int or sense["owner_sample_id"] != attempt["sample_id"]
            or attempt.get("kind") != sense.get("owner")):
        return None
    expected_id = f"{run}/{row['world_epoch']}/{row['life_epoch']}/{seq}"
    if (row["episode_id"] == expected_id and (sense.get("owner"),outcome.get("status"))
            in (("motor","motor_goal_reached"),("route","arrived"))):
        return "runtime"
    return None


def dataset(paths):
    """Retain only observed successful episodes with matching applied action IDs."""
    rows, outcomes, attempts = [], {}, {}
    for raw_path in paths:
        path = Path(raw_path)
        if path.stat().st_size > 128*1024*1024:
            raise ValueError("Split traces larger than 128 MiB before training.")
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                if len(line) > 256*1024:
                    raise ValueError("Oversized training trace row.")
                row = json.loads(line)
                if not isinstance(row, dict) or row.get("schema") != 1:
                    raise ValueError("Expected trace schema 1.")
                episode = row.get("episode_id")
                if not isinstance(episode, str) or not episode:
                    continue
                if row.get("event") == "outcome":
                    if episode in outcomes and outcomes[episode] != row:
                        raise ValueError("Conflicting terminal outcomes for one episode.")
                    outcomes[episode] = row
                elif row.get("event") == "attempt":
                    if episode in attempts and attempts[episode] != row:
                        raise ValueError("Conflicting attempts for one episode.")
                    attempts[episode] = row
                elif row.get("event") == "observation" and row.get("goal"):
                    rows.append(row)
                    if len(rows) > 250000:
                        raise ValueError("Training trace exceeds the bounded sample count.")
    accepted=[]
    for row in rows:
        outcome = outcomes.get(row["episode_id"])
        producer = attribution(row,outcome,attempts.get(row["episode_id"]))
        if not producer:
            continue
        sense = row["sense"]
        try:
            goal = row["goal"]
            if "position" in goal:
                goal = remaining_goal(sense["position"], goal["position"])
                if goal is None:
                    continue
            elif producer != "stock-water-replay":
                # Historical live traces repeated their initial displacement
                # without an endpoint. Only the identified baseline fixture
                # already computed a fresh relative goal at every physics tick.
                continue
            inputs = features(sense, row["state"], goal)
            axes = vector(sense["axes"], 4)
            buttons = sense["buttons"]
            if type(buttons) is not int or not 0 <= buttons <= 31 or any(abs(x)>1.00001 for x in axes):
                continue
        except (KeyError, ValueError, TypeError):
            continue
        group=row.get("split_group",row["episode_id"])
        if not isinstance(group,str) or not group:
            raise ValueError("A split group must be a nonempty string.")
        accepted.append({"episode_id":row["episode_id"], "split_group":group, "features":inputs,
            "target":axes+[float(bool(buttons&1)),float(bool(buttons&2))]})
    return accepted


def split_episodes(rows, fraction=.25, seed=0):
    if not 0 < fraction < 1:
        raise ValueError("Holdout fraction must lie between zero and one.")
    episode_groups={}
    for row in rows:
        group=row.get("split_group",row["episode_id"])
        if episode_groups.setdefault(row["episode_id"],group)!=group:
            raise ValueError("One episode has inconsistent split groups.")
    groups = sorted(set(episode_groups.values()))
    if len(groups) < 2:
        raise ValueError("At least two independent successful episode groups are needed for a held-out evaluation.")
    random.Random(seed).shuffle(groups)
    count = max(1, min(len(groups)-1, round(len(groups)*fraction)))
    held = set(groups[:count])
    return ([row for row in rows if episode_groups[row["episode_id"]] not in held],
            [row for row in rows if episode_groups[row["episode_id"]] in held])


def fit_weights(x, y, hx, *, epochs, hidden, seed, learning_rate):
    """Fit on x/y only. hx supplies optional predictions and never enters an update."""
    import numpy as np
    mean=x.mean(axis=0); scale=x.std(axis=0); scale[scale<1e-6]=1.
    x=(x-mean)/scale; hx=(hx-mean)/scale
    rng=np.random.default_rng(seed)
    w1=rng.normal(0,1/math.sqrt(x.shape[1]),(hidden,x.shape[1])); b1=np.zeros(hidden)
    w2=rng.normal(0,1/math.sqrt(hidden),(len(OUTPUTS),hidden)); b2=np.zeros(len(OUTPUTS))
    params=[w1,b1,w2,b2]; moment=[np.zeros_like(p) for p in params]; variance=[np.zeros_like(p) for p in params]
    def forward(xx):
        activation=np.tanh(xx@w1.T+b1)
        z=activation@w2.T+b2
        out=np.concatenate((np.tanh(z[:,:4]),1/(1+np.exp(-np.clip(z[:,4:],-40,40)))),axis=1)
        return activation,out
    initial_predictions=forward(hx)[1]; update=0
    for epoch in range(epochs):
        indices=rng.permutation(len(x))
        for offset in range(0,len(indices),128):
            chosen=indices[offset:offset+128]; xx,yy=x[chosen],y[chosen]
            activation,out=forward(xx)
            derivative=np.empty_like(out)
            derivative[:,:4]=2*(out[:,:4]-yy[:,:4])*(1-out[:,:4]**2)/(len(chosen)*4)
            derivative[:,4:]=(out[:,4:]-yy[:,4:])/(len(chosen)*2)
            dw2=derivative.T@activation; db2=derivative.sum(axis=0)
            hidden_derivative=(derivative@w2)*(1-activation**2)
            grads=[hidden_derivative.T@xx,hidden_derivative.sum(axis=0),dw2,db2]
            update+=1
            for index,(param,gradient) in enumerate(zip(params,grads)):
                moment[index]=.9*moment[index]+.1*gradient
                variance[index]=.999*variance[index]+.001*gradient*gradient
                param-=learning_rate*(moment[index]/(1-.9**update))/(np.sqrt(variance[index]/(1-.999**update))+1e-8)
    weights={"normalization":{"mean":mean.tolist(),"scale":scale.tolist()},
             "w1":w1.tolist(),"b1":b1.tolist(),"w2":w2.tolist(),"b2":b2.tolist()}
    return weights,initial_predictions,forward(hx)[1]


def fit(rows, *, epochs=200, hidden=32, seed=0, holdout=.25, learning_rate=.01):
    if type(epochs) is not int or not 1 <= epochs <= 5000 or type(hidden) is not int or not 1 <= hidden <= 128:
        raise ValueError("Epochs must be 1..5000 and hidden units 1..128.")
    if not math.isfinite(learning_rate) or not 0 < learning_rate <= .1:
        raise ValueError("Learning rate must be in (0,.1].")
    try:
        import numpy as np
    except ImportError as exc:
        raise ValueError("Offline training needs NumPy; deployed inference does not.") from exc
    train, held = split_episodes(rows,holdout,seed)
    x=np.asarray([vector(r["features"],len(FEATURES)) for r in train],dtype=float)
    y=np.asarray([vector(r["target"],len(OUTPUTS)) for r in train],dtype=float)
    hx=np.asarray([vector(r["features"],len(FEATURES)) for r in held],dtype=float)
    hy=np.asarray([vector(r["target"],len(OUTPUTS)) for r in held],dtype=float)
    for targets in (y,hy):
        if np.any(np.abs(targets[:,:4])>1) or np.any((targets[:,4:]<0)|(targets[:,4:]>1)):
            raise ValueError("Demonstration controls are outside the motor action contract.")
    weights,initial_predictions,predicted=fit_weights(x,y,hx,epochs=epochs,hidden=hidden,seed=seed,learning_rate=learning_rate)
    initial=float(np.mean((initial_predictions[:,:4]-hy[:,:4])**2))
    metrics={"method":"behavior_cloning", "seed":seed,"epochs":epochs,
        "train_samples":len(train),"heldout_samples":len(held),
        "train_episode_ids":sorted({r["episode_id"] for r in train}),
        "heldout_episode_ids":sorted({r["episode_id"] for r in held}),
        "train_split_groups":sorted({r.get("split_group",r["episode_id"]) for r in train}),
        "heldout_split_groups":sorted({r.get("split_group",r["episode_id"]) for r in held}),
        "initial_heldout_axis_mse":initial,
        "heldout_axis_mse":float(np.mean((predicted[:,:4]-hy[:,:4])**2)),
        "heldout_button_accuracy":float(np.mean((predicted[:,4:]>=.5)==(hy[:,4:]>=.5))),
        "limitation":"Held-out action fit does not establish successful traversal or stronger gameplay."}
    model={"schema":1,"feature_names":list(FEATURES),"output_names":list(OUTPUTS),
        **weights,
        "provenance":metrics}
    canonical(model)
    return model,metrics


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("traces",nargs="+",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--epochs",type=int,default=200)
    parser.add_argument("--hidden",type=int,default=32)
    parser.add_argument("--seed",type=int,default=0)
    args=parser.parse_args(argv)
    try:
        model,metrics=fit(dataset(args.traces),epochs=args.epochs,hidden=args.hidden,seed=args.seed)
        model["provenance"]["input_sha256"]=[hashlib.sha256(p.read_bytes()).hexdigest() for p in args.traces]
        data=canonical(model)
        args.output.write_bytes(data+b"\n")
        print(json.dumps({"model_sha256":hashlib.sha256(data).hexdigest(),"metrics":metrics},indent=2))
        return 0
    except (OSError,ValueError,KeyError) as exc:
        parser.exit(1,"Motor training: "+str(exc)+"\n")


if __name__ == "__main__":
    raise SystemExit(main())

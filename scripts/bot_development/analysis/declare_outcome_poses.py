#!/usr/bin/env python3
"""Generate independent stock-water start lists from geometry alone."""
import argparse
from collections import defaultdict
import csv
import hashlib
import itertools
import json
import math
from pathlib import Path
import sys
import tempfile

SEED = "41024"
SPLITS = ("train", "development", "sealed")
INPUTS = ("native/tests/stock_water_replay/bank_cases.tsv",
          "qa/lily-motor-stress-cases.tsv", "qa/lily-recovery-fresh-cases.tsv")
LIMIT = 64
HISTORY_FLOOR = {"pool": .075, "shaft": .045}
NEW_POSE_FLOOR = {"pool": .12, "shaft": .08}


def token(*fields):
    return hashlib.sha256("|".join([SEED, *map(str, fields)]).encode("ascii")).digest()


def draw(lo, hi, *fields):
    return lo + int.from_bytes(token(*fields), "big") % (hi - lo + 1)


def groups():
    """Each split gets holds in both distance/depth bands; no cell is reused."""
    for band in range(2):
        pool = [(col, row) for row in range(3*band, 3*band+3) for col in range(5)]
        pool.sort(key=lambda slot: token("allocation", "pool", *slot))
        for slot, split in zip(pool, ["train"]*6 + ["development"]*3 + ["sealed"]*4):
            yield "pool", split, slot
        shaft = list(range(band*5, band*5+5))
        shaft.sort(key=lambda slot: token("allocation", "shaft", slot))
        for slot, split in zip(shaft, ["train"]*2 + ["development"] + ["sealed"]*2):
            yield "shaft", split, (slot,)


def candidate(kind, split, cell, attempt):
    tag = ("sample", kind, *cell, attempt)
    if kind == "pool":
        col, row = cell
        # 5 x 6 disjoint XY cells; choose at most one center per cell.
        lx, ly = -2300000 + 320000*col, 400000 + 250000*row
        bounds = [(lx+80000, lx+240000), (ly+62500, ly+187500), (-660000, -180000)]
    else:
        low = -720000 + 155000*cell[0]
        bounds = [(2942000, 3012000), (-153000, -83000), (low+43000, low+112000)]
    micro = [draw(low, high, *tag, axis) for axis, (low, high) in enumerate(bounds)]
    pos = [f"{item/1_000_000:.6f}" for item in micro]
    fields = {"origin":"41", "wet":"44" if kind == "pool" else "54",
              "dry":"10" if kind == "pool" else "41", "start_sector":"42" if kind == "pool" else "54",
              "control_dt":".040", "flags":"cb4f" if kind == "pool" else "4b4f",
              "health":"100", "endurance_ms":"12000", "pitch":"0", "vertical_speed":"0",
              "yaw_offsets":"-45,45,135,-135" if split == "sealed" else "-90,0,90,180"}
    return dict(fields, **dict(zip("xyz", pos)))


def table(path, rows, columns):
    with path.open("x", newline="") as stream:
        writer = csv.DictWriter(stream, columns, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "map", "source", "output"):
        parser.add_argument("--"+name, type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    sys.path.insert(0, str(args.repo/"scripts/bot_development/analysis"))
    import validate_replay_poses as validator
    point = lambda row: tuple(validator.binary32(row[axis]) for axis in "xyz")
    previous = []
    for name in INPUTS:
        with (args.repo/name).open(newline="") as stream:
            reader = csv.DictReader(stream, delimiter="\t")
            columns = reader.fieldnames
            previous += list(reader)
    if len(previous) != 23:
        raise ValueError("Unexpected historical pose-group count")
    anchored = json.loads((args.repo/"qa/lily-recovery-declaration.json").read_bytes())
    reference = anchored["fresh_evaluation"]["geometry_validation"]
    if validator.digest(args.map) != reference["map_sha256"]:
        raise ValueError("Unexpected owned map identity")
    accepted, assignments, counts = [], [], defaultdict(int)
    labels = {}
    chosen = []
    for kind, split, cell in groups():
        counts[split, kind] += 1
        case = f"outcome-{split}-{kind}-{counts[split, kind]:02d}"
        candidates = [dict(candidate(kind, split, cell, i), case=f"{case}-p{i:02d}") for i in range(LIMIT)]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/"proposals.tsv"
            table(path, candidates, columns)
            verdict = validator.validate(args.source, args.map, path, radius=.065)
        if verdict["engine_input_sha256"] != reference["engine_input_sha256"]:
            raise ValueError("Unexpected geometry validation engine identities")
        failures = defaultdict(int)
        for i, (item, result) in enumerate(zip(candidates, verdict["cases"], strict=True)):
            if not result["sphere_inside"]:
                failures["sphere"] += 1
                continue
            p = point(item)
            hist = [r for r in previous if r["start_sector"] == item["start_sector"]]
            if min(math.dist(p, point(r)) for r in hist) < HISTORY_FLOOR[kind]:
                failures["historic_spacing"] += 1
                continue
            if any(math.dist(p, point(r)) < NEW_POSE_FLOOR[kind] for r in accepted
                   if r["start_sector"] == item["start_sector"]):
                failures["new_spacing"] += 1
                continue
            item["case"] = case
            accepted.append(item)
            chosen.append((split, kind, item))
            labels[case] = split
            assignments.append(dict(case=case, split=split, family=kind, cell=cell,
                                    accepted_proposal=i, rejections=dict(failures)))
            break
        else:
            raise ValueError(f"Declared cell exhausted: {case}")
    if len({point(r) for r in [*previous,*accepted]}) != len(previous) + len(accepted):
        raise ValueError("Duplicate binary32 position")
    geometries = {}
    for split in SPLITS:
        rows = [item for label, kind, item in chosen if label == split]
        path = args.output/f"{split}.tsv"
        table(path, rows, columns)
        result = validator.validate(args.source, args.map, path)
        if not result["all_spheres_inside"]:
            raise ValueError("Final bank is not wholly inside")
        (args.output/f"{split}-geometry.json").write_text(json.dumps(result, indent=2)+"\n")
        geometries[split] = dict(tsv_sha256=result["cases_sha256"], groups=len(rows),
             yaw_trials=result["yaw_trials"], min_sphere_clearance=min(r["conservative_radius_clearance"] for r in result["cases"]))
    spacings = {}
    nearest_rows = {}
    for kind in ("pool", "shaft"):
        new = {split:[r for label, family, r in chosen if label == split and family == kind] for split in SPLITS}
        old = [r for r in previous if r["start_sector"] == new["train"][0]["start_sector"]]
        distances = lambda pairs: min((math.dist(point(a),point(b)), a["case"], b["case"]) for a,b in pairs)
        spacings[kind] = {"cross_split":{}, "within_split":{}, "to_history":{}}
        for a,b in itertools.combinations(SPLITS, 2):
            spacings[kind]["cross_split"][a+"__"+b] = distances(itertools.product(new[a], new[b]))
        for split in SPLITS:
            spacings[kind]["within_split"][split] = distances(itertools.combinations(new[split], 2))
            spacings[kind]["to_history"][split] = distances(itertools.product(new[split], old))
            for row in new[split]:
                others = [s for name in SPLITS if name != split for s in new[name]]
                d1,_,n1 = distances((row,s) for s in others)
                d2,_,n2 = distances((row,s) for s in old)
                nearest_rows[row["case"]] = {"nearest_other_split":n1, "other_split_distance":d1,
                                            "nearest_history":n2, "history_distance":d2}
    report = dict(schema=1, seed=SEED, cells=assignments, historical_sha256={n:validator.digest(args.repo/n) for n in INPUTS},
                  generator_sha256=validator.digest(__file__), radius=.065, history_minimum=HISTORY_FLOOR,
                  accepted_minimum=NEW_POSE_FLOOR, count_old=23, count_new=len(accepted), splits=geometries,
                  distance_units="3-D Euclidean on engine binary32 center coordinates, in game units",
                  nearest_by_family=spacings, nearest_by_group=nearest_rows)
    (args.output/"spacing-and-allocation.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(geometries, indent=2))
    print(json.dumps(spacings, indent=2))


if __name__ == "__main__":
    main()

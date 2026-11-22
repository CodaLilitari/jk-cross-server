"""Compare four-seat trials using the same conservative live clip windows."""
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
from analyze_speedvideo import unique_fresh

WEAPONS = {1: "fists", 2: "Bryar", 3: "E11", 4: "thermal", 5: "bow", 6: "repeater", 7: "rail", 8: "mine", 9: "concussion", 10: "saber"}


def analyze(trace, detail):
    trial = json.loads(gzip.decompress(trace.read_bytes()))
    report = json.loads(detail.read_text())
    result = trial["result"]
    first = result["recording_start_trace_seconds"]
    returned = result["recording_return_trace_seconds"]
    midpoint = (first + returned) / 2
    end = first + result["capture"]["duration_seconds"]
    assert report["clip_window"] == [returned, end]
    by_seat = {}
    for name, info in report["rows"].items():
        samples = [row for row in unique_fresh(trial["observations"][name]) if returned <= row["wall_seconds"] <= end]
        assert len(samples) == info["n"]
        def event_life(t):
            # Assign a life only when the event is bounded by close living publications
            # in the same world/life, allowing up to one second of own-state age.
            before = [row for row in samples if row["wall_seconds"] - midpoint <= t]
            after = [row for row in samples if row["wall_seconds"] - midpoint >= t]
            if not before or not after:
                return None
            lo, hi = before[-1], after[0]
            def key(row):
                return row["world_epoch"], row["life_epoch"]
            if key(lo) != key(hi) or min(lo["state"]["health"], hi["state"]["health"]) <= 0 or hi["wall_seconds"] - lo["wall_seconds"] > 0.8:
                return None
            return key(lo)
        plans, clears, same_identity_revisits = [], [], []
        for event in info["equipment_log"]:
            life = event_life(event["t"])
            if event["event"] == "plan":
                plans.append(event)
                for prev, prev_life in clears:
                    if life is None or life != prev_life or not 0 < float(event["game"]) - float(prev["game"]) < 45:
                        continue
                    if tuple(event[k] for k in ("item","guid","signature")) == tuple(prev[k] for k in ("item","guid","signature")):
                        same_identity_revisits.append({"life": life, "item":event["item"], "guid":event["guid"], "signature":event["signature"],"failed_clip_s": prev["t"], "planned_clip_s":event["t"],"game_s_after_failure":round(float(event["game"])-float(prev["game"]),3)})
            elif event.get("reason") == "air-return":
                clears.append((event, life))
        max_stall = max(info["candidate_stalls"], key=lambda e:e["span"], default=None)
        alive = info["fresh_living_states"]
        selected = {WEAPONS.get(int(k),k): v for k,v in info["living_weapons"].items()}
        guns = {WEAPONS.get(int(e["weapon"]),e["weapon"]) + (" secondary" if e["alternate"]=="1" else " primary") for e in info["fire_input_changes"]}
        gear_reasons = Counter(e.get("reason") for e in info["equipment_log"] if e["event"]=="clear")
        dry_runs = [e for e in info["environment_spans"] if e["value"]=="dry" and e["span"]>=1]
        deltas = Counter(k for entry in info["ammo_increases"] for k in entry["delta"])
        by_seat[name] = {
            "fresh_states":info["n"], "living_states": alive, "living_states_by_life":info["lives"],
            "wet_states":info["living_environment"].get("wet",0), "dry_states":info["living_environment"].get("dry",0),
            "uncertain_sector_states":sum(v for k,v in info["living_environment"].items() if k not in ("wet","dry")),
            "distinct_dry_spans_at_least_1s":len(dry_runs),
            "longest_mapped_dry_span_s":max((e["span"] for e in dry_runs),default=0),
            "seat_score":info["score"],"selected_weapons":selected, "living_states_with_target":info["living_with_target"],
            "recorded_fire_mode_changes":len(info["fire_input_changes"]), "modes_requested":sorted(guns),
            "ammo_increase_samples_by_bin":deltas,"gear_plans":len(plans),
            "pack_plan_events":sum(e.get("pack")=="1" for e in plans), "gear_clear_reasons":gear_reasons,
            "same_life_same_identity_replans_within_45s_of_air_return":same_identity_revisits,
            "longest_horizontal_confinement":max_stall,
            "number_of_horizontal_confinements":len(info["candidate_stalls"]),
            "sum_horizontal_confinements_s":round(sum(e["span"] for e in info["candidate_stalls"]),3),
            "observed_living_movement_same_life_units":info["sampled_same_life_travel_units"],
            "own_state_modes":info["modes"],
        }
    return {"label":result["label"],"wasm":result["shipped_wasm_sha256"],
            "clip_duration":result["capture"]["duration_seconds"],"clip_window":report["clip_window"],
            "command_records":len(trial["directed_commands"]), "command_timestamps":[e.get("wall_seconds") for e in trial["directed_commands"]],
            "seats":by_seat}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    parser.add_argument("--run",nargs=2,type=Path,action="append",required=True,metavar=("TRACE_GZ","DETAIL_JSON"))
    args=parser.parse_args()
    payload=[analyze(trace,detail) for trace,detail in args.run]
    args.output.write_text(json.dumps(payload,indent=2)+"\n")

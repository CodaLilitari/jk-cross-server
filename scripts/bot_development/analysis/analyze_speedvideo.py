"""Summarize the recorded Canyon Oasis clip from its exported telemetry wrapper."""
import argparse
import gzip
import hashlib
import json
import math
import re
from pathlib import Path


POWERS = {"speed": 0x02, "seeing": 0x04, "jump": 0x01}
SPEED_REQUEST = re.compile(r"\bBOT_FORCE_INPUT\b[^\n]*?\bbin=22(?:\s|$)")


def life(row):
    return row["world_epoch"], row["life_epoch"]


def unique_fresh(rows):
    """Keep the first fresh poll of each own-state publication across clip boundaries."""
    seen = set()
    for row in sorted(rows, key=lambda r: r["wall_seconds"]):
        state = row["state"]
        if not row["native_active"] or not 0 <= row["age_seconds"] <= 1:
            continue
        key = (*life(row), state["game_time"])
        if key not in seen:
            seen.add(key)
            yield row


def summarize_power(rows, bit, midpoint):
    def clip(row):
        return round(row["wall_seconds"] - midpoint, 3)

    episodes = []
    previous = None
    previous_on = False
    on_count = 0
    for row in rows:
        state = row["state"]
        on = state["health"] > 0 and bool(state["force_mask"] & bit)
        connected = (
            previous is not None
            and life(row) == life(previous)
            and state["health"] > 0 and previous["state"]["health"] > 0
            and row["wall_seconds"] - previous["wall_seconds"] <= 1.0
            and 0 < state["game_time"] - previous["state"]["game_time"] <= 1.0
        )
        if on:
            on_count += 1
            if not previous_on or not connected:
                episode = {
                    "world_epoch": row["world_epoch"], "life_epoch": row["life_epoch"],
                    "first_active_clip_second": clip(row), "active_states": 0,
                    "entry": "sampled_off_to_on" if connected else "first_seen_active",
                }
                if connected:
                    episode["preceding_inactive_clip_second"] = clip(previous)
                episodes.append(episode)
            episodes[-1]["last_active_clip_second"] = clip(row)
            episodes[-1]["active_states"] += 1
        elif previous_on and connected:
            episodes[-1]["following_inactive_clip_second"] = clip(row)
        previous, previous_on = row, on
    return {
        "alive_active_states": on_count,
        "sampled_off_to_on_transitions": sum(e["entry"] == "sampled_off_to_on" for e in episodes),
        "observed_active_intervals": len(episodes),
        "sum_first_to_last_active_sample_seconds": round(sum(
            e["last_active_clip_second"] - e["first_active_clip_second"] for e in episodes
        ), 3),
        "per_life_intervals": episodes,
    }


def sampled_score(rows, midpoint):
    if not rows:
        return None

    def at(row):
        s = row["state"]
        return {"clip_second": round(row["wall_seconds"] - midpoint, 3),
                "world_epoch": row["world_epoch"], "kills": s["kills"], "deaths": s["deaths"]}

    first, last = at(rows[0]), at(rows[-1])
    delta = {k: last[k] - first[k] for k in ("kills", "deaths")} if first["world_epoch"] == last["world_epoch"] else None
    return {"opening_sample": first, "closing_sample": last, "sampled_delta": delta}


def analyze(path):
    payload = path.read_bytes()
    data = json.loads(gzip.decompress(payload))
    result = data["result"]
    start, returned = result["recording_start_trace_seconds"], result["recording_return_trace_seconds"]
    duration = result["capture"]["duration_seconds"]
    if not all(math.isfinite(x) for x in (start, returned, duration)) or not 0 <= returned - start < duration:
        raise ValueError("Invalid recorder start/return bracket or duration")
    midpoint = (start + returned) / 2
    end = start + duration
    seats = {}
    for seat, all_rows in data["observations"].items():
        rows = [r for r in unique_fresh(all_rows) if returned <= r["wall_seconds"] <= end]
        alive = sum(r["state"]["health"] > 0 for r in rows)
        console = data["qualification"]["console"][seat]
        powers = {name: summarize_power(rows, bit, midpoint) for name, bit in POWERS.items()}
        periods = powers["speed"]["per_life_intervals"]
        seats[seat] = {
            "distinct_fresh_states_in_clip": len(rows),
            "distinct_fresh_alive_states_in_clip": alive,
            "speed_hotkey_requests_in_whole_session_retained_console":
                sum(bool(SPEED_REQUEST.search(message)) for _, _, message in console),
            "powers_in_clip": powers,
            "speed_visual_review_clip_seconds": [
                {"first_active": e["first_active_clip_second"],
                 "interior_active": round((e["first_active_clip_second"] + e["last_active_clip_second"]) / 2, 2)}
                for e in periods
            ],
            "sampled_score_in_clip": sampled_score(rows, midpoint),
        }
    return {
        "input_sha256": hashlib.sha256(payload).hexdigest(), "build": result["build"],
        "wasm_sha256": result["shipped_wasm_sha256"],
        "recorder_start_bracket_trace_seconds": [start, returned], "capture_duration_seconds": duration,
        "included_poll_window_trace_seconds": [returned, end],
        "video_time_uncertainty_from_recorder_start_seconds": round((returned - start) / 2, 6),
        "method": (
            "The poll window is the intersection of all possible capture windows in the recorder call bracket. "
            "Clip timestamps are poll times relative to its midpoint. Telemetry may precede the poll by up to one second. "
            "Fresh driver-active states are deduplicated by world, life and game time before clipping. "
            "Power intervals group consecutive living active states in one life with wall- and game-time gaps of at most one second. "
            "The summed spans omit unsampled endpoints and describe observations, not exact uptime. "
            "First-seen-active can follow a clip boundary, death, life change or gap. Neither episode nor transition counts establish a cast count. "
            "Console bin-22 counts are requests across the entire retained session, including warm-up. Scores use the first and last retained clip samples."
        ),
        "seats": seats,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("telemetry", type=Path)
    print(json.dumps(analyze(parser.parse_args().telemetry), indent=2, allow_nan=False))

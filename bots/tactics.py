"""Named, bounded tactic values for the bots.

This mirrors the table in the engine's src/AI/jkBotTactics.inc. A tactic is a
number the bot's planner or movement code reads on every decision; none of
them writes game state. The wire identifies a tactic by its position in
TACTICS, so new rows are appended and existing rows never move.

Three ways to set them, from most to least permanent:

* compiled defaults (the "default" column);
* a baseline file named by JK_BOT_TACTICS_FILE, written with write_file();
* a live companion "tactics" command, encoded with encode().

Run ``python -m bots.tactics list`` to print the table and presets, or
``python -m bots.tactics write PATH --preset NAME --set name=value`` to
publish a baseline file.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path
import re
import struct
import sys

# name, default, legacy, lowest, highest, meaning
TACTICS = (
    ("value_conc", 18.0, 18.0, 0.0, 40.0, "worth of a missing concussion rifle while healthy"),
    ("value_rail", 12.0, 12.0, 0.0, 40.0, "worth of a missing rail detonator while healthy"),
    ("value_repeater", 10.0, 10.0, 0.0, 40.0, "worth of a missing repeater while healthy"),
    ("value_weapon", 8.0, 8.0, 0.0, 40.0, "worth of any other missing gun"),
    ("explore", 2.4, 2.4, 0.0, 10.0, "weight of places not visited lately"),
    ("explore_wet", 0.0, 1.0, 0.0, 1.0, "share of that weight an underwater place keeps"),
    ("travel_cost", 0.42, 0.42, 0.05, 2.0, "how fast a goal loses appeal with path length"),
    ("pursuit", 9.0, 9.0, 0.0, 40.0, "appeal of hunting a living opponent"),
    ("goal_hold", 14.0, 14.0, 2.0, 60.0, "seconds a chosen goal is kept"),
    ("water_entry_cost", 4.0, 0.0, 0.0, 40.0, "extra path cost of stepping into water"),
    ("dive_min_value", 6.0, 0.0, 0.0, 40.0, "least a submerged pickup must be worth to dive for"),
    ("dive_seconds", 8.0, 8.0, 2.0, 30.0, "seconds underwater before heading for air"),
    ("run", 1.0, 0.0, 0.0, 1.0, "hold the run key on checked open ground (0 or 1)"),
    ("run_brake", 0.8, 0.8, 0.2, 3.0, "stop running this far before a jump, drop, lift, water edge or corner"),
    ("exact_thrust", 1.0, 0.0, 0.0, 1.0, "aim thrust exactly along the wanted direction (0 or 1)"),
    ("strafe_run", 1.0, 0.0, 0.0, 1.0, "use the forward-plus-strafe diagonal on straights (0 or 1)"),
    ("strafe_min_leg", 1.0, 1.0, 0.3, 10.0, "shortest straight run that uses the diagonal"),
    ("confine_radius", 0.35, 0.35, 0.1, 2.0, "staying inside this radius counts as confined"),
    ("confine_seconds", 6.0, 0.0, 0.0, 60.0, "for this long; 0 turns the check off"),
    ("tabu_seconds", 12.0, 12.0, 1.0, 120.0, "first escape avoids the failing places this long; repeats double it"),
    ("combat_strafe", 0.55, 0.55, 0.0, 1.0, "sideways share of gunfight movement"),
    ("gun_far", 2.5, 2.5, 0.3, 20.0, "a gunner advances beyond this range"),
    ("gun_near", 0.75, 0.75, 0.0, 10.0, "a gunner backs off inside this range"),
    ("dive_retry", 45.0, 0.0, 0.0, 300.0, "seconds a way into water is avoided after a wasted dive (0 = no memory)"),
    ("crossing_seconds", 17.0, 0.0, 0.0, 19.0, "air allowed for a swim that comes out on another bank (engine limit 20)"),
    ("swim_pitch", 1.0, 0.0, 0.0, 1.0, "swim steep legs by looking along them and pushing forward"),
    ("run_jump", 1.0, 0.0, 0.0, 1.0, "cross gaps with a jump released at a sprint, using Force Speed and Force Jump"),
    ("dodge_jump", 1.0, 0.0, 0.0, 1.0, "hop over an incoming rocket or charge with a short Force Jump"),
    ("blind_use", 0.0, 1.0, 0.0, 1.0, "press use whenever blocked (1), or only with a switch, door or usable thing in front (0)"),
    ("water_slip", 1.0, 0.0, 0.0, 1.0, "in water on a leg meant for dry ground, replan instead of hopping at the surface"),
    ("conc_alt_range", 1.4, 99.0, 0.0, 99.0, "concussion rifle: beam (alt fire) inside this range, shell beyond it; 99 = old beam-first"),
    ("heavy_hold", 1.0, 0.0, 0.0, 1.0, "keep a heavy gun in hand through a moment without a safe shot"),
    ("item_pull", 2.0, 0.0, 0.0, 99.0, "Force Pull items worth at least this much from where the bot stands; 0 = never"),
    ("hazard_avoid", 1.0, 0.0, 0.0, 1.0, "keep clear of laid mines and resting grenades, in plans and on foot"),
    ("mines", 1.0, 0.0, 0.0, 1.0, "collect sequencer charges and lay proximity mines on item spots just taken"),
    ("thermals", 1.0, 0.0, 0.0, 1.0, "collect thermal detonators and throw them where guns serve badly"),
    ("absorb_reserve", 1.0, 0.0, 0.0, 1.0, "keep mana to raise Absorb while it is down; answer Grip with Protection or Absorb first"),
    ("turn_rate", 1800.0, 0.0, 0.0, 7200.0, "degrees a second the view may turn, through the mouse-look path; 0 = keyboard turn rate"),
    ("jump_memory", 30.0, 0.0, 0.0, 600.0, "seconds a Jump or Force Jump leg that landed elsewhere, and its ledge, are set aside (0 = no memory)"),
    ("quick_respawn", 1.0, 0.0, 0.0, 1.0, "respawn the moment the stock three-second death timer allows (0 or 1)"),
    ("air_health", 0.0, 30.0, 0.0, 100.0, "below this health, head for air even with breath left (0 = breath alone decides)"),
    ("swim_cost", 3.0, 1.0, 1.0, 10.0, "path cost of a leg swum under water per unit of length (1 = same as walking)"),
    ("speed_upkeep", 1.0, 0.0, 0.0, 1.0, "keep Force Speed up on walking legs and in fights, past the Absorb reserve (0 or 1)"),
    ("water_fight", 1.0, 0.0, 0.0, 1.0, "swim and climb out facing the fight and shooting; one swimmer per exit spot (0 or 1)"),
    ("resupply", 1.0, 0.0, 0.0, 1.0, "collect pulled guns, put ammunition first when out of shots, prefer disarmed opponents (0 or 1)"),
    ("fjump_standstill", 1.0, 0.0, 0.0, 1.0, "judge Force Jump legs as flown from a standstill, the way the bot flies them (0 or 1)"),
    ("always_run", 1.0, 0.0, 0.0, 1.0, "run on all dry ground, corners and pickups included; walk only short of a pit, ledge, water or hurtful floor (0 or 1)"),
    ("pull_on_move", 1.0, 0.0, 0.0, 1.0, "keep running through an item Force Pull and run onto the item as it flies in (0 or 1)"),
    ("pack_hunt", 1.0, 0.0, 0.0, 1.0, "find ways to dropped packs from the graph nodes nearest them, and reach packs on pool floors (0 or 1)"),
    ("pack_deny", 3.0, 0.0, 0.0, 20.0, "least worth of a dropped pack holding a loaded concussion rifle, rail detonator or repeater (0 = no floor)"),
    ("lip_escape", 1.0, 0.0, 0.0, 1.0, "on a lip with the centre over a drop: route from the floor underfoot and step back rather than freeze"),
    ("trap_avoid", 1.0, 0.0, 0.0, 1.0, "keep out of an armed or firing level trap's zone, walk out when caught, never press its switch by accident"),
    ("trap_use", 6.0, 0.0, 0.0, 10.0, "longest walk (units of path) to a level trap's switch to spring it on an opponent (0 = never)"),
    ("trap_chance", 0.6, 0.6, 0.0, 1.0, "chance a trap opening is taken"),
    ("jump_margin", 1.0, 0.0, 0.0, 1.0, "accept a running jump only if a launch 15% slow (7% slow with less Force Jump lift) still lands; come back down from a launch far too slow"),
    ("trap_disarm", 1.0, 0.0, 0.0, 1.0, "switch an armed lightning ramp back off once it has stood armed a while with no opponent near it, from farther the longer it stands (up to twice trap_use)"),
    ("field_switch", 1.0, 0.0, 0.0, 1.0, "work a level's force field: a way through it while it is on costs the walk by that side's switch, which the bot presses before crossing; never walk into it while on"),
    ("lift_call", 1.0, 0.0, 0.0, 1.0, "work a lift that will not come or go: press its button on this level, or step off across its threshold and plan again; no blind use presses while waiting (0 or 1)"),
    ("fjump_margin", 1.0, 0.0, 0.0, 1.0, "build a Force Jump leg only if it still flies at 25 frames a second, and fly the check at the averaged frame time (0 or 1)"),
    ("dead_end", 1.0, 0.0, 0.0, 1.0, "with no route out of where it stands, open the floor door it stands on: look down and press use (0 or 1)"),
    ("leg_axis", 1.0, 0.0, 0.0, 1.0, "off a walking leg's line with the straight way to its node blocked, get back onto the line first (0 or 1)"),
    ("lift_hop", 1.0, 0.0, 0.0, 1.0, "leave a ledge halfway up a lift shaft by the lift: onto its deck as it passes or where it stands below (0 or 1)"),
    ("leg_square", 1.0, 0.0, 0.0, 1.0, "pressed against the wall beside a narrow opening, step square onto the leg's line until the body is clear of the jamb (0 or 1)"),
    ("saber_heavy", 1.0, 0.0, 0.0, 1.0, "swing the saber's heavy secondary (160 damage, longest reach) from contact at a target still in reach as it lands; no swing out of contact (0 or 1)"),
)
NAMES = tuple(row[0] for row in TACTICS)
INDEX = {name: index for index, name in enumerate(NAMES)}
DEFAULTS = {row[0]: row[1] for row in TACTICS}
LEGACY = {row[0]: row[2] for row in TACTICS}
RANGES = {row[0]: (row[3], row[4]) for row in TACTICS}
COMMIT_SECONDS = 8
WIRE_PAIRS = 21
RESET = 1
RESET_LEGACY = 2

# Starting points for a coach, not tuned results. Each lists only what
# differs from the defaults and is sent with the reset flag, so the outcome
# does not depend on what was set before. Only default and legacy have been
# through a live match; see docs/BOT_TACTICS.md.
PRESETS = {
    "default": {},
    "legacy": {name: LEGACY[name] for name in NAMES if LEGACY[name] != DEFAULTS[name]},
    "arsenal": {"value_conc": 26.0, "value_rail": 16.0, "value_repeater": 12.0, "pursuit": 6.0},
    "hunter": {"pursuit": 16.0, "travel_cost": 0.3, "explore": 1.2, "gun_far": 1.8, "gun_near": 0.5},
    "standoff": {"pursuit": 6.0, "gun_far": 4.0, "gun_near": 1.5, "combat_strafe": 0.8},
    "dry": {"water_entry_cost": 12.0, "dive_min_value": 12.0, "dive_seconds": 6.0},
}
PRESET_NOTES = {
    "default": "the compiled defaults",
    "legacy": "behaviour before the tactic table: no running, no water policy, no confinement check",
    "arsenal": "collect the heavy guns before looking for a fight",
    "hunter": "go to the opponent and close the distance",
    "standoff": "keep range and strafe more in a gunfight",
    "dry": "stay out of water except for a heavy gun or badly needed health",
}


def validate(values) -> dict[str, float]:
    """Return the values as floats, or raise ValueError naming the problem."""
    if type(values) is not dict:
        raise ValueError("Tactic values must be an object of name: number.")
    checked = {}
    for name, value in values.items():
        if name not in INDEX:
            raise ValueError(f"Unknown tactic: {name!r}.")
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(f"Tactic {name} needs a finite number.")
        low, high = RANGES[name]
        # The engine stores single precision; compare what it will receive.
        sent = struct.unpack("<f", struct.pack("<f", value))[0]
        if not low <= sent <= high:
            raise ValueError(f"Tactic {name} must be within {low:g}..{high:g}.")
        checked[name] = float(value)
    return checked


def resolve(preset=None, values=None, reset=False) -> tuple[bool, dict[str, float]]:
    """Combine a preset with explicit values into (reset, values to send).

    A preset always resets to the compiled defaults first. Explicit values
    are merged on top of the preset, or into the bot's current table when
    there is no preset and reset is false.
    """
    if type(reset) is not bool:
        raise ValueError("reset must be true or false.")
    merged = {}
    if preset is not None:
        if type(preset) is not str or preset not in PRESETS:
            raise ValueError(f"Unknown preset: {preset!r}.")
        merged.update(PRESETS[preset])
        reset = True
    merged.update(validate(values or {}))
    if not merged and not reset:
        raise ValueError("Give a preset, at least one value, or reset.")
    if len(wire(reset, merged)[1]) > WIRE_PAIRS:
        raise ValueError(f"At most {WIRE_PAIRS} values fit one command.")
    return reset, merged


def wire(reset: bool, values: dict[str, float]) -> tuple[int, dict[str, float]]:
    """Flags and the records that reach the same table in the fewest values.

    A reset starts from the compiled defaults, or from the legacy column when
    fewer of the wanted values differ from it.
    """
    if not reset:
        return 0, dict(values)
    wanted = dict(DEFAULTS)
    wanted.update(values)
    from_legacy = {name: wanted[name] for name in NAMES if wanted[name] != LEGACY[name]}
    if len(from_legacy) < len(values):
        return RESET_LEGACY, from_legacy
    return RESET, dict(values)


def encode(reset: bool, values: dict[str, float]) -> bytes:
    """Command payload after the 8-byte deadline: flags, count, records."""
    flags, checked = wire(reset, validate(values))
    if len(checked) > WIRE_PAIRS or (not checked and not reset):
        raise ValueError("Nothing to send, or too many values for one command.")
    records = b"".join(struct.pack("<Bf", INDEX[name], checked[name]) for name in sorted(checked, key=INDEX.get))
    return bytes((flags, len(checked))) + records


def table(preset=None, values=None) -> dict[str, float]:
    """The complete table a preset plus explicit values produces."""
    _, merged = resolve(preset or "default", values)
    return {**DEFAULTS, **merged}


def render_file(values: dict[str, float]) -> str:
    """A complete baseline revision. Names left out keep the compiled default."""
    checked = validate(values)
    lines = ["version=1"]
    for name in NAMES:
        if name in checked:
            lines.append(f"{name}={_number(checked[name])}")
    return "\n".join(lines) + "\n"


def _number(value: float) -> str:
    # The engine's reader accepts digits, one point and a sign: no exponent.
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text if text not in ("", "-0") else "0"


def write_file(path: Path, values: dict[str, float]) -> None:
    """Publish a complete baseline; the bot never sees a partial write."""
    text = render_file(values)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="ascii")
    temporary.chmod(0o600)
    temporary.replace(path)


def describe() -> dict:
    """Everything a coach needs to choose and send tactics."""
    return {"commit_seconds": COMMIT_SECONDS, "max_values_per_command": WIRE_PAIRS,
            "tactics": [{"name": name, "default": default, "legacy": legacy, "min": low, "max": high,
                         "meaning": meaning} for name, default, legacy, low, high, meaning in TACTICS],
            "presets": {name: {"values": dict(values), "meaning": PRESET_NOTES[name]}
                        for name, values in PRESETS.items()}}


ROW = re.compile(r'X\(\s*(\w+)\s*,\s*"(\w+)"\s*,\s*([-\d.]+)f\s*,\s*([-\d.]+)f\s*,\s*([-\d.]+)f\s*,\s*([-\d.]+)f\s*\)')


def engine_rows(source: str) -> list[tuple[str, float, float, float, float]]:
    """Rows of BOT_TACTIC_TABLE as written in jkBotTactics.inc or a patch of it."""
    start = source.index("#define BOT_TACTIC_TABLE(X)")
    body = source[start:source.index("enum {", start)]
    return [(name, float(default), float(legacy), float(low), float(high))
            for _, name, default, legacy, low, high in ROW.findall(body)]


def parse_assignments(items) -> dict[str, float]:
    values = {}
    for item in items or ():
        name, separator, text = item.partition("=")
        if not separator or name in values:
            raise ValueError(f"Expected one name=value per tactic: {item!r}.")
        try:
            values[name] = float(text)
        except ValueError:
            raise ValueError(f"Tactic {name} needs a number: {text!r}.") from None
    return validate(values)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="op", required=True)
    sub.add_parser("list", help="print the tactic table and the presets")
    write = sub.add_parser("write", help="publish a baseline file for JK_BOT_TACTICS_FILE")
    write.add_argument("path", type=Path)
    write.add_argument("--preset", choices=sorted(PRESETS), default="default")
    write.add_argument("--set", action="append", metavar="NAME=VALUE", help="override one tactic; repeatable")
    args = parser.parse_args(argv)
    try:
        if args.op == "list":
            for name, default, legacy, low, high, meaning in TACTICS:
                print(f"{name:17} default {default:<6g} legacy {legacy:<6g} range {low:g}..{high:g}  {meaning}")
            print()
            for name, values in PRESETS.items():
                changes = ", ".join(f"{key}={value:g}" for key, value in values.items()) or "no changes"
                print(f"{name:9} {PRESET_NOTES[name]}: {changes}")
            return 0
        _, merged = resolve(args.preset, parse_assignments(args.set))
        write_file(args.path, merged)
        print(f"Wrote {args.path} ({len(merged)} values differ from the defaults).")
        return 0
    except (OSError, ValueError) as error:
        print(f"Tactics: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

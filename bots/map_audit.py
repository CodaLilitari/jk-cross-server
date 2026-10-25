#!/usr/bin/env python3
"""Audit owned stock JK multiplayer maps against the compiled bot pickup catalog.

No game content is copied to the report. This checks map structure, authored item
bindings, CTF references and classification coverage, not successful traversal or
connected gameplay. The engine builds collision-checked routes at runtime.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from manager.content import archive_index, child_casefold

STOCK_MAPS = {
    "jk1mp": {"m2.jkl", "m4.jkl", "m5.jkl", "m10.jkl", "m_boss15.jkl", "m_boss17.jkl"},
    "jk1ctf": {"c1.jkl", "c2.jkl", "c3.jkl"},
}


def pickup_catalog(source: str) -> dict[str, str]:
    rows = re.findall(r'\{"([^"\n]+)","([^"\n]+)",\{BOT_ITEM_([A-Z_]+),', source)
    if not rows:
        raise ValueError("No Bot_ClassifyPickup table found in engine source or published bot patch")
    result: dict[str, str] = {}
    for template, model, kind in rows:
        result[template.casefold()] = kind.casefold()
        result[model.casefold()] = kind.casefold()
    return result


def parse_jkl(text: str) -> dict:
    """Parse only metadata needed by the audit, preserving inherited templates."""
    section = ""
    templates: dict[str, dict[str, str]] = {}
    things: dict[int, dict] = {}
    cogs: list[dict] = []
    counts: dict[str, int] = {}
    errors: list[str] = []
    for original in text.splitlines():
        line = original.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.fullmatch(r"(?i)section:\s*(\w+)", line)
        if match:
            section = match[1].lower()
            continue
        match = re.fullmatch(r"(?i)world\s+(vertices|surfaces|sectors|things)\s+(\d+)", line)
        if match:
            counts[match[1].lower()] = int(match[2])
        if section == "templates":
            row = line.split()
            if len(row) < 2 or row[0].lower() in {"world", "end"}:
                continue
            name, base = (v.casefold() for v in row[:2])
            if base != "none" and base not in templates:
                errors.append(f"Template {name} has unknown earlier base {base}")
            props = templates.get(base, {}).copy()
            props.update({k.casefold(): v.casefold() for k, v in re.findall(r"(\w+)=([^\s]+)", line)})
            templates[name] = props
        elif section == "things":
            row = line.split()
            if not row or not re.fullmatch(r"\d+:", row[0]):
                continue
            if len(row) < 10:
                errors.append("Incomplete thing row")
                continue
            try:
                index = int(row[0][:-1]); name = row[1].casefold()
                if name not in templates:
                    raise ValueError(f"Thing {index} has unknown template {name}")
                if index in things:
                    raise ValueError(f"Duplicate thing {index}")
                props = templates[name].copy()
                props.update({k.casefold(): v.casefold() for k, v in re.findall(r"(\w+)=([^\s]+)", line)})
                things[index] = {"template": name, "position": tuple(float(x) for x in row[3:6]),
                                 "sector": int(row[9]), "properties": props}
            except ValueError as exc:
                errors.append(str(exc))
        elif section == "cogs":
            row = line.split()
            if len(row) >= 2 and re.fullmatch(r"\d+:", row[0]):
                cogs.append({"script": row[1].casefold(), "args": row[2:]})
    for index, thing in things.items():
        if not 0 <= thing["sector"] < counts.get("sectors", 0):
            errors.append(f"Thing {index} references invalid sector")
        if index >= counts.get("things", 0):
            errors.append(f"Thing {index} exceeds reserved capacity")
    return {"counts": counts, "things": things, "cogs": cogs, "errors": errors}


def audit_map(name: str, data: bytes, catalog: dict[str, str], *, ctf: bool) -> dict:
    parsed = parse_jkl(data.decode("latin-1"))
    categories: Counter[str] = Counter()
    unknown: Counter[str] = Counter()
    starts = paths = 0
    for thing in parsed["things"].values():
        props = thing["properties"]
        if props.get("type") == "player":
            starts += 1
        if props.get("move") == "path" and int(props.get("numframes", "0")) > 1:
            paths += 1
        if props.get("type") != "item":
            continue
        category = catalog.get(thing["template"], catalog.get(props.get("model3d", "")))
        if category:
            categories[category] += 1
        else:
            unknown[thing["template"]] += 1
    errors = list(parsed["errors"])
    bindings = None
    if ctf:
        instances = [c for c in parsed["cogs"] if c["script"] == "ctf_main.cog"]
        if len(instances) != 1:
            errors.append("CTF requires exactly one stock CTF_MAIN instance")
        else:
            try:
                args = instances[0]["args"]
                indices = [int(x) for x in args[:7]]
                if len(indices) != 7:
                    raise ValueError("CTF_MAIN has incomplete initial binding list")
                red, gold, red_base, gold_base, lobby, red_mark, gold_mark = indices
                if red == gold or red_mark == gold_mark:
                    raise ValueError("CTF team objects/sectors must be distinct")
                for index in (red, gold, red_base, gold_base):
                    if index not in parsed["things"]:
                        raise ValueError("CTF_MAIN references an absent flag or base thing")
                for index in (lobby, red_mark, gold_mark):
                    if not 0 <= index < parsed["counts"].get("sectors", 0):
                        raise ValueError("CTF_MAIN references an invalid lobby/team sector")
                if parsed["things"][red]["template"] != "ctf_redflag" or parsed["things"][gold]["template"] != "ctf_goldflag":
                    raise ValueError("CTF_MAIN flag references are not stock flag templates")
                bindings = {"validated": True, "flags": 2, "bases": 2, "selection_sectors": 2,
                            "team_selection": "walk_into_mark_sector", "capture": "touch_own_flag_at_home_while_carrying_enemy_flag"}
            except ValueError as exc:
                errors.append(str(exc))
    return {"map": name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
            "world": parsed["counts"], "authored_things": len(parsed["things"]),
            "player_starts": starts, "path_movers": paths,
            "item_count": sum(categories.values()) + sum(unknown.values()),
            "classified_items": sum(categories.values()), "item_categories": dict(sorted(categories.items())),
            "unclassified_templates": dict(sorted(unknown.items())), "ctf_bindings": bindings,
            "errors": errors, "status": "structure_and_pickup_catalog_pass" if not errors and not unknown else "needs_review"}


def audit(data: Path, source: Path) -> dict:
    catalog = pickup_catalog(source.read_text())
    episode_dir = child_casefold(data, "episode")
    if episode_dir is None:
        raise ValueError("Game data needs an episode directory")
    report = {"schema": 1, "scope": "original JKDF2 stock multiplayer maps",
              "evidence": "read_only_archive_structure_and_pickup_classification",
              "not_established": ["collision-route reachability", "complete traversal", "CTF captures", "live multiplayer compatibility"],
              "classifier_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "episodes": []}
    for episode, expected in STOCK_MAPS.items():
        archive = child_casefold(episode_dir, episode + ".gob")
        if archive is None:
            report["episodes"].append({"episode": episode, "status": "missing_owned_archive", "maps": []})
            continue
        entries = archive_index(archive)
        maps = {Path(e["name"]).name.casefold(): e for e in entries if e["name"].lower().endswith(".jkl")}
        missing = expected - maps.keys()
        rows = []
        with archive.open("rb") as handle:
            for name in sorted(expected & maps.keys()):
                entry = maps[name]
                if entry["size"] > 32 * 1024 * 1024:
                    raise ValueError("Stock map audit size limit exceeded")
                handle.seek(entry["offset"])
                rows.append(audit_map(name, handle.read(entry["size"]), catalog, ctf=episode == "jk1ctf"))
        report["episodes"].append({"episode": episode, "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                                   "missing_maps": sorted(missing), "maps": rows,
                                   "status": "pass" if not missing and all(r["status"] == "structure_and_pickup_catalog_pass" for r in rows) else "needs_review"})
    report["status"] = "pass" if all(e["status"] == "pass" for e in report["episodes"]) else "incomplete"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-data", required=True, type=Path)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1] / "native/bot-client.patch",
                        help="jkBotNavigation.inc or the published bot-client.patch containing its catalog")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(args.game_data, args.source)
    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    else:
        print(text, end="")
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())

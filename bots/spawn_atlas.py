"""Export authored JKDF2 stock multiplayer player-start metadata from owned archives."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from bots.map_audit import STOCK_MAPS, parse_jkl
from manager.content import archive_index, child_casefold


def build_map_atlas(name: str, data: bytes) -> dict:
    parsed = parse_jkl(data.decode("latin-1"))
    errors = list(parsed["errors"])
    starts = []
    for index, thing in parsed["things"].items():
        if thing["properties"].get("type") == "player":
            starts.append({"source_kind": "authored_player_thing", "engine_eligibility": "not_checked",
                           "thing_index": index, **thing})
    if not starts:
        errors.append("No authored player starts found")
    return {"map": name, "sha256": hashlib.sha256(data).hexdigest(), "world": parsed["counts"],
            "authored_things": len(parsed["things"]), "player_starts": len(starts),
            "starts": starts, "errors": errors, "status": "incomplete" if errors else "pass"}


def _read_episode(episode_dir: Path, episode: str, expected: set[str]) -> dict:
    errors = []
    maps = []
    result = {"episode": episode, "maps": maps, "errors": errors}
    try:
        archive = child_casefold(episode_dir, episode + ".gob")
        if archive is None:
            raise ValueError(f"Missing archive {episode}.gob")
        entries = {}
        for entry in archive_index(archive):
            name = Path(entry["name"]).name.casefold()
            if name in expected:
                if name in entries:
                    raise ValueError(f"Ambiguous map basename {name} in {archive.name}")
                entries[name] = entry
        missing = sorted(expected - entries.keys())
        result["missing_maps"] = missing
        if missing:
            errors.append("Missing maps: " + ", ".join(missing))
        with archive.open("rb") as handle:
            result["archive_sha256"] = hashlib.file_digest(handle, "sha256").hexdigest()
            for name, entry in sorted(entries.items()):
                if entry["size"] > 32 * 1024 * 1024:
                    raise ValueError(f"{name} exceeds the stock map audit size limit")
                handle.seek(entry["offset"])
                data = handle.read(entry["size"])
                if len(data) != entry["size"]:
                    raise ValueError(f"Incomplete archive entry {name}")
                row = build_map_atlas(name, data)
                maps.append(row)
                if row["errors"]:
                    errors.append(f"{name} failed map validation")
    except (OSError, ValueError) as exc:
        errors.append(str(exc))
    result["status"] = "incomplete" if errors else "pass"
    return result


def build_atlas(data: Path) -> dict:
    episodes = []
    errors = []
    try:
        directory = child_casefold(data, "episode")
        if directory is None or not directory.is_dir():
            raise ValueError("Game data needs an Episode directory")
        for episode, expected in STOCK_MAPS.items():
            row = _read_episode(directory, episode, expected)
            episodes.append(row)
            if row["errors"]:
                errors.append(f"{episode} failed archive or map validation")
    except (OSError, ValueError) as exc:
        errors.append(str(exc))
    return {"schema": 1, "episodes": episodes, "errors": errors, "status": "incomplete" if errors else "pass"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-data", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists() and args.game_data.is_dir():
        archive_names = {name + ".gob" for name in STOCK_MAPS}
        for directory in args.game_data.iterdir():
            if directory.name.casefold() != "episode" or not directory.is_dir():
                continue
            for archive in directory.iterdir():
                if archive.name.casefold() in archive_names and archive.exists() and args.output.samefile(archive):
                    parser.error(f"Output identifies an input game archive: {archive}")
    report = build_atlas(args.game_data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())

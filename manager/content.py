"""Read resource catalogs and validate the selected game content."""
from __future__ import annotations
import hashlib
import re
import struct
from pathlib import Path
from .config import ConfigError

def child_casefold(parent: Path, name: str) -> Path | None:
    matches = [p for p in parent.iterdir() if p.name.casefold() == name.casefold()]
    if len(matches) > 1:
        raise ConfigError(f"Ambiguous case variants for {name} in {parent}.")
    return matches[0] if matches else None

def archive_index(path: Path) -> list[dict]:
    size = path.stat().st_size
    with path.open("rb") as f:
        header = f.read(12)
        if len(header) != 12 or header[:4] != b"GOB " or struct.unpack_from("<I", header, 4)[0] != 20:
            raise ConfigError(f"{path.name} is not a GOB/GOO archive.")
        offset = struct.unpack_from("<I", header, 8)[0]
        if not 12 <= offset <= size - 4:
            raise ConfigError(f"Invalid index in {path.name}.")
        f.seek(offset)
        count = struct.unpack("<I", f.read(4))[0]
        if count > 100000 or offset + 4 + count * 136 > size:
            raise ConfigError(f"Invalid archive entry count in {path.name}.")
        entries, names = [], set()
        for _ in range(count):
            row = f.read(136)
            start, length = struct.unpack_from("<II", row)
            name = row[8:].split(b"\0", 1)[0].decode("ascii").replace("\\", "/")
            if start + length > size or name.casefold() in names:
                raise ConfigError(f"Invalid or duplicate entry in {path.name}: {name}.")
            names.add(name.casefold())
            entries.append({"name": name, "offset": start, "size": length})
        return entries

def catalog(data: Path) -> dict:
    if not data.is_dir():
        raise ConfigError("Game data directory does not exist.")
    episode_dir = child_casefold(data, "episode")
    resource_dir = child_casefold(data, "resource")
    if not episode_dir or not resource_dir or not episode_dir.is_dir() or not resource_dir.is_dir():
        raise ConfigError("The game data folder must contain resource and episode directories.")
    episodes, errors = [], []
    for path in sorted(episode_dir.iterdir(), key=lambda p: p.name.casefold()):
        if path.suffix.casefold() not in (".gob", ".goo") or not path.is_file():
            continue
        try:
            entries = archive_index(path)
            maps = sorted(Path(x["name"]).name for x in entries if x["name"].lower().endswith(".jkl"))
            ep = next((x for x in entries if x["name"].casefold() == "episode.jk"), None)
            if not ep or ep["size"] > 1024 * 1024:
                raise ConfigError("Missing or oversized episode.jk")
            with path.open("rb") as f:
                f.seek(ep["offset"])
                text = f.read(ep["size"]).decode("latin-1")
            kind = re.search(r"(?im)^\s*TYPE\s+(\d+)\b", text)
            episode_type = int(kind[1]) if kind else 0
            # Stock JK1CTF declares TYPE 8 (special/CTF), independently of
            # the deathmatch and cooperative episode bits.
            if maps and episode_type & 14:
                episodes.append({"episode": path.stem, "file": path.name, "maps": maps,
                                 "type": episode_type, "title": text.splitlines()[0].strip('"'),
                                 "size": path.stat().st_size})
        except (ValueError, OSError) as exc:
            errors.append({"file": path.name, "error": str(exc)})
    return {"episodes": episodes, "errors": errors}

def preflight(config: dict) -> dict:
    data = Path(config["game_data"])
    result = catalog(data)
    match = next((e for e in result["episodes"] if e["episode"].casefold() == config["episode"].casefold()), None)
    if not match:
        raise ConfigError(f"Episode {config['episode']} was not found in the game data folder.")
    if config["map"].casefold() not in {m.casefold() for m in match["maps"]}:
        raise ConfigError(f"Map {config['map']} was not found in {match['file']}.")
    resources = child_casefold(data, "resource")
    names = {p.name.casefold() for p in resources.iterdir() if p.is_file()}
    if "jk_.cd" not in names:
        raise ConfigError("Missing resource/jk_.cd game-data marker. Select a complete installed game data folder, including its original marker file.")
    required = ("jkmres.goo",) if config["game"] == "mots" else ("res2.gob",)
    missing = [name for name in required if name not in names]
    if config["game"] == "jk" and not {"res1.gob", "res1hi.gob", "res1low.gob"} & names:
        missing.append("res1.gob, res1hi.gob, or res1low.gob")
    if config["game"] == "mots" and not {"jkmsnd.goo", "jkmsndlo.goo"} & names:
        missing.append("jkmsnd.goo or jkmsndlo.goo")
    if missing:
        raise ConfigError("Missing required resources: " + ", ".join(missing))
    episode_path = child_casefold(data, "episode") / match["file"]
    hasher = hashlib.sha256()
    with episode_path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(block)
    return {"game": config["game"], "episode": match["file"], "map": config["map"],
            "episode_sha256": hasher.hexdigest(), "catalog": result,
            "note": "Archive hashes identify content; connected gameplay is a separate check."}

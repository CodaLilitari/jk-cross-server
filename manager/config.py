"""Validated configuration. Process arguments never pass through a shell."""
from __future__ import annotations
import copy
import ipaddress
import json
import os
import re
from pathlib import Path
from bots.settings import PROFILE_IDS, check_scope, engine_path

DEFAULT = {
    "version": 1, "game": "jk", "name": "JK Cross Server",
    "episode": "JK1MP", "map": "m2.jkl", "max_players": 7,
    "rank": 0, "tick_ms": 100, "score_limit": 0, "time_limit": 0,
    "teams": False, "game_flags": 0, "password": "",
    "native_port": 3500, "ipc_port": 46000, "broker_port": 46001,
    "engine": "", "game_data": "", "mod_dir": "", "web_client": "",
    "web_enabled": True, "web_asset_downloads": True,
    "web_bind": "127.0.0.1", "web_port": 8787,
    "web_origins": [], "web_ice_servers": [], "retail_enabled": False, "directplay_bridge": "",
    "wine": "", "wine_prefix": "", "auto_restart": False,
    "bots_enabled": False, "bots_profiles": ["boba_fett", "jan_ors"],
    "bots_sabers_only": False, "bots_fists_peace": True,
    "bots_force_enabled": True, "bots_taunts": True, "bots_engine": "",
}

class ConfigError(ValueError):
    pass

def validate(value: dict, *, require_paths: bool = False) -> dict:
    if not isinstance(value, dict):
        raise ConfigError("Configuration must be a JSON object.")
    extra = set(value) - set(DEFAULT)
    if extra:
        raise ConfigError("Unknown settings: " + ", ".join(sorted(extra)))
    out = copy.deepcopy(DEFAULT)
    out.update(value)
    if out["game"] == "mots" and "rank" not in value:
        out["rank"] = 7
    if out["version"] != 1 or out["game"] not in ("jk", "mots"):
        raise ConfigError("Use configuration version 1 and game jk or mots.")
    for key in ("name", "password"):
        text = out[key]
        if not isinstance(text, str) or len(text.encode("utf-16-le")) > 62:
            raise ConfigError(f"{key} must fit 31 UTF-16 code units.")
        if any(ord(c) < 32 or c == ":" for c in text):
            raise ConfigError(f"{key} contains a reserved character.")
    if not out["name"]:
        raise ConfigError("Server name cannot be empty.")
    for key in ("episode", "map"):
        text = out[key]
        if not isinstance(text, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,31}", text) or ".." in text:
            raise ConfigError(f"{key} must be a plain ASCII resource name, up to 31 characters.")
    if not out["map"].lower().endswith(".jkl"):
        raise ConfigError("Map must end in .jkl.")
    if Path(out["episode"]).suffix.lower() in (".gob", ".goo"):
        out["episode"] = Path(out["episode"]).stem
    limits = {
        "max_players": (1, 31), "rank": (0, 8), "tick_ms": (10, 1000),
        "score_limit": (0, 9999), "time_limit": (0, 9999), "game_flags": (0, 0xFFFF),
        "native_port": (1024, 65535), "ipc_port": (1024, 65535),
        "broker_port": (1024, 65535), "web_port": (1024, 65535),
    }
    for key, (lo, hi) in limits.items():
        if type(out[key]) is not int or not lo <= out[key] <= hi:
            raise ConfigError(f"{key} must be an integer from {lo} to {hi}.")
    if out["game"] == "mots" and not out["game_flags"] & 0x1000 and out["rank"] < 7:
        raise ConfigError("MotS personality sessions need advertised rank 7 or 8 for unchanged native clients. Use rank 7, or enable ranked-Jedi flag 4096 for a ranked session.")
    if len({out[x] for x in ("ipc_port", "broker_port", "web_port")}) != 3:
        raise ConfigError("IPC, broker, and browser ports must be distinct.")
    for key in ("teams", "web_enabled", "web_asset_downloads", "retail_enabled", "auto_restart",
                "bots_enabled", "bots_sabers_only", "bots_fists_peace", "bots_force_enabled", "bots_taunts"):
        if type(out[key]) is not bool:
            raise ConfigError(f"{key} must be true or false.")
    profiles = out["bots_profiles"]
    if (not isinstance(profiles, list) or not 1 <= len(profiles) <= 4
            or any(not isinstance(item, str) or item not in PROFILE_IDS for item in profiles)
            or len(set(profiles)) != len(profiles)):
        raise ConfigError("bots_profiles must select one to four distinct stock bot profile ids.")
    if out["bots_enabled"]:
        try:
            check_scope(out, len(profiles))
        except ValueError as exc:
            raise ConfigError(str(exc)) from None
    if out["retail_enabled"]:
        if out["max_players"] > 15:
            raise ConfigError("Mixed retail sessions support at most 15 configured slots, including the dedicated host.")
        if not 100 <= out["tick_ms"] <= 300:
            raise ConfigError("Retail session tick interval must be 100–300 ms.")
    try:
        ipaddress.ip_address(out["web_bind"])
    except (ValueError, TypeError):
        raise ConfigError("web_bind must be a literal IP address.") from None
    if not isinstance(out["web_origins"], list) or any(not isinstance(s, str) or not re.fullmatch(r"https?://[^/\s]+", s) for s in out["web_origins"]):
        raise ConfigError("web_origins must be a list of exact http(s) origins.")
    if not isinstance(out["web_ice_servers"], list) or len(out["web_ice_servers"]) > 8:
        raise ConfigError("web_ice_servers must be an array of at most eight ICE server objects.")
    for server in out["web_ice_servers"]:
        if not isinstance(server, dict) or set(server) - {"urls", "username", "credential"}:
            raise ConfigError("Each ICE server accepts urls, username, and credential.")
        urls = server.get("urls")
        urls = [urls] if isinstance(urls, str) else urls
        if not isinstance(urls, list) or not 1 <= len(urls) <= 8 or any(
            not isinstance(url, str) or len(url) > 512 or not re.fullmatch(r"(?:stun|stuns|turn|turns):[^\s]+", url)
            for url in urls
        ):
            raise ConfigError("Each ICE server needs one or more stun:, stuns:, turn:, or turns: URLs.")
        if any(not isinstance(server.get(key, ""), str) or len(server.get(key, "")) > 1024
               for key in ("username", "credential")):
            raise ConfigError("ICE usernames and credentials must be strings of at most 1024 characters.")
    for key in ("engine", "game_data", "mod_dir", "web_client", "directplay_bridge", "wine", "wine_prefix", "bots_engine"):
        if not isinstance(out[key], str) or "\0" in out[key]:
            raise ConfigError(f"{key} must be a filesystem path.")
        if out[key]:
            out[key] = str(Path(out[key]).expanduser().resolve())
    if require_paths:
        if out["bots_enabled"]:
            import sys
            if sys.platform != "linux":
                raise ConfigError("The packaged bot clients currently require a Linux server host.")
            bot_engine = engine_path(out)
            if not bot_engine.is_file() or not os.access(bot_engine, os.X_OK):
                raise ConfigError(f"Bot executable is missing or not executable: {bot_engine}")
        if not Path(out["engine"]).is_file():
            raise ConfigError("Choose a built JK Cross Server engine executable.")
        if not out["game_data"] or not Path(out["game_data"]).is_dir():
            raise ConfigError("Choose your installed game's data folder.")
        for key in ("mod_dir", "web_client"):
            if out[key] and not Path(out[key]).is_dir():
                raise ConfigError(f"{key} is not a directory.")
        if out["retail_enabled"] and not Path(out["directplay_bridge"]).is_file():
            raise ConfigError("Retail transport needs the DirectPlay bridge executable.")
        if out["retail_enabled"] and os.name != "nt" and not Path(out["wine"]).is_file():
            raise ConfigError("Retail transport on Linux needs a Wine executable or launcher.")
    return out

def load(path: Path) -> dict:
    return validate(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else copy.deepcopy(DEFAULT)

def save(path: Path, value: dict) -> dict:
    checked = validate(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(checked, indent=2) + "\n", encoding="utf-8")
    temp.chmod(0o600)
    temp.replace(path)
    return checked

def registry(config: dict) -> dict:
    return {
        "gameName": config["name"], "serverPassword": config["password"],
        "serverEpisodeGob": config["episode"], "serverMapJkl": config["map"],
        "maxPlayers": config["max_players"], "bIsDedicated": True,
        "maxRank": config["rank"], "tickRate": config["tick_ms"],
        "portNum": config["native_port"], "gameFlags": config["game_flags"],
        "sessionFlags": 0, "timeLimit": config["time_limit"], "scoreLimit": config["score_limit"],
        "bUseScoreLimit": bool(config["score_limit"]), "bUseTimeLimit": bool(config["time_limit"]),
        "bIsSingleLevel": False, "bIsTeams": config["teams"], "bIsCoop": False, "bIsEpisodeCoop": False,
        "enableVsync": False, "enableBloom": False, "enableSSAO": False, "fpslimit": 60,
    }

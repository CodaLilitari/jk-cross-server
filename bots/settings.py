"""Shared settings for ordinary player bots; no engine or manager imports."""
from __future__ import annotations

from pathlib import Path


PROFILE_IDS = ("boba_fett", "jan_ors", "kyle_katarn", "stormtrooper",
               "bossk", "greedo", "sariss", "yun")
BEHAVIOR_FIELDS = ("bots_sabers_only", "bots_fists_peace", "bots_force_enabled")


def check_scope(config: dict, count: int) -> None:
    if (config["game"] != "jk" or config["password"] or config["mod_dir"]
            or config["game_flags"] & ~0x1BF or config["episode"].casefold() not in ("jk1mp", "jk1ctf")
            or type(config["rank"]) is not int or not 0 <= config["rank"] <= 8):
        raise ValueError("Bots support stock JK1MP or JK1CTF, ranks 0–8, no password, no mod, and ordinary JK multiplayer flags only.")
    if config["episode"].casefold() == "jk1ctf" and not config["teams"]:
        raise ValueError("Stock JK1CTF bots require Team game to be enabled.")
    if config["episode"].casefold() == "jk1mp":
        if config["teams"] and not config["game_flags"] & 0x100:
            raise ValueError("JK1MP team bots need skin-based teams: include additional game flag 256.")
        if config["game_flags"] & 0x101 and not config["teams"]:
            raise ValueError("Enable Team game when using JK1MP team or team-skin flags with bots.")
    if not 1 <= count <= 4:
        raise ValueError("Choose between one and four bots.")
    if count + 1 >= config["max_players"]:
        raise ValueError("Allow at least the bot count plus two player slots for conservative launcher headroom; the dedicated host is added separately.")


def behavior_values(config: dict) -> dict:
    return {"sabers_only": config.get("bots_sabers_only", False),
            "fists_peace": config.get("bots_fists_peace", True),
            "force_enabled": config.get("bots_force_enabled", True)}


def write_behavior(path: Path, config: dict) -> None:
    """Publish a complete behavior revision; readers never see partial writes."""
    values = behavior_values(config)
    if any(type(value) is not bool for value in values.values()):
        raise ValueError("Bot behavior settings must be true or false.")
    text = "version=1\n" + "".join(f"{key}={int(value)}\n" for key, value in values.items())
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="ascii")
    temporary.chmod(0o600)
    temporary.replace(path)


def engine_path(config: dict) -> Path:
    return Path(config["bots_engine"]) if config.get("bots_engine") else Path(__file__).resolve().parents[1] / "bin/bots-linux-x86_64/jk-bot-client"

#!/usr/bin/env python3
"""Run isolated, ordinary native JK clients controlled by the prototype AI.

This launcher never starts or changes the server. Game archives are input files;
profiles, registry settings, logs, and lifecycle ownership belong to each run.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
from pathlib import Path
import re
import secrets
import select
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import BinaryIO

from manager import config as server_config
from .settings import behavior_values, check_scope, write_behavior

ROOT = Path(__file__).resolve().parents[1]
PROFILE_FILE = Path(__file__).with_name("profiles.json")
JOIN_TIMEOUT = 90.0
STOP_GRACE = 5.0
EVENTS = ("spawn", "kill", "death", "ambient")
JOINED = re.compile(rb"^BOT_JOINED slot=(\d+) net=(\d+)(?:\s|$)")


def load_profiles(path: Path = PROFILE_FILE) -> dict[str, dict]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(value, dict) or value.get("version") != 1
            or value.get("game") != "jk" or not isinstance(value.get("profiles"), list)
            or not value["profiles"]):
        raise ValueError("Profiles must contain version 1, game jk, and a nonempty profiles array.")
    profiles, names = {}, set()
    for row in value["profiles"]:
        if not isinstance(row, dict):
            raise ValueError("Every profile must be an object.")
        ident, name = row.get("id"), row.get("name")
        if not isinstance(ident, str) or not re.fullmatch(r"[a-z0-9_-]{1,32}", ident):
            raise ValueError("Profile id must be 1–32 lowercase ASCII letters, digits, underscores, or hyphens.")
        if not isinstance(name, str) or not re.fullmatch(r"Bot_[A-Za-z0-9_-]{1,11}", name):
            raise ValueError(f"{ident}: name must begin Bot_ and fit 15 ASCII characters without spaces.")
        if ident in profiles or name.casefold() in names:
            raise ValueError("Profile ids and case-insensitive player names must be unique.")
        for key, extension in (("model", "3do"), ("sound", "snd")):
            item = row.get(key)
            if (not isinstance(item, str) or len(item) > 31
                    or not re.fullmatch(r"[A-Za-z0-9_-]+\." + extension, item)):
                raise ValueError(f"{ident}: {key} must be a plain ASCII .{extension} basename, at most 31 characters.")
        if row.get("force_side", "light") not in ("light", "dark") or row.get("force_style", "balanced") not in ("balanced", "master"):
            raise ValueError(f"{ident}: invalid Force side or style.")
        taunts = row.get("taunts")
        if not isinstance(taunts, dict) or set(taunts) != set(EVENTS):
            raise ValueError(f"{ident}: taunts must contain exactly spawn, kill, death, and ambient.")
        for event in EVENTS:
            lines = taunts[event]
            if (not isinstance(lines, list) or not 1 <= len(lines) <= 16
                    or any(not isinstance(line, str) or not 1 <= len(line) <= 110
                           or any(not 32 <= ord(c) <= 126 for c in line) for line in lines)):
                raise ValueError(f"{ident}: {event} needs 1–16 printable ASCII lines of 1–110 characters.")
        profiles[ident] = row
        names.add(name.casefold())
    return profiles


def select_profiles(profiles: dict[str, dict], selection: str) -> list[dict]:
    selected = selection.split(",")
    if not 1 <= len(selected) <= 4 or any(not x for x in selected):
        raise ValueError("Choose 1–4 comma-separated profile ids.")
    if len(set(selected)) != len(selected):
        raise ValueError("Each profile may be selected only once in a run.")
    unknown = set(selected) - profiles.keys()
    if unknown:
        raise ValueError("Unknown profiles: " + ", ".join(sorted(unknown)))
    return [profiles[x] for x in selected]


def endpoint(value: str) -> str:
    if not isinstance(value, str) or value.count(":") != 1:
        raise ValueError("--connect must be HOST:PORT (hostname or IPv4; IPv6 is not supported here).")
    host, port = value.split(":")
    if (not 1 <= len(host) <= 253 or any(not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
                                      for label in host.split("."))
            or not port.isascii() or not port.isdecimal() or not 1 <= int(port) <= 65535):
        raise ValueError("--connect needs a valid hostname/IPv4 and a port from 1 to 65535.")
    return f"{host}:{int(port)}"


def child_casefold(parent: Path, name: str) -> Path:
    found = [p for p in parent.iterdir() if p.name.casefold() == name.casefold()]
    if len(found) != 1 or not found[0].is_dir():
        raise ValueError(f"Expected one {name} directory in {parent}.")
    return found[0]


def ensure_separate(source: Path, destination: Path) -> None:
    source, destination = source.resolve(), destination.resolve()
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError("Bot runtime and original game data must be separate, non-overlapping directories.")


def stage_tree(source: Path, destination: Path, ancestors: frozenset[Path] = frozenset()) -> None:
    """Lowercase game input names; never import human profiles or settings."""
    resolved = source.resolve()
    if resolved in ancestors:
        raise ValueError(f"Directory symlink cycle in game data: {source}")
    ancestors = ancestors | {resolved}
    destination.mkdir(mode=0o700)
    used = set()
    for child in source.iterdir():
        name = child.name.casefold()
        if name == "video":
            continue
        if name == "authority" or (name.startswith("jk-admin-key-") and name.endswith(".cog")):
            continue
        if name in used:
            raise ValueError(f"Ambiguous filename case in {source}: {child.name}")
        used.add(name)
        output = destination / name
        if child.is_dir():
            stage_tree(child, output, ancestors)
        elif child.is_file():
            try:
                os.link(child.resolve(), output)
            except OSError:
                shutil.copy2(child, output)
        else:
            raise ValueError(f"Unsupported game input file: {child}")


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def prepare_bot(data: Path, directory: Path, profile: dict) -> None:
    ensure_separate(data, directory)
    directory.mkdir(mode=0o700)
    for name in ("resource", "episode"):
        stage_tree(child_casefold(data, name), directory / name)
    for name in ("player", "xdg", "config"):
        (directory / name).mkdir(mode=0o700)
    write_json(directory / "registry.json", {
        "Window_isFullscreen": False, "Window_isHiDpi": False, "enableVsync": False,
        "enableBloom": False, "enableSSAO": False, "fpslimit": 30,
    })
    write_json(directory / "profile.json", profile)
    with (directory / "persona.tsv").open("w", encoding="ascii", newline="\n") as output:
        for event in EVENTS:
            for line in profile["taunts"][event]:
                output.write(f"{event}\t{line}\n")


def bot_environment(engine: Path, directory: Path, run_directory: Path, index: int,
                    display: str, taunts: bool, *, behavior_file: Path | None = None,
                    team: int = 0, force_side: str = "light", force_style: str = "balanced") -> dict[str, str]:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("OPENJKDF2_GATEWAY_", "JK_GATEWAY_", "JK_BOT_"))
           and k != "OPENJKDF2_REQUIRE_DP_POOL"}
    env.update(OPENJKDF2_ROOT=str(directory), XDG_RUNTIME_DIR=str(directory / "xdg"),
               XDG_CONFIG_HOME=str(directory / "config"), DISPLAY=display,
               ALSOFT_DRIVERS="null", SDL_AUDIODRIVER="dummy", LIBGL_ALWAYS_SOFTWARE="1",
               JK_BOT_PERSONA_FILE=str(directory / "persona.tsv"),
               JK_BOT_CHAT_LOCK=str(run_directory / "chat.lock"),
               JK_BOT_CHAT_PHASE=str(15 + 40 * index), JK_BOT_TAUNTS="1" if taunts else "0",
               JK_BOT_TEAM=str(team), JK_BOT_FORCE_SIDE=force_side, JK_BOT_FORCE_STYLE=force_style)
    if behavior_file is not None:
        env["JK_BOT_BEHAVIOR_FILE"] = str(behavior_file)
    env["LD_LIBRARY_PATH"] = str(engine.parent) + (os.pathsep + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")
    return env


@dataclass
class Child:
    label: str
    process: subprocess.Popen
    log: BinaryIO
    record: dict | None = None
    started: float = 0.0
    offset: int = 0
    pending: bytes = b""


def group_alive(pid: int) -> bool:
    try:
        os.killpg(pid, 0)
        return True
    except ProcessLookupError:
        return False


def stop_group(process: subprocess.Popen, grace: float = STOP_GRACE) -> None:
    # The leader can have exited while a descendant still owns the group.
    # Reaping the leader is not sufficient evidence that the run is stopped.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        process.poll()
        if not group_alive(process.pid):
            break
        time.sleep(0.03)
    if group_alive(process.pid):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"Owned process {process.pid} did not exit after SIGKILL.") from error


def start_display(run_directory: Path, children: list[Child], *, managed: bool = False) -> tuple[str, int]:
    executable = shutil.which("Xvfb")
    if not executable:
        raise ValueError("Install Xvfb or set DISPLAY: the bot client needs X at bootstrap.")
    read_fd, write_fd = os.pipe()
    log = (run_directory / "xvfb.log").open("wb")
    try:
        process = subprocess.Popen([executable, "-displayfd", str(write_fd), "-screen", "0", "640x480x24", "-nolisten", "tcp"],
                                   stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                   pass_fds=(write_fd,), start_new_session=not managed)
        children.append(Child("Xvfb", process, log))
    except BaseException:
        log.close()
        os.close(read_fd)
        raise
    finally:
        os.close(write_fd)
    try:
        data = b""
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and len(data) < 64:
            if process.poll() is not None:
                raise RuntimeError("Xvfb exited during startup; see xvfb.log.")
            if select.select([read_fd], [], [], 0.1)[0]:
                chunk = os.read(read_fd, 64)
                if not chunk:
                    raise RuntimeError("Xvfb closed its readiness pipe before choosing a display.")
                data += chunk
                if b"\n" in data:
                    number = data.split(b"\n", 1)[0]
                    if not number.isdigit() or not 0 <= int(number) <= 65535:
                        raise RuntimeError("Xvfb returned an invalid display number.")
                    # Xvfb may write another readiness notification. Keep this
                    # reader alive until after Xvfb is terminated, avoiding EPIPE.
                    return ":" + number.decode("ascii"), read_fd
        raise RuntimeError("Timed out waiting for an Xvfb display number.")
    except BaseException:
        os.close(read_fd)
        raise


def inspect_log(child: Child) -> bool:
    """Read bounded incremental output and record a normal joined player ID."""
    if child.record is None:
        return False
    with Path(child.log.name).open("rb") as source:
        source.seek(child.offset)
        chunk = source.read(1024 * 1024)
        child.offset += len(chunk)
    changed = False
    lines = (child.pending + chunk).split(b"\n")
    child.pending = lines.pop()[-8192:]
    for line in lines:
        if line.startswith(b"BOT_JOIN_REJECTED"):
            message = line[:500].decode("utf-8", "replace")
            child.record["error"] = message
            raise RuntimeError(f"{child.label}: {message}")
        joined = JOINED.match(line)
        if joined and not child.record["joined"]:
            slot, network_id = map(int, joined.groups())
            if not 0 <= slot < 32 or not 0 < network_id <= 0xFFFFFFFF:
                raise RuntimeError(f"{child.label}: invalid joined slot/network ID.")
            child.record.update(joined=True, slot=slot, network_id=network_id, joined_at=utc_now())
            print(f"{child.label}: joined slot {slot}, network ID {network_id}", flush=True)
            changed = True
    return changed


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def launch(config: dict, profiles: list[dict], *, engine: Path, connect: str,
           runtime: Path, seconds: float, taunts: bool, behavior_file: Path | None = None,
           status_file: Path | None = None, managed: bool = False) -> tuple[int, Path]:
    check_scope(config, len(profiles))
    if sys.platform != "linux":
        raise ValueError("The packaged bot prototype currently supports Linux only.")
    if managed and os.getpgrp() != os.getpid():
        raise ValueError("Managed bot runner must own its process group.")
    if not engine.is_file() or not os.access(engine, os.X_OK):
        raise ValueError(f"Bot executable is missing or not executable: {engine}")
    if not math.isfinite(seconds) or not 0 <= seconds <= 86400:
        raise ValueError("--seconds must be between 0 and 86400; 0 runs until interrupted.")
    data = Path(config["game_data"]).resolve()
    if not config["game_data"] or not data.is_dir():
        raise ValueError("server-config must point game_data to your installed JK data directory.")
    runtime, engine = runtime.resolve(), engine.resolve()
    ensure_separate(data, runtime)
    connect = endpoint(connect)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_directory = runtime / (stamp + "-" + secrets.token_hex(4))
    run_directory.mkdir(parents=True, mode=0o700)
    if behavior_file is None:
        behavior_file = run_directory / "behavior.cfg"
        write_behavior(behavior_file, config)
    else:
        behavior_file = behavior_file.resolve()
        if not behavior_file.is_file():
            raise ValueError("The supplied live bot behavior file does not exist.")
    if status_file is not None:
        status_file = status_file.resolve()
    session = {"version": 1, "started_at": utc_now(), "server": connect,
               "engine": str(engine), "game": "jk", "result": "starting", "bots": [],
               "behavior_file": str(behavior_file), "initial_behavior": behavior_values(config),
               "episode": config["episode"], "map": config["map"], "rank": config["rank"],
               "teams": config["teams"], "managed": managed,
               "seat_policy": "Static count check only; no live human reservation or cross-run coordination."}
    receipt = run_directory / "session.json"
    def publish():
        write_json(receipt, session)
        if status_file is not None:
            write_json(status_file, session)
    publish()
    print(f"Bot run: {run_directory}", flush=True)
    children: list[Child] = []
    display_read_fd = None
    stopped = []
    previous_signals = {}
    errors = []
    exit_code = 1
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous_signals[sig] = signal.signal(sig, lambda signum, frame: stopped.append(signum))
        display = os.environ.get("DISPLAY", "")
        if not display:
            display, display_read_fd = start_display(run_directory, children, managed=managed)
        for index, profile in enumerate(profiles):
            directory = run_directory / profile["id"]
            prepare_bot(data, directory, profile)
            team = 1 + index % 2 if config["teams"] else 0
            force_side = profile.get("force_side", "light")
            force_style = profile.get("force_style", "balanced")
            record = {"id": profile["id"], "name": profile["name"], "model": profile["model"],
                      "sound": profile["sound"], "directory": str(directory), "joined": False,
                      "requested_team": team, "force_side": force_side, "force_style": force_style}
            session["bots"].append(record)
            log = (directory / "client.log").open("wb")
            command = [str(engine), "-headless", "-botConnect", connect,
                       "-botName", profile["name"], "-botSkin", profile["model"], "-botSound", profile["sound"]]
            try:
                process = subprocess.Popen(command, cwd=directory, stdin=subprocess.DEVNULL,
                                           stdout=log, stderr=subprocess.STDOUT, start_new_session=not managed,
                                           env=bot_environment(engine, directory, run_directory, index, display, taunts,
                                                               behavior_file=behavior_file, team=team, force_side=force_side,
                                                               force_style=force_style))
            except BaseException:
                log.close()
                raise
            record["pid"] = process.pid
            children.append(Child(profile["name"], process, log, record, time.monotonic()))
            publish()
        started = time.monotonic()
        session["result"] = "running"
        publish()
        while not stopped:
            changed = False
            for child in children:
                changed |= inspect_log(child)
                returncode = child.process.poll()
                if returncode is not None:
                    if child.record is not None:
                        child.record["returncode"] = returncode
                    raise RuntimeError(f"{child.label} exited unexpectedly with status {returncode}; see its log.")
                if child.record is not None and not child.record["joined"] and time.monotonic() - child.started >= JOIN_TIMEOUT:
                    child.record["error"] = "join watchdog expired"
                    raise RuntimeError(f"{child.label} did not join within {JOIN_TIMEOUT:g} seconds.")
            if changed:
                publish()
            if seconds and time.monotonic() - started >= seconds:
                if not all(row["joined"] for row in session["bots"]):
                    raise RuntimeError("Requested duration ended before all bots joined; increase --seconds or check logs.")
                session["result"] = "duration_complete"
                break
            time.sleep(0.05)
        if stopped:
            session.update(result="stopped", signal=stopped[0])
        exit_code = 0
    except (OSError, ValueError, RuntimeError) as error:
        errors.append(str(error))
        session["result"] = "failed"
    finally:
        # Continue cleanup even when one child/descriptor fails. Never leave
        # another bot alive merely because a sibling was already gone.
        for child in reversed(children):
            try:
                if managed:
                    # The manager owns the common process group. The runner
                    # stops its direct children; manager teardown also kills
                    # the group, even if this runner exits unexpectedly.
                    if child.process.poll() is None:
                        child.process.terminate()
                        try:
                            child.process.wait(timeout=STOP_GRACE)
                        except subprocess.TimeoutExpired:
                            child.process.kill()
                            child.process.wait(timeout=2)
                else:
                    stop_group(child.process)
            except Exception as error:
                errors.append(f"Cleanup {child.label}: {error}")
            if child.record is not None:
                child.record["returncode"] = child.process.poll()
            try:
                child.log.close()
            except Exception as error:
                errors.append(f"Close {child.label} log: {error}")
        if display_read_fd is not None:
            try:
                os.close(display_read_fd)
            except OSError as error:
                errors.append(f"Close display readiness pipe: {error}")
        for sig, handler in previous_signals.items():
            signal.signal(sig, handler)
        if errors:
            exit_code = 1
            session.update(result="failed", errors=errors)
        session["finished_at"] = utc_now()
        publish()
    for error in errors:
        print("Bot run failed: " + error, file=sys.stderr, flush=True)
    return exit_code, run_directory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list-profiles", action="store_true")
    parser.add_argument("--server-config", type=Path)
    parser.add_argument("--profiles", help="Comma-separated stock profile ids; defaults to bots_profiles in the server config")
    parser.add_argument("--engine", type=Path, default=ROOT / "bin/bots-linux-x86_64/jk-bot-client")
    parser.add_argument("--connect", help="HOST:PORT, default 127.0.0.1:<native_port> from server config")
    parser.add_argument("--runtime", type=Path, default=ROOT / "runtime/bots")
    parser.add_argument("--seconds", type=float, default=0, help="Stop after this many seconds; 0 runs until interrupted")
    parser.add_argument("--no-taunts", action="store_true")
    parser.add_argument("--behavior-file", type=Path, help="Read live behavior settings from this existing file")
    parser.add_argument("--status-file", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--managed", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        profiles = load_profiles()
        if args.list_profiles:
            for ident, row in profiles.items():
                print(f"{ident:15} {row['name']:15} {row['model']:12} {row['sound']}")
            return 0
        if args.server_config is None or not args.server_config.is_file():
            raise ValueError("Supply an existing --server-config JSON file for your running server.")
        config = server_config.validate(json.loads(args.server_config.read_text(encoding="utf-8")))
        selected = select_profiles(profiles, args.profiles or ",".join(config["bots_profiles"]))
        code, _ = launch(config, selected, engine=args.engine,
                         connect=args.connect or f"127.0.0.1:{config['native_port']}",
                         runtime=args.runtime, seconds=args.seconds,
                         taunts=config["bots_taunts"] and not args.no_taunts,
                         behavior_file=args.behavior_file, status_file=args.status_file, managed=args.managed)
        return code
    except (OSError, ValueError, RuntimeError) as error:
        print("Bot launcher: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

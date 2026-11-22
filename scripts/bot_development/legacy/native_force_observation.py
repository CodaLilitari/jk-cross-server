#!/usr/bin/env python3
"""Observe two native JK clients in a bounded Linux Force test.

The caller supplies the repository, owned game installation and a fresh output
directory. This is a development observation, not a competitive-skill verdict.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time

BOT = "bin/bots-linux-x86_64/jk-bot-client"
SERVER = "bin/linux-x86_64/openjkdf2"
PATCH = "native/bot-client.patch"
GNS = "libGameNetworkingSockets.so"
STOCK_MP = "27a4b3642e0965753232f35b1e8e846c91df1eca1da77398b5efda66ca369a2e"
STOCK_MAPS = ("m2.jkl", "m4.jkl", "m5.jkl", "m10.jkl", "m_boss15.jkl", "m_boss17.jkl")
EXPECTED = {"light": {21, 22, 23, 24, 25, 28}, "dark": {21, 22, 23, 24, 31, 33}}
FLAGS = {"SDL_VIDEODRIVER": "offscreen", "SDL_VIDEO_DRIVER": "offscreen",
         "EGL_PLATFORM": "surfaceless", "LIBGL_ALWAYS_SOFTWARE": "1",
         "ALSOFT_DRIVERS": "null", "SDL_AUDIODRIVER": "dummy", "LP_NUM_THREADS": "2"}
START = time.monotonic()
STOP = []
CHILDREN = {}
READERS = {}
LABELS = {"dark": "boba_fett", "light": "jan_ors"}


class Failure(Exception):
    """A public error string assembled only from non-sensitive fields."""


def check():
    if STOP:
        raise Failure("interrupted_signal_%d" % STOP[0])
    if time.monotonic() - START >= 172:
        raise Failure("overall_deadline")


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as inp:
        while block := inp.read(1024 * 1024):
            check()
            value.update(block)
    return value.hexdigest()


def dump(value):
    return json.dumps(value, separators=(",", ":"), allow_nan=False)


def choose(directory, name):
    matches = [p for p in directory.iterdir() if p.name.casefold() == name]
    if len(matches) != 1:
        raise Failure("missing_or_ambiguous_" + name)
    return matches[0]


def stage(source, target):
    # Private copies only. prepare_bot can then safely hard-link *these* inputs.
    for name in ("resource", "episode"):
        (target / name).mkdir(parents=True)
    resource = choose(source, "resource")
    variants = [n for n in ("res1hi.gob", "res1.gob", "res1low.gob")
                if any(p.name.casefold() == n for p in resource.iterdir())]
    if not variants:
        raise Failure("missing_stock_resource_gob")
    files = [("episode", choose(source, "episode"), "jk1mp.gob"),
             ("resource", resource, "res2.gob"), ("resource", resource, variants[0]),
             ("resource", resource, "jk_.cd")]
    for section, parent, name in files:
        check()
        with choose(parent, name).open("rb") as src, (target / section / name).open("xb") as dst:
            while chunk := src.read(1024 * 1024):
                check()
                dst.write(chunk)


def boot(label, command, directory, env, output):
    path = output / (label + ".log")
    with path.open("xb") as log:
        CHILDREN[label] = subprocess.Popen(command, cwd=directory, stdin=subprocess.DEVNULL,
                                            stdout=log, stderr=subprocess.STDOUT, env=env,
                                            start_new_session=True)
    READERS[label] = path.open("rb")


def shutdown():
    # Signal all private sessions together, including descendants of exited leaders.
    def send(sig):
        for child in CHILDREN.values():
            try:
                os.killpg(child.pid, sig)
            except ProcessLookupError:
                pass
    send(signal.SIGTERM)
    end = time.monotonic() + 1
    while time.monotonic() < end and any(p.poll() is None for p in CHILDREN.values()):
        time.sleep(.03)
    send(signal.SIGKILL)
    for child in CHILDREN.values():
        child.wait(timeout=1)
    for reader in READERS.values():
        reader.close()


def owns_udp(pid, port):
    sockets = set()
    for path in Path(f"/proc/{pid}/fd").iterdir():
        try:
            target = os.readlink(path)
        except FileNotFoundError:
            continue
        if target.startswith("socket:["):
            sockets.add(target[8:-1])
    for table in ("udp", "udp6"):
        path = Path(f"/proc/{pid}/net/{table}")
        if path.exists():
            for line in path.read_text().splitlines()[1:]:
                fields = line.split()
                if int(fields[1].split(":")[1], 16) == port and fields[9] in sockets:
                    return True
    return False


def private_env(directory, engine):
    # Do not pass through gateway, proxy, desktop, credential or gameplay settings.
    env = dict(FLAGS, PATH=os.defpath, LANG="C", HOME=str(directory),
               OPENJKDF2_ROOT=str(directory), XDG_RUNTIME_DIR=str(directory / "xdg"),
               XDG_CONFIG_HOME=str(directory / "config"), XDG_DATA_HOME=str(directory / "data"),
               XDG_CACHE_HOME=str(directory / "cache"), TMPDIR=str(directory / "tmp"),
               LD_LIBRARY_PATH=str(engine.parent))
    for child in ("xdg", "config", "tmp", "data", "cache"):
        (directory / child).mkdir(exist_ok=True)
    return env


def check_liveness():
    check()
    for label, process in CHILDREN.items():
        code = process.poll()
        if code is not None:
            raise Failure(f"{label}_exited_{code}")


def new_stats(side):
    return {"side": side, "joined": None, "loadout": None, "behavior": None,
            "samples": 0, "matching_star_samples": 0, "first_stars": None,
            "input_counts": Counter(), "active_counts": Counter(), "immobile_samples": 0,
            "ranges": {}, "mana_decreases": 0, "health_decreases": 0,
            "target_slots": [], "examples": {}, "previous": {}}


def observe(side, name, line, row, trace):
    # Save only typed numeric evidence. Native logs stay private, outside the receipt.
    kind, _, tail = line.partition(" ")
    fields = dict(part.split("=", 1) for part in tail.split() if "=" in part)
    if kind == "BOT_JOIN_REJECTED":
        raise Failure(side + "_join_rejected")
    if kind == "BOT_LOADOUT":
        if not re.fullmatch(r"rank=8 side=" + side + " style=competitive spent=24 remaining=0", tail):
            raise Failure(side + "_incorrect_saved_plan")
        row["loadout"] = {"rank": 8, "style": "competitive", "spent": 24, "remaining": 0}
    if kind == "BOT_JOINED":
        slot, net = int(fields["slot"]), int(fields["net"])
        if not 0 <= slot < 32 or not 0 < net <= 0xffffffff:
            raise Failure(side + "_invalid_join_identity")
        row["joined"] = {"slot": slot, "net": net}
    if fields.get("name") != name:
        return
    if kind == "BOT_BEHAVIOR":
        row["behavior"] = {k: int(fields[k]) for k in ("sabers_only", "fists_peace", "force_enabled")}
    if not row["joined"]:
        return
    if kind == "BOT_STATUS":
        slot = int(fields["target"])
        if slot >= 0 and slot not in row["target_slots"]:
            row["target_slots"].append(slot)
    if kind == "BOT_FORCE_INPUT":
        bin_id = int(fields["bin"])
        row["input_counts"][bin_id] += 1
        event = {k: float(fields[k]) for k in ("mana", "level", "hold")}
        trace.write(dump(dict(event, side=side, event="input", bin=bin_id,
                              read_elapsed_s=round(time.monotonic()-START,3)))+"\n")
    if kind != "BOT_FORCE_STATE":
        return
    sample = {k: float(fields[k]) for k in ("t", "health", "shields", "mana")}
    stars = [float(s) for s in fields["stars"].split(",")]
    if len(stars) != 14 or not all(math.isfinite(v) for v in [*stars, *sample.values()]):
        raise Failure(side + "_invalid_sample")
    sample.update({k: int(fields[k]) for k in ("thing", "guid", "blind", "immobile")})
    mask = int(fields["active"], 16)
    trace.write(dump(dict(sample, side=side, event="state", stars=stars, active=mask,
                          read_elapsed_s=round(time.monotonic()-START,3)))+"\n")
    row["samples"] += 1
    row["first_stars"] = row["first_stars"] or stars
    row["matching_star_samples"] += stars == [4 if b in EXPECTED[side] else 0 for b in range(21,35)]
    row["immobile_samples"] += sample["immobile"] == 1
    prev = row["previous"]
    example = {k:sample[k] for k in ("t","health","shields","mana","immobile")}
    example["active"] = mask
    for label, condition in (("first_active",mask), ("first_immobile",sample["immobile"]),
                             ("first_mana_decrease",prev and sample["mana"] < prev["mana"]),
                             ("first_health_decrease",prev and sample["health"] < prev["health"])):
        if condition and label not in row["examples"]:
            row["examples"][label] = example
    for b in range(21,35):
        if mask & (1 << (b-21)):
            row["active_counts"][b] += 1
    for key in ("health", "shields", "mana", "t"):
        value = sample[key]
        lo, hi = row["ranges"].get(key,(value,value))
        row["ranges"][key] = [min(lo,value),max(hi,value)]
    prev = row["previous"]
    if prev and (sample["thing"],sample["guid"]) == (prev["thing"],prev["guid"]):
        for key in ("mana","health"):
            row[key+"_decreases"] += sample[key] < prev[key]
    row["previous"] = sample


def run(args, receipt, tmp):
    repo, source, output = args.repo.resolve(), args.data.resolve(), args.output.resolve()
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(repo))
    from bots.run import prepare_bot, load_profiles, bot_environment
    from bots.settings import write_behavior
    from manager import config
    from manager.content import archive_index

    def git(*words):
        return subprocess.check_output(["git","-C",str(repo),*words],stderr=subprocess.DEVNULL,
                                       timeout=5,text=True).strip()
    receipt.update(commit=git("rev-parse","HEAD"), branch=git("rev-parse","--abbrev-ref","HEAD"),
                   source_tree_clean=not bool(git("status","--porcelain","--untracked-files=no")),
                   platform={"python":platform.python_version(),"glibc":platform.libc_ver()[1]},
                   render_environment=FLAGS, bot_options={"taunts":False,"team":0,
                       "force_style":"competitive","trace_force":True})
    bot, server = repo / BOT, repo / SERVER
    packaged = json.loads((repo/"native/BOT_BUILD.json").read_text())
    files = [BOT,str(Path(BOT).parent/GNS),PATCH,SERVER,str(Path(SERVER).parent/GNS)]
    hashes = receipt["sha256"] = {name:digest(repo/name) for name in files}
    if any(hashes[name] != packaged["files"][name]["sha256"] for name in files[:3]):
        raise Failure("packaged_bot_binary_patch_or_gns_hash_mismatch")
    server_dir = tmp/"server"
    stage(source,server_dir)
    gob = server_dir/"episode/jk1mp.gob"
    hashes["jk1mp.gob"] = digest(gob)
    for p in (server_dir/"resource").glob("*.gob"):
        hashes[p.name] = digest(p)
    if hashes["jk1mp.gob"] != STOCK_MP:
        raise Failure("stock_episode_hash_mismatch")
    audit = json.loads((repo / "qa/bots-stock-map-audit.json").read_text())
    episode = next(item for item in audit["episodes"] if item["episode"] == "jk1mp")
    expected_hash = next(item["sha256"] for item in episode["maps"] if item["map"] == args.map)
    map_key = "jkl/" + args.map
    entry = next(item for item in archive_index(gob) if item["name"].casefold() == map_key)
    with gob.open("rb") as inp:
        inp.seek(entry["offset"])
        hashes[map_key] = hashlib.sha256(inp.read(entry["size"])).hexdigest()
    if hashes[map_key] != expected_hash:
        raise Failure("stock_map_hash_mismatch")
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1",0))
        port = sock.getsockname()[1]
    cfg = dict(config.DEFAULT,map=args.map,rank=8,native_port=port,bots_fists_peace=False,bots_force_enabled=True,
               bots_sabers_only=False,bots_taunts=False,web_enabled=False,spectator_rendering=False,
               name="Native Force QA",max_players=4)
    registry = config.registry(cfg)
    receipt["server_registry"] = registry.copy()
    receipt["server_registry"].pop("serverPassword")
    receipt["server_argv"] = ["-headless","-dedicatedServer","-episode","JK1MP","-map",args.map]
    (server_dir/"registry.json").write_text(dump(registry))
    (server_dir/"player").mkdir()
    write_behavior(tmp/"behavior.cfg",cfg)
    profiles = load_profiles()
    receipt["bots"] = bots = {s:new_stats(s) for s in LABELS}
    for side, pid in LABELS.items():
        if (profiles[pid]["force_side"],profiles[pid]["force_style"]) != (side,"competitive"):
            raise Failure(side+"_incorrect_profile")
        prepare_bot(server_dir,tmp/side,profiles[pid])
    boot("server",[str(server),*receipt["server_argv"]],server_dir,private_env(server_dir,server),output)
    before = time.monotonic()
    while not owns_udp(CHILDREN["server"].pid,port):
        check_liveness()
        if time.monotonic()-before > 25:
            raise Failure("dedicated_server_udp_readiness_timeout")
        time.sleep(.1)
    receipt["dedicated_server_owned_udp_port"] = True
    partial = {s:b"" for s in LABELS}

    def collect(trace):
        for side, pid in LABELS.items():
            if side not in READERS:
                continue
            raw = partial[side] + READERS[side].read(1024*1024)
            lines = raw.split(b"\n")
            partial[side] = lines.pop()[-16384:]
            for line in lines:
                text = line.decode("ascii","replace").strip()
                marker = text.find("BOT_")
                if marker >= 0:
                    observe(side,profiles[pid]["name"],text[marker:],bots[side],trace)

    with (output/"force-trace.jsonl").open("x",encoding="ascii",buffering=1) as trace:
        for index, (side, pid) in enumerate(LABELS.items()):
            p = profiles[pid]
            directory = tmp/side
            env = private_env(directory,bot)
            standard = bot_environment(bot,directory,tmp,index,"",False,behavior_file=tmp/"behavior.cfg",
                                       force_side=side,force_style="competitive")
            env.update({k:v for k,v in standard.items() if k.startswith("JK_BOT_")})
            env["JK_BOT_TRACE_FORCE"] = "1"
            args_bot = ["-headless","-botConnect",f"127.0.0.1:{port}","-botName",p["name"],
                        "-botSkin",p["model"],"-botSound",p["sound"]]
            bots[side]["argv"] = args_bot
            boot(side,[str(bot),*args_bot],directory,env,output)
            # Give each real client its own discovery / welcome cycle before the next.
            wait_start = time.monotonic()
            while not bots[side]["joined"]:
                collect(trace)
                check_liveness()
                if time.monotonic()-wait_start>40:
                    raise Failure(side+"_join_timeout")
                time.sleep(.10)
        start_match = time.monotonic()
        while True:
            collect(trace)
            check_liveness()
            if time.monotonic()-start_match >= args.duration:
                break
            time.sleep(.15)
    receipt["both_joined_observation_wall_seconds"] = round(time.monotonic()-start_match,2)
    for side, row in bots.items():
        if not row["joined"] or not row["loadout"] or row["matching_star_samples"] == 0:
            raise Failure(side+"_join_or_live_loadout_unverified")
        if row["behavior"] != {"sabers_only":0,"fists_peace":0,"force_enabled":1}:
            raise Failure(side+"_behavior_unverified")
    if any(bots["light"]["joined"][k] == bots["dark"]["joined"][k] for k in ("slot","net")):
        raise Failure("duplicate_live_identity")
    receipt["effects"] = {"any_active_bin_sample":any(r["active_counts"] for r in bots.values()),
                          "any_mana_decrease":any(r["mana_decreases"] for r in bots.values()),
                          "any_immobile_sample":any(r["immobile_samples"] for r in bots.values()),
                          "any_health_decrease":any(r["health_decreases"] for r in bots.values()),
                          "target_effect_caster_attribution":"unverified"}
    receipt["status"] = "live_join_and_loadout_verified"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("repo","data","output"):
        parser.add_argument("--"+key,type=Path,required=True)
    parser.add_argument("--map", choices=STOCK_MAPS, default="m2.jkl")
    parser.add_argument("--duration",type=int,default=75,choices=range(1,121),metavar="1..120")
    args = parser.parse_args()
    os.umask(0o077)
    for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):
        signal.signal(sig,lambda num,frame:STOP.append(num))
    receipt = {"version":1,"requested_map":args.map,"requested_match_seconds":args.duration,"status":"failed"}
    made_output = False
    code = 1
    try:
        out = args.output.resolve()
        for inp in (args.data.resolve(),args.repo.resolve()):
            if inp == out or inp in out.parents or out in inp.parents:
                raise Failure("output_overlaps_inputs")
        out.mkdir(mode=0o700)
        made_output = True
        with tempfile.TemporaryDirectory(prefix="jk-force-",dir="/tmp") as temp:
            try:
                run(args,receipt,Path(temp))
            finally:
                shutdown()
        code = 0
    except Failure as e:
        receipt["error"] = str(e)
    except Exception as e:
        # OSError strings often contain private installation paths.
        receipt["error"] = type(e).__name__
        if isinstance(e,OSError):
            receipt["errno"] = e.errno
        if isinstance(e,subprocess.CalledProcessError):
            receipt["exit_code"] = e.returncode
    if STOP:
        code = 1
        receipt["error"] = "interrupted_signal_%d" % STOP[0]
    if code:
        receipt["status"] = "failed"
    for row in receipt.get("bots",{}).values():
        row.pop("previous",None)
    receipt["elapsed_wall_seconds"] = round(time.monotonic()-START,2)
    if made_output:
        with (args.output/"receipt.json").open("x",encoding="ascii") as f:
            f.write(dump(receipt)+"\n")
    print(dump(receipt),flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())

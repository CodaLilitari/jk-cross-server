"""Stage private Windows JK inputs into WSL for bounded native Force observation."""
import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile
import tempfile
import threading
import time


TIME_LIMIT = 300

PREFLIGHT = r'''
import os, pathlib, re, subprocess, sys, json
repo = pathlib.Path(CONFIG["repo"]).resolve()
bins = ("bin/linux-x86_64/openjkdf2","bin/bots-linux-x86_64/jk-bot-client")
def check():
    if not repo.is_dir():
        return {"error":"clone_absent"}
    output = pathlib.Path(CONFIG["output"]).resolve()
    if output == repo or repo in output.parents or output in repo.parents:
        return {"error":"output_overlaps_repository"}
    if os.path.lexists(output):
        return {"error":"output_already_exists"}
    if not output.parent.is_dir():
        return {"error":"output_parent_absent"}
    missing = set()
    failed = False
    for rel in bins:
        binary = repo / rel
        for target in (binary,binary.parent/"libGameNetworkingSockets.so"):
            if not target.is_file() or target == binary and not os.access(target,os.X_OK):
                return {"error":"packaged_file_absent_or_not_executable","file":target.name}
            result = subprocess.run(["/usr/bin/ldd",str(target)],timeout=15,check=False,
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,
                env={"PATH":os.defpath,"LC_ALL":"C","LD_LIBRARY_PATH":str(target.parent)})
            for line in result.stdout.splitlines():
                match = re.search(r"^\s*([\w+.\-]+)\s*=>\s*not found\b",line)
                if match:
                    missing.add(match[1])
                elif "not found" in line:
                    match = re.search(r"(lib[\w+.\-]+\.so(?:\.[\d.]+)?):\s+version",line)
                    if match:
                        missing.add(match[1])
                    else:
                        failed = True
            failed |= result.returncode != 0
    if missing:
        return {"error":"native_runtime_unavailable","libraries":sorted(missing)}
    if failed:
        return {"error":"ldd_failed"}
    return {"bridge_preflight":"ready"}
try:
    report = check()
except Exception as e:
    report = {"error":"preflight_"+type(e).__name__}
print(json.dumps(report,separators=(",",":")),flush=True)
sys.exit(int("error" in report))
'''

RECEIVER = r'''
import fcntl, hashlib, io, json, os, pathlib, signal, socket, struct, subprocess, sys, tarfile, tempfile, time
from pathlib import Path

FILES = {"res1hi.gob":("data/Resource/res1hi.gob",128*1024**2),
         "res2.gob":("data/Resource/res2.gob",128*1024**2),
         "jk_.cd":("data/Resource/jk_.cd",1024**2),
         "jk1mp.gob":("data/Episode/jk1mp.gob",16*1024**2),
         "qualification.py":("qualification.py",128*1024)}
OUT = Path(CONFIG["output"]).resolve()
REPO = Path(CONFIG["repo"]).resolve()

class Stop(Exception):
    pass

def interrupted(sig,frame):
    raise Stop("receiver_timeout" if sig==signal.SIGALRM else "receiver_interrupted")

LOOPBACK = """
import fcntl, os, socket, struct, sys
with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as control:
    request = struct.pack("16sH22x",b"lo",0)
    flags = struct.unpack_from("H",fcntl.ioctl(control,0x8913,request),16)[0]
    fcntl.ioctl(control,0x8914,struct.pack("16sH22x",b"lo",flags|1))
if {name for _,name in socket.if_nameindex()} != {"lo"}:
    raise RuntimeError("private_network_namespace_required")
os.execv(sys.executable,[sys.executable,"-B",*sys.argv[1:]])
"""

def receive(tmp):
    seen = set()
    with tarfile.open(fileobj=sys.stdin.buffer,mode="r|",bufsize=256*1024) as archive:
        for member in archive:
            if member.name not in FILES or member.name in seen:
                raise Stop("unexpected_or_duplicate_member")
            rel, limit = FILES[member.name]
            if member.type != tarfile.REGTYPE or not 1 <= member.size <= limit:
                raise Stop("invalid_member_type_or_size")
            seen.add(member.name)
            dest = tmp/rel
            dest.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            with archive.extractfile(member) as src, dest.open("xb") as dst:
                remaining = member.size
                while remaining:
                    block = src.read(min(remaining,1024*1024))
                    if not block:
                        raise Stop("truncated_member")
                    dst.write(block)
                    remaining -= len(block)
    if seen != set(FILES):
        raise Stop("incomplete_file_set")
    if hashlib.sha256((tmp/"qualification.py").read_bytes()).hexdigest() != CONFIG["harness_sha256"]:
        raise Stop("harness_sha256_mismatch")

def qualify(tmp):
    script = tmp/"qualification.py"
    cmd = ["/usr/bin/unshare","-Urn",sys.executable,"-I","-c",LOOPBACK,str(script),
           "--repo",str(REPO),"--data",str(tmp/"data"),"--output",str(OUT),"--duration",str(CONFIG["duration"]),"--map",CONFIG["map"]]
    child = None
    with (tmp/"private-stdout").open("x+b") as output, (tmp/"private-stderr").open("xb") as err:
        try:
            child = subprocess.Popen(cmd,cwd=tmp,stdin=subprocess.DEVNULL,stdout=output,stderr=err,
                                     start_new_session=True)
            rc = child.wait(timeout=179)
        finally:
            if child is not None and child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=1)
        output.seek(0)
        raw = output.read(65537)
        if len(raw)>65536:
            raise Stop("unexpected_native_receipt_size")
        try:
            result = json.loads(raw)
        except (ValueError,UnicodeError):
            return {"error":"namespace_or_harness_exited_without_receipt","returncode":rc},1
        if not isinstance(result,dict) or result.get("status") not in ("failed","live_join_and_loadout_verified"):
            raise Stop("invalid_native_receipt")
        return result,int(rc != 0 or result["status"] != "live_join_and_loadout_verified")

def main():
    os.umask(0o077)
    for sig in (signal.SIGALRM,signal.SIGTERM,signal.SIGINT,signal.SIGHUP):
        signal.signal(sig,interrupted)
    signal.alarm(CONFIG["receiver_limit"])
    try:
        if os.path.lexists(OUT):
            raise Stop("output_already_exists")
        with tempfile.TemporaryDirectory(prefix="jk-force-input-",dir="/var/tmp") as name:
            tmp=Path(name)
            receive(tmp)
            result,code=qualify(tmp)
    except Stop as error:
        result,code={"error":str(error)},1
    except Exception as error:
        result,code={"error":"receiver_"+type(error).__name__},1
    finally:
        signal.alarm(0)
    print(json.dumps(result,separators=(",",":")),flush=True)
    return code
sys.exit(main())
'''


def wsl(program, distro, configuration):
    # repr serializes values as Python literals; caller paths never become code.
    program = "CONFIG = " + repr(configuration) + "\n" + program
    data = base64.b64encode(program.encode("utf-8")).decode("ascii")
    stub = "import base64;exec(base64.b64decode('" + data + "'))"
    return ["wsl.exe","--distribution",distro,"--cd","/var/tmp","--exec","/usr/bin/python3",
            "-I","-c",stub]


def public_json(raw):
    if len(raw)>65536:
        return {"error":"oversized_wsl_response"}
    try:
        result=json.loads(raw)
        if isinstance(result,dict):
            return result
    except (ValueError,UnicodeError):
        pass
    return {"error":"wsl_exited_without_json"}


def ship(pipe, errors, args, harness_sha256):
    try:
        with pipe, tarfile.open(fileobj=pipe,mode="w|",format=tarfile.USTAR_FORMAT,
                                bufsize=256*1024) as stream:
            files = [("res1hi.gob",args.data/"Resource"/"Res1hi.gob",128*1024**2),
                     ("res2.gob",args.data/"Resource"/"Res2.gob",128*1024**2),
                     ("jk_.cd",args.data/"Resource"/"JK_.CD",1024**2),
                     ("jk1mp.gob",args.data/"Episode"/"JK1MP.GOB",16*1024**2),
                     ("qualification.py",args.harness,128*1024)]
            for name, path, maximum in files:
                if not path.is_file():
                    errors.append({"error":"required_input_missing","file":name})
                    return
                with path.open("rb") as src:
                    entry = tarfile.TarInfo(name)
                    entry.size=os.fstat(src.fileno()).st_size
                    entry.mode=0o600
                    if not 1<=entry.size<=maximum:
                        errors.append({"error":"input_size_outside_bound","file":name})
                        return
                    if name=="qualification.py":
                        script=src.read(maximum+1)
                        if hashlib.sha256(script).hexdigest()!=harness_sha256:
                            errors.append({"error":"harness_sha256_mismatch"})
                            return
                        stream.addfile(entry,io.BytesIO(script))
                    else:
                        stream.addfile(entry,src)
    except (BrokenPipeError,ConnectionResetError):
        pass
    except Exception as error:
        errors.append({"error":"sender_"+type(error).__name__})


def execute(args):
    start=time.monotonic()
    if not args.harness.is_file() or not 1 <= args.harness.stat().st_size <= 128 * 1024:
        return {"error":"harness_missing_or_oversized"},1
    harness_sha256 = hashlib.sha256(args.harness.read_bytes()).hexdigest()
    configuration = {"repo":args.repo,"output":args.output,"duration":args.duration,
                     "map":args.map,"harness_sha256":harness_sha256}
    pre=subprocess.run(wsl(PREFLIGHT,args.distro,configuration),stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=90)
    report=public_json(pre.stdout)
    if pre.returncode or report != {"bridge_preflight":"ready"}:
        return report,1
    # Reserve time for a SIGTERM-aware Linux teardown and Windows process exit.
    left=TIME_LIMIT-(time.monotonic()-start)
    configuration["receiver_limit"] = max(1,int(left)-12)
    program = RECEIVER
    errors=[]
    with tempfile.TemporaryFile() as response:
        child=subprocess.Popen(wsl(program,args.distro,configuration),stdin=subprocess.PIPE,stdout=response,stderr=subprocess.DEVNULL)
        thread=threading.Thread(target=ship,args=(child.stdin,errors,args,harness_sha256),daemon=True)
        try:
            thread.start()
            rc=child.wait(timeout=max(1,TIME_LIMIT-2-(time.monotonic()-start)))
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=1)
        thread.join(timeout=.5)
        if errors:
            return errors[0],1
        response.seek(0)
        result=public_json(response.read(65537))
        return result,int(rc!=0 or "error" in result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--distro", required=True, help="An existing WSL distribution.")
    parser.add_argument("--data", type=Path, required=True, help="Owned Windows JK installation.")
    parser.add_argument("--repo", required=True, help="Absolute repository path inside WSL.")
    parser.add_argument("--output", required=True, help="Fresh absolute output path inside WSL.")
    parser.add_argument("--harness", type=Path,
                        default=Path(__file__).with_name("native_force_observation.py"))
    parser.add_argument("--map", choices=("m2.jkl", "m4.jkl", "m5.jkl", "m10.jkl",
                                         "m_boss15.jkl", "m_boss17.jkl"), default="m_boss17.jkl")
    parser.add_argument("--duration", type=int, choices=range(1, 121), default=75, metavar="1..120")
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("Run this bridge on Windows; run native_force_observation.py directly on Linux.")
    if not args.data.is_dir():
        parser.error("--data must identify an existing game installation.")
    for value in (args.repo, args.output):
        if not PurePosixPath(value).is_absolute() or "\x00" in value:
            parser.error("WSL repository and output paths must be absolute Linux paths.")
    try:
        result, code=execute(args)
    except (KeyboardInterrupt,subprocess.TimeoutExpired):
        result,code={"error":"bridge_interrupted_or_timed_out"},1
    except Exception as error:
        result,code={"error":"bridge_"+type(error).__name__},1
    print(json.dumps(result,separators=(",",":")),flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())

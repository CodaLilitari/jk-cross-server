#!/usr/bin/env python3
"""Package a compiled current JKWeb bot with its patch and LGPL relink inputs."""
from pathlib import Path
import argparse
import hashlib
import io
import json
import shlex
import shutil
import subprocess
import tarfile

BASE = "7a6f95c9a3399e59acbf019dc6b25f9981d29dff"
SDK = "6.0.12"
ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def package(source, build):
    if subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip() != BASE:
        raise ValueError("The engine must use the documented upstream commit.")
    patch = ROOT / "web_bots/engine.patch"
    subprocess.run(["git", "diff", "--check"], cwd=source, check=True)
    patch.write_bytes(subprocess.check_output(["git", "diff", "--binary", "HEAD"], cwd=source))
    subprocess.run(["git", "apply", "--reverse", "--check", str(patch)], cwd=source, check=True)
    out = ROOT / "bin/bots-jkweb"
    out.mkdir(parents=True, exist_ok=True)
    for name in ("openjkdf2.js", "openjkdf2.wasm"):
        shutil.copy2(build / name, out / name)
    link = shlex.split((build / "CMakeFiles/openjkdf2.dir/link.txt").read_text())
    expanded = []
    for arg in link[1:]:
        if arg.startswith("@"):
            expanded.extend(shlex.split((build / arg[1:]).read_text()))
        else:
            expanded.append(arg)
    members = {}
    relink = ["em++"]
    for arg in expanded:
        path = Path(arg)
        if arg.startswith("-L"):
            continue
        if path.is_absolute():
            if path.parent == source / "packaging/wasm":
                arg = "pre-js/" + path.name
                members[arg] = path
            else:
                raise ValueError("Unexpected absolute linker input: " + arg)
        elif arg.endswith((".o", ".a")):
            if not (build / arg).is_file():
                raise ValueError("Missing linker input: " + arg)
            members[arg] = build / arg
        relink.append(arg)
    for file in (source / "src/external/libsmacker").iterdir():
        if file.is_file():
            members["libsmacker/" + file.name] = file
    for name in ("engine_config.h", "types_enums.h"):
        members["libsmacker/" + name] = source / "src" / name
    members["ENGINE_LICENSE.md"] = source / "LICENSE.md"
    compiler_flags = {}
    for row in (build / "CMakeFiles/sith_engine.dir/flags.make").read_text().splitlines():
        if " = " in row:
            key, value = row.split(" = ", 1)
            compiler_flags[key] = shlex.split(value)
    compile_args = compiler_flags["C_DEFINES"] + compiler_flags["C_FLAGS"] + ["-Ilibsmacker"]
    script = '''#!/usr/bin/env python3
"""Activate Emscripten 6.0.12, modify libsmacker, then run this script."""
from pathlib import Path
import json, subprocess
root = Path(__file__).resolve().parent
config = json.loads((root / "link.json").read_text())
for name in ("smacker", "smk_bitstream", "smk_hufftree"):
    subprocess.run(["emcc", *config["compile_args"], "-c", "libsmacker/"+name+".c",
        "-o", "CMakeFiles/sith_engine.dir/src/external/libsmacker/"+name+".c.o"], cwd=root, check=True)
subprocess.run(config["link"], cwd=root, check=True)
print(root / "openjkdf2.wasm")
'''
    archive = ROOT / "web_bots/engine-relink.tar.gz"
    with tarfile.open(archive, "w:gz", dereference=True) as tar:
        for name, file in sorted(members.items()):
            tar.add(file, arcname=name, recursive=False)
        for name, content in (("relink.py", script), ("link.json", json.dumps({"link": relink, "compile_args": compile_args}, indent=2))):
            data = content.encode()
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            entry.mode = 0o755 if name.endswith(".py") else 0o644
            tar.addfile(entry, io.BytesIO(data))
    changed = subprocess.check_output(["git", "diff", "--name-only", "HEAD"], cwd=source, text=True).splitlines()
    files = [out / "openjkdf2.js", out / "openjkdf2.wasm", patch, archive]
    manifest = {
        "repository": "https://github.com/tristamus/OpenJKDF2",
        "branch": "web-mp", "base_commit": BASE, "emscripten": SDK,
        "netcode": 2, "game": "JKDF2", "game_assets_included": False,
        "method": "CMake source build with ordinary player input hooks; unchanged upstream WSRelay protocol.",
        "patch": "web_bots/engine.patch", "relink": "web_bots/engine-relink.tar.gz",
        "source_pins": subprocess.check_output(["git", "submodule", "status", "lib/zlib", "lib/libpng"], cwd=source, text=True).splitlines(),
        "changed_sources": {name: sha(source / name) for name in changed},
        "files": {str(p.relative_to(ROOT)): {"sha256": sha(p), "bytes": p.stat().st_size} for p in files},
    }
    (ROOT / "web_bots/BUILD.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest["files"], indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("build", type=Path)
    args = parser.parse_args()
    package(args.source.resolve(), args.build.resolve())

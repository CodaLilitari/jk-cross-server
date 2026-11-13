"""Package native outputs, notices, and exact linkable LGPL materials."""
from pathlib import Path
import argparse
import hashlib
import io
import json
import shlex
import shutil
import subprocess
import tarfile

BASE = "74e4657c4f1751d09af9ad9e056acb8f41997acb"


def make_relink_plan(link_text, build):
    """Keep link flags; unescape CMake's literal dollar without evaluating a shell."""
    link = shlex.split(link_text)
    if not link:
        raise ValueError("Empty native link command")
    link[0] = "c++"
    relink, archive_paths = [], {}
    for index, argument in enumerate(link):
        # shlex preserves \$ inside double quotes; the original shell/CMake link
        # interprets it as a literal dollar. subprocess receives that literal.
        if argument.startswith("-Wl,-rpath,"):
            argument = argument.replace("\\$", "$")
        if index and link[index - 1] == "-o":
            if argument != "openjkdf2":
                raise ValueError("Unexpected native output: " + argument)
            relink.append("openjkdf2-relinked")
            continue
        path = Path(argument)
        if not argument.startswith("-") and path.suffix in (".o", ".a", ".so"):
            # Absolute shared libraries remain distribution dependencies. Bundle
            # every static input, including the system GLEW archive.
            if not path.is_absolute() or path.suffix in (".o", ".a"):
                source = (build / path).resolve()
                if not source.is_file():
                    raise FileNotFoundError(source)
                name = "system-static/" + path.name if path.is_absolute() else argument
                if name in archive_paths and archive_paths[name] != source:
                    raise ValueError("Conflicting archive input: " + name)
                archive_paths[name] = source
                argument = name
        relink.append(argument)
    return relink, archive_paths


def make_post_link_plan(executable):
    """Match the pinned Release build's strip step when the shipped ELF is stripped."""
    sections = subprocess.check_output(["readelf", "--sections", "--wide", str(executable)], text=True)
    return [["strip", "openjkdf2-relinked"]] if ".symtab" not in sections else []


RELINK_SCRIPT = '''#!/usr/bin/env python3
"""Rebuild libsmacker and relink; optionally verify the exact supplied objects."""
from pathlib import Path
import argparse
import json
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--supplied-objects", action="store_true",
                    help="Skip library compilation and relink the packaged objects unchanged")
args = parser.parse_args()
root = Path(__file__).resolve().parent
if not args.supplied_objects:
    for name in ("smacker", "smk_bitstream", "smk_hufftree"):
        subprocess.run(["cc", "-O2", "-fshort-wchar", "-c",
                        str(root / "libsmacker" / (name + ".c")), "-o",
                        str(root / "CMakeFiles/sith_engine.dir/src/external/libsmacker" / (name + ".c.o"))],
                       check=True)
subprocess.run(json.loads((root / "link.json").read_text()), cwd=root, check=True)
for command in json.loads((root / "post-link.json").read_text()):
    subprocess.run(command, cwd=root, check=True)
print(root / "openjkdf2-relinked")
'''


LICENSES = [
 'LICENSE.md','src/external/libsmacker/COPYING','src/external/libsmusher/LICENSE',
 'src/external/fcaseopen/LICENSE.txt','src/external/nativefiledialog-extended/LICENSE',
 '3rdparty/json/LICENSE.MIT','lib/zlib/LICENSE','lib/libpng/LICENSE',
 'lib/glew/LICENSE.txt','lib/freeglut/COPYING','lib/physfs/LICENSE.txt',
 'lib/GameNetworkingSockets/LICENSE','lib/protobuf/LICENSE',
 'lib/protobuf/third_party/utf8_range/LICENSE','lib/SDL/LICENSE.txt',
 'lib/SDL/src/hidapi/LICENSE.txt','lib/SDL/src/hidapi/LICENSE-bsd.txt',
 'lib/SDL/src/hidapi/LICENSE-orig.txt','lib/SDL/src/video/yuv2rgb/LICENSE',
 'lib/SDL_mixer/LICENSE.txt','lib/SDL_mixer/src/timidity/COPYING',
 'lib/SDL_mixer/src/dr_libs/LICENSE','lib/SDL_mixer/external/ogg/COPYING',
 'lib/SDL_mixer/external/vorbis/COPYING','lib/SDL_mixer/external/opus/COPYING',
 'lib/SDL_mixer/external/opus/LICENSE_PLEASE_READ.txt',
 'lib/SDL_mixer/external/opusfile/COPYING']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("build", type=Path)
    args = parser.parse_args()
    repo, build = args.source.resolve(), args.build.resolve()
    native = Path(__file__).resolve().parent
    project, runtime = native.parent, native.parent / "bin/linux-x86_64"
    if subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip() != BASE:
        parser.error("The source checkout does not match the pinned base")
    link_text = (build / "CMakeFiles/openjkdf2.dir/link.txt").read_text()
    relink, archive_paths = make_relink_plan(link_text, build)
    post_link = make_post_link_plan(build / "openjkdf2")
    runtime.mkdir(parents=True, exist_ok=True)
    for name in ("openjkdf2", "libGameNetworkingSockets.so"):
        shutil.copy2(build / name, runtime / name)
    for relative in LICENSES:
        path = project / "licenses/native" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo / relative, path)
    with tarfile.open(native / "relink-linux-x86_64.tar.gz", "w:gz") as tar:
        for name, path in sorted(archive_paths.items()):
            tar.add(path, arcname=name, recursive=False)
        for path in sorted((repo / "src/external/libsmacker").iterdir()):
            if path.is_file():
                tar.add(path, arcname="libsmacker/" + path.name, recursive=False)
        for name in ("engine_config.h", "types_enums.h"):
            tar.add(repo / "src" / name, arcname="libsmacker/" + name, recursive=False)
        tar.add(repo / "LICENSE.md", arcname="libsmacker/ENGINE_LICENSE.md", recursive=False)
        for name, content in (("link.json", json.dumps(relink, indent=2)),
                              ("post-link.json", json.dumps(post_link, indent=2)),
                              ("original-link.txt", link_text), ("relink.py", RELINK_SCRIPT)):
            data = content.encode()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o755 if name.endswith(".py") else 0o644
            tar.addfile(info, io.BytesIO(data))
    manifest = {
        "repository": "https://gitlab.com/codalilitari/OpenJKDF2-MotS-Fixes",
        "base_commit": BASE,
        "patch": "native/crossplay-dedicated.patch",
        "platform": "Linux x86_64",
        "build_environment": {
            "distribution": Path("/etc/os-release").read_text(),
            "compiler": subprocess.check_output(["cc", "--version"], text=True).splitlines()[0],
        },
        "source_pins": subprocess.check_output(["git", "submodule", "status", "--recursive"], cwd=repo, text=True).splitlines(),
        "files": {},
        "system_libraries": subprocess.check_output(["ldd", str(runtime / "openjkdf2")], text=True).splitlines(),
        "relink_inputs": {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in sorted(archive_paths.items())},
        "relink_modes": {
            "default": "Recompile bundled LGPL libsmacker source, then link; output may differ from packaged executable.",
            "supplied_objects": "Relink every supplied object unchanged, preserving original flags including literal $ORIGIN.",
        },
        "relink_post_link_commands": post_link,
    }
    for path in (runtime / "openjkdf2", runtime / "libGameNetworkingSockets.so",
                 native / "crossplay-dedicated.patch", native / "relink-linux-x86_64.tar.gz"):
        manifest["files"][str(path.relative_to(project))] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size,
        }
    (native / "BUILD.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest["files"], indent=2))


if __name__ == "__main__":
    main()

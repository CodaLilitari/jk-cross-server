#!/usr/bin/env python3
"""Build actual engine admin/chat/action regressions with inert delivery stubs.

Includes ordinary QuitPlayer and SendEndLevel packet/timer contracts. This does
not establish a live mixed-client map transition or transport disconnect.
"""
from pathlib import Path
import argparse
import shlex
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--cc", default="cc")
    parser.add_argument("--cxx", default="c++")
    parser.add_argument("--sanitize", action="store_true")
    args = parser.parse_args()
    source, build = args.source.resolve(), args.build.resolve()
    flags_path = build / "CMakeFiles/sith_engine.dir/flags.make"
    if not flags_path.is_file() or not (source / "src/Dss/sithAdmin.c").is_file():
        parser.error("Need patched dedicated engine source and a configured Unix Makefiles build")
    entries = {}
    for line in flags_path.read_text().splitlines():
        if " = " in line:
            key, value = line.split(" = ", 1)
            entries[key] = shlex.split(value)
    flags = ["-I" + str(source / "src")]
    for key in ("C_DEFINES", "C_INCLUDES", "C_FLAGS"):
        if key not in entries:
            parser.error(f"{flags_path} has no {key}")
        flags.extend(entries[key])
    for include in ("lib/SDL/include", "lib/SDL_mixer/include", "lib/GameNetworkingSockets/include"):
        if (source / include).is_dir():
            flags.append("-I" + str(source / include))
    flags += ["-UNDEBUG", "-ffunction-sections", "-fdata-sections"]
    sanitize = ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"] if args.sanitize else []
    tests = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix="jk-server-admin-test-") as directory:
        temporary = Path(directory)
        objects = []
        for path in (source / "src/Dss/sithAdmin.c", source / "src/Dss/sithMulti.c",
                     source / "src/Dss/jkDSS.c", tests / "test_server_admin.c"):
            obj = temporary / (path.name + ".o")
            subprocess.run([args.cc, *flags, *sanitize, "-c", str(path), "-o", str(obj)], check=True)
            objects.append(str(obj))
        binary = temporary / "test_server_admin"
        subprocess.run([args.cc, *objects, *sanitize, "-Wl,--gc-sections", "-lm", "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
        connections = temporary / "test_server_admin_connections"
        subprocess.run([args.cxx, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-UNDEBUG",
                        "-I" + str(source / "src"), *sanitize,
                        str(tests / "test_server_admin_connections.cpp"), "-o", str(connections)], check=True)
        subprocess.run([str(connections)], check=True)


if __name__ == "__main__":
    main()

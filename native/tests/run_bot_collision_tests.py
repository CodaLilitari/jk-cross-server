#!/usr/bin/env python3
"""Compile the real collision helper with its real math for C2 regression.

Requires patched bot source and a configured Unix Makefiles engine build.
Does not run a game session or qualify map traversal.
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
    args = parser.parse_args()
    source, build = args.source.resolve(), args.build.resolve()
    flags = build / "CMakeFiles/sith_engine.dir/flags.make"
    if not flags.is_file() or not (source / "src/Engine/sithIntersect.c").is_file():
        parser.error("Need patched bot source and a configured Unix Makefiles build")
    entries = {}
    for line in flags.read_text().splitlines():
        if " = " in line:
            key, value = line.split(" = ", 1)
            entries[key] = shlex.split(value)
    command = [args.cc, "-I" + str(source / "src")]
    for key in ("C_DEFINES", "C_INCLUDES", "C_FLAGS"):
        if key not in entries:
            parser.error(f"{flags} has no {key}")
        command.extend(entries[key])
    for include in ("lib/SDL/include", "lib/SDL_mixer/include", "lib/GameNetworkingSockets/include"):
        if (source / include).is_dir():
            command.append("-I" + str(source / include))
    command += ["-UNDEBUG", "-ffunction-sections", "-fdata-sections",
                str(Path(__file__).with_name("test_bot_collision.c"))]
    command.extend(str(source / "src" / name) for name in (
        "Primitives/rdMath.c", "Primitives/rdVector.c", "General/stdMath.c"))
    command += ["-Wl,--gc-sections", "-lm"]
    with tempfile.TemporaryDirectory(prefix="jk-bot-collision-test-") as directory:
        binary = Path(directory) / "test_bot_collision"
        subprocess.run(command + ["-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    main()

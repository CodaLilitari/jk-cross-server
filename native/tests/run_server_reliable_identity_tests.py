#!/usr/bin/env python3
"""Compile actual engine reliable dispatch with inert, bounded delivery fixtures."""
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
    entries = {}
    for line in (build / "CMakeFiles/sith_engine.dir/flags.make").read_text().splitlines():
        if " = " in line:
            key, value = line.split(" = ", 1)
            entries[key] = shlex.split(value)
    flags = ["-I" + str(source / "src")]
    for key in ("C_DEFINES", "C_INCLUDES", "C_FLAGS"):
        flags.extend(entries[key])
    for include in ("lib/SDL/include", "lib/SDL_mixer/include", "lib/GameNetworkingSockets/include"):
        if (source / include).is_dir():
            flags.append("-I" + str(source / include))
    flags += ["-UNDEBUG", "-ffunction-sections", "-fdata-sections"]
    with tempfile.TemporaryDirectory(prefix="jk-reliable-identity-") as directory:
        binary = Path(directory) / "test_reliable_identity"
        subprocess.run([args.cc, *flags, str(source / "src/Devices/sithComm.c"),
                        str(Path(__file__).with_name("test_server_reliable_identity.c")),
                        "-Wl,--gc-sections", "-lm", "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    main()

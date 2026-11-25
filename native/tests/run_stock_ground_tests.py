#!/usr/bin/env python3
"""Drive the engine's own ground physics and movement control with bot inputs.

Compiles Engine/sithPhysics.c and the unmodified sithControl_PlayerMovement
from the patched engine source against flat synthetic ground. This measures
speeds, headings and stopping distances; it is not a level or a live match.
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent


def stock_function(source: Path, filename: str, name: str) -> str:
    """Extract one whole top-level upstream definition from the checkout."""
    text = (source / "src" / filename).read_text()
    matches = re.findall(rf"^\w[^\n]*\b{name}\([^;\n]*\)\s*\{{[\s\S]*?^\}}", text, re.MULTILINE)
    if len(matches) != 1:
        raise ValueError(f"Expected one top-level definition of {name} in {filename}")
    return matches[0] + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True,
                        help="Engine source with the bot patches applied")
    parser.add_argument("--build", type=Path, required=True,
                        help="Configured engine CMake build directory")
    parser.add_argument("--cc", default=os.environ.get("CC", "cc"))
    args = parser.parse_args()
    source = args.source.resolve()
    flags_file = args.build.resolve() / "CMakeFiles/sith_engine.dir/flags.make"
    if not flags_file.is_file() or not (source / "src/AI/jkBotTactics.inc").is_file():
        parser.error("Need the patched source and a configured Unix Makefiles CMake build")
    flags = dict(line.split(" = ", 1) for line in flags_file.read_text().splitlines() if " = " in line)
    with tempfile.TemporaryDirectory(prefix="jk-stock-ground-") as directory:
        work = Path(directory)
        (work / "stock_functions.inc").write_text(
            stock_function(source, "Devices/sithControl.c", "sithControl_PlayerMovement"))
        command = [args.cc, f"-I{source}/src", f"-I{work}"]
        for key in ("C_DEFINES", "C_INCLUDES", "C_FLAGS"):
            command.extend(shlex.split(flags[key]))
        for library in ("SDL", "SDL_mixer", "GameNetworkingSockets"):
            command.append(f"-I{source}/lib/{library}/include")
        command += ["-UNDEBUG", "-ffunction-sections", "-fdata-sections", str(HERE / "test_stock_ground.c")]
        command += [str(source / "src" / unit) for unit in
                    ("Primitives/rdMatrix.c", "Primitives/rdMath.c", "Primitives/rdVector.c",
                     "General/stdMath.c")]
        executable = work / "check"
        subprocess.run([*command, "-Wl,--gc-sections", "-lm", "-o", str(executable)], check=True)
        subprocess.run([str(executable)], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

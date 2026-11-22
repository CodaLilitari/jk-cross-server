"""Replay a captured swimmer state with the patched JKWeb engine sources."""
import argparse
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

from geometry import write_geometry

HERE = Path(__file__).resolve().parent
FUNCTIONS = {
    "World/sithThing.c": (
        "sithThing_ValidateThingPointer sithThing_UpdateMove sithThing_SetSector "
        "sithThing_ExitSector sithThing_EnterSector sithThing_EnterWater "
        "sithThing_ExitWater sithThing_AttachThingToSurface sithThing_DetachThing"
    ),
    "World/sithActor.c": "sithActor_Update",
    "Devices/sithControl.c": (
        "sithControl_PlayerLook sithControl_FreeCam sithControl_PlayerMovement"
    ),
}


def stock_functions(source):
    """Extract whole top-level upstream definitions from the supplied checkout."""
    functions = []
    for filename, names in FUNCTIONS.items():
        text = (source / "src" / filename).read_text()
        for name in names.split():
            pattern = rf"^\w[^\n]*\b{name}\([^;\n]*\)\s*\{{[\s\S]*?^\}}"
            matches = re.findall(pattern, text, re.MULTILINE)
            if len(matches) != 1:
                raise ValueError(f"Expected one top-level definition of {name} in {filename}")
            functions.append(matches[0])
    return "\n\n".join(functions) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="patched JKWeb source tree")
    parser.add_argument("--build", type=Path, required=True, help="configured native CMake build")
    parser.add_argument("--map", type=Path, required=True, help="local owned Canyon Oasis JKL")
    parser.add_argument("--origin", type=int, default=41)
    parser.add_argument("--wet", type=int, default=54)
    parser.add_argument("--dry", type=int, default=41)
    parser.add_argument("--start-sector", type=int, help="observed swimmer sector (defaults to --wet)")
    parser.add_argument("--position", type=float, nargs=3, required=True, metavar=("X", "Y", "Z"))
    timing = parser.add_mutually_exclusive_group(required=True)
    timing.add_argument("--control-hz", type=int, choices=(15, 20, 30, 60))
    timing.add_argument("--control-dt", type=float, help="observed seconds per control update")
    parser.add_argument("--flags", type=lambda s: int(s, 16), required=True)
    parser.add_argument("--health", type=float, required=True)
    parser.add_argument("--endurance-ms", type=int, required=True)
    parser.add_argument("--pitch", type=float, required=True)
    parser.add_argument("--yaw", type=float, default=0)
    parser.add_argument("--vertical-speed", type=float, required=True)
    args = parser.parse_args()
    dt = args.control_dt if args.control_dt is not None else 1.0 / args.control_hz
    if not 1.0 / 150 <= dt <= 0.25:
        parser.error("control interval must be between 1/150 and 0.25 seconds")
    start_sector = args.wet if args.start_sector is None else args.start_sector
    source = args.source.resolve()
    flags_file = args.build.resolve() / "CMakeFiles/sith_engine.dir/flags.make"
    flags = dict(line.split(" = ", 1) for line in flags_file.read_text().splitlines() if " = " in line)
    with tempfile.TemporaryDirectory(prefix="jk-stock-water-") as tmp:
        work = Path(tmp)
        (work / "stock_functions.inc").write_text(stock_functions(source))
        geometry = work / "map.numeric"
        write_geometry(args.map, geometry)
        compile_args = [os.environ.get("CC", "cc"), f"-I{source}/src", f"-I{work}"]
        for key in ("C_DEFINES", "C_INCLUDES", "C_FLAGS"):
            compile_args.extend(shlex.split(flags[key]))
        for lib in ("SDL", "SDL_mixer", "GameNetworkingSockets"):
            compile_args.append(f"-I{source}/lib/{lib}/include")
        compile_args.extend(["-UNDEBUG", "-ffunction-sections", "-fdata-sections", str(HERE / "replay.c")])
        units = ("Primitives/rdMatrix.c", "Primitives/rdMath.c", "Primitives/rdVector.c",
                 "General/stdMath.c", "World/sithSector.c")
        compile_args.extend(str(source / "src" / unit) for unit in units)
        executable = work / "replay"
        subprocess.run([*compile_args, "-Wl,--gc-sections", "-lm", "-o", executable], check=True)
        x, y, z = args.position
        values = dict(X=x, Y=y, Z=z, PF=format(args.flags, "x"),
                      HEALTH=args.health, END=args.endurance_ms, PITCH=args.pitch,
                      YAW=args.yaw, VZ=args.vertical_speed)
        env = {k: v for k, v in os.environ.items() if not k.startswith("TRACE_") and k != "EXTRA"}
        env.update({f"TRACE_{key}": str(value) for key, value in values.items()})
        subprocess.run([executable, geometry, str(args.origin), str(args.wet), str(args.dry),
                        str(start_sector), str(dt)],
                       check=True, env=env)


if __name__ == "__main__":
    main()

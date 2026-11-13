#!/usr/bin/env python3
"""Run actual patched-engine observer invariants with controlled render fixtures."""
from pathlib import Path
import argparse
import shlex
import subprocess
import tempfile

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--build",type=Path,required=True)
    args=parser.parse_args()
    source,build=args.source.resolve(),args.build.resolve()
    entries={}
    for line in (build/"CMakeFiles/sith_engine.dir/flags.make").read_text().splitlines():
        if " = " in line:
            key,value=line.split(" = ",1);entries[key]=shlex.split(value)
    command=["cc","-I"+str(source/"src")]
    for key in ("C_DEFINES","C_INCLUDES","C_FLAGS"):command+=entries[key]
    command += ["-I"+str(source/"lib/SDL/include"),"-I"+str(source/"lib/SDL/include/SDL3"),"-UNDEBUG","-ffunction-sections","-fdata-sections"]
    with tempfile.TemporaryDirectory(prefix="jk-observer-test-") as directory:
        for name in ("test_spectator_render","test_spectator_controller","test_spectator_cache","test_spectator_frame","test_spectator_geometry"):
            output=Path(directory)/name
            sources=[str(Path(__file__).with_name(name+".c"))]
            if name != "test_spectator_render":
                sources += [str(build/"generated/globals.c")]
            if name in ("test_spectator_controller","test_spectator_frame","test_spectator_geometry"):
                sources += [str(source/path) for path in ("src/Primitives/rdMatrix.c","src/Primitives/rdVector.c","src/General/stdMath.c")]
            compiled=subprocess.run(command+sources+["-Wl,--gc-sections","-lm","-o",str(output)])
            if compiled.returncode:
                raise SystemExit(compiled.returncode)
            tested=subprocess.run([str(output)])
            if tested.returncode:
                raise SystemExit(f"{name} failed with exit status {tested.returncode}")

if __name__=="__main__":main()

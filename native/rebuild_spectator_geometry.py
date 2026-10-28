#!/usr/bin/env python3
"""Recompile geometry units and relink locally, preserving baseline objects/build.

This is an incremental qualification helper, not a distributable build recipe.
It requires the exact recovered baseline compile database and link inputs.
"""
import argparse
import json
from pathlib import Path
import shlex
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, required=True)
parser.add_argument('--baseline-build', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
source, baseline, output = (p.resolve() for p in (args.source, args.baseline_build, args.output))
if output == baseline or baseline in output.parents:
    parser.error('output must be separate from the baseline build')
output.mkdir(parents=True, exist_ok=True)
entries = json.loads((baseline / 'compile_commands.json').read_text())
changed = ['src/Main/jkObserver.c', 'src/Raster/rdCache.c']
replacements = {}
commands = []
for relative in changed:
    entry = next(e for e in entries if e['file'].endswith('/' + relative))
    original_source = str(Path(entry['file']).parents[len(Path(relative).parts)-1])
    command = [token.replace(original_source+'/', str(source)+'/') for token in shlex.split(entry['command'])]
    index = command.index('-o') + 1
    original_object = command[index]
    destination = output / Path(original_object).name
    command[index] = str(destination)
    replacements[original_object] = str(destination)
    commands.append(command)
    subprocess.run(command, cwd=baseline, check=True)
command = shlex.split((baseline/'CMakeFiles/openjkdf2.dir/link.txt').read_text())
command = [replacements.get(token, token) for token in command if not token.startswith('-Wl,--dependency-file=')]
# CMake shell escaping must not survive into direct subprocess argv.
command = [token.replace('\\$', '$') if token.startswith('-Wl,-rpath,') else token for token in command]
command[command.index('-o')+1] = str(output/'openjkdf2')
commands.append(command)
subprocess.run(command, cwd=baseline, check=True)
(output/'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
print(output/'openjkdf2')

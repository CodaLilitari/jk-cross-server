#!/usr/bin/env python3
"""Syntax-check the actual Linux observer with the optional n-gon profile.

Uses the recovered compile database, changes source paths and adds only the
n-gon definition plus syntax-only mode. No baseline objects are written.
This is not a TARGET_TWL build or runtime qualification.
"""
import argparse
import json
from pathlib import Path
import shlex
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--build', type=Path, required=True)
    args = parser.parse_args()
    source, build = args.source.resolve(), args.build.resolve()
    entries = json.loads((build / 'compile_commands.json').read_text())
    entry = next(e for e in entries if e['file'].endswith('/src/Main/jkObserver.c'))
    original_source = str(Path(entry['file']).parents[2])
    command = [token.replace(original_source + '/', str(source) + '/')
               for token in shlex.split(entry['command'])]
    index = command.index('-o')
    del command[index:index + 2]
    command.remove('-c')
    command += ['-DRDCACHE_RENDER_NGONS', '-fsyntax-only']
    subprocess.run(command, cwd=build, check=True)
    print('PASS actual Linux SDL2 observer compiles with RDCACHE_RENDER_NGONS')


if __name__ == '__main__':
    main()

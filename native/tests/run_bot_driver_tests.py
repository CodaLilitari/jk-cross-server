#!/usr/bin/env python3
"""Compile concrete AI regressions against the patched, configured engine.

A controlled stub collision engine is used. This does not establish live game,
transport or retail/browser compatibility. Requires GCC-compatible section GC.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import shlex
import subprocess
import tempfile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True,
                        help='Engine source with bot-client.patch applied')
    parser.add_argument('--build', type=Path, required=True,
                        help='Configured engine CMake build directory')
    parser.add_argument('--cc', default='cc')
    args = parser.parse_args()
    source, build = args.source.resolve(), args.build.resolve()
    flags = build / 'CMakeFiles/sith_engine.dir/flags.make'
    if not flags.is_file() or not (source / 'src/AI/jkBot.c').is_file():
        parser.error('Need the patched source and a configured Unix Makefiles CMake build')
    entries = {}
    for line in flags.read_text().splitlines():
        if ' = ' in line:
            key, value = line.split(' = ', 1)
            entries[key] = shlex.split(value)
    # Put patched source first if flags came from the exact base build.
    command = [args.cc, '-I' + str(source / 'src')]
    for key in ('C_DEFINES', 'C_INCLUDES', 'C_FLAGS'):
        if key not in entries:
            parser.error(f'{flags} has no {key}')
        command.extend(entries[key])
    for include in ('lib/SDL/include', 'lib/SDL_mixer/include',
                    'lib/GameNetworkingSockets/include'):
        if (source / include).is_dir():
            command.append('-I' + str(source / include))
    command += ['-Wall', '-Wextra', '-Werror', '-UNDEBUG', '-ffunction-sections',
                '-fdata-sections', str(Path(__file__).with_name('test_bot_driver.c')),
                '-Wl,--gc-sections', '-lm']
    with tempfile.TemporaryDirectory(prefix='jk-bot-regression-') as directory:
        output = Path(directory) / 'test_bot_driver'
        subprocess.run(command + ['-o', str(output)], check=True)
        subprocess.run([str(output)], check=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

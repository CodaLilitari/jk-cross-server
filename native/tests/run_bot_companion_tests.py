#!/usr/bin/env python3
"""Build the real native bot with a local socketpair and controlled world."""
import argparse
from pathlib import Path
import shlex
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, required=True)
parser.add_argument('--build', type=Path, required=True)
parser.add_argument('--cc', default='cc')
args = parser.parse_args()
source = args.source.resolve()
flags = {}
for line in (args.build / 'CMakeFiles/sith_engine.dir/flags.make').read_text().splitlines():
    if ' = ' in line:
        key, value = line.split(' = ', 1)
        flags[key] = shlex.split(value)
with tempfile.TemporaryDirectory(prefix='jk-companion-test-') as directory:
    executable = Path(directory) / 'test'
    cmd = [args.cc, '-I' + str(source / 'src'), *flags['C_DEFINES'], *flags['C_INCLUDES'],
           *flags['C_FLAGS'], '-Wall', '-Wextra', '-Werror', '-UNDEBUG', '-ffunction-sections',
           '-fdata-sections', *(['-DTEST_INTEGRATED_HEARING'] if (source / 'src/AI/jkBotHearing.inc').is_file() else []), str(Path(__file__).with_name('test_bot_companion.c')),
           '-Wl,--gc-sections', '-lm', '-o', str(executable)]
    # Real chat decoding/attribution with the ordinary network transport replaced
    # at its boundary by the fixture's recorded outbound chat sink.
    obj = Path(directory) / 'multichat.o'
    subprocess.run([args.cc, '-I' + str(source / 'src'), *flags['C_DEFINES'], *flags['C_INCLUDES'],
                    *flags['C_FLAGS'], '-ffunction-sections', '-fdata-sections',
                    '-DsithMulti_SendChat=sithMulti_OriginalSendChat', '-c',
                    str(source / 'src/Dss/sithMulti.c'), '-o', str(obj)], check=True)
    cmd.insert(cmd.index('-Wl,--gc-sections'), str(obj))
    subprocess.run(cmd, check=True)
    subprocess.run([str(executable)], check=True, timeout=10)

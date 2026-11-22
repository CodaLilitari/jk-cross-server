"""Rebuild exactly the native bot and multiplayer GUI from verified relink inputs.

Requires an existing configured Unix Makefiles build and the pinned SDL checkout.
Changes outside these two translation units are rejected. This helper does not
replace the packaged release files or perform a full engine build.
"""
from pathlib import Path
import argparse
import ctypes.util
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import tarfile

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def run(argv, **kwargs):
    return subprocess.run(argv, check=True, **kwargs)

def load(path):
    return json.loads(path.read_text())

def save(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n')

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--source', type=Path, required=True)
p.add_argument('--repo', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--build-dir', type=Path, required=True, help='Configured CMake build containing flags.make and generated/globals.h.')
p.add_argument('--sdl-source', type=Path, required=True, help='Pinned SDL source checkout used by that build.')
opt = p.parse_args()
src, repo, out = (x.resolve() for x in (opt.source, opt.repo, opt.output))
for inp in (src, repo, opt.build_dir.resolve(), opt.sdl_source.resolve()):
    if out == inp or inp in out.parents or out in inp.parents:
        raise ValueError('Output must be outside the source, repository and dependency builds.')
out.mkdir(exist_ok=False, parents=True)
tools_root = opt.build_dir.resolve()
base = load(repo/'native/BOT_BUILD.json')
if run(['git','-C',str(src),'rev-parse','HEAD'],capture_output=True,text=True).stdout.strip() != base['base_commit']:
    raise ValueError('Source commit differs from native build pin.')
archive = repo/'native/bot-relink-linux-x86_64.tar.gz'
if digest(archive) != base['files']['native/bot-relink-linux-x86_64.tar.gz']['sha256']:
    raise ValueError('Native relink archive digest mismatch.')
with tarfile.open(archive) as f:
    f.extractall(out, filter='data')
if not all(digest(out / k)==v for k,v in base['relink_inputs'].items()):
    raise ValueError('Native relink input digest mismatch.')
sdl = opt.sdl_source.resolve()
if run(['git','-C',str(sdl),'rev-parse','HEAD'],capture_output=True,text=True).stdout.strip() != 'f87239e71e42da91ca317a12eefb82cfbf3393eb':
    raise ValueError('SDL source commit differs from pinned build.')
flags_file = tools_root/'CMakeFiles/sith_engine.dir/flags.make'
fields = dict(line.split(' = ',1) for line in flags_file.read_text().splitlines())
args = ['cc', *shlex.split(fields['C_DEFINES']), '-DPLATFORM_CURL','-DPLATFORM_NO_CACERT_BLOB','-D_FORTIFY_SOURCE=3','-fstack-protector-strong','-fstack-clash-protection','-fcf-protection',
        '-I'+str(src/'src'), '-I'+str(tools_root/'generated'), '-I'+str(sdl/'include'),
        *shlex.split(fields['C_FLAGS']), '-DNDEBUG']
compiled, cmdlog, consumed = [], [], set()
for relative in ('src/AI/jkBot.c','src/Gui/jkGUIMultiplayer.c'):
    obj_rel = 'CMakeFiles/sith_engine.dir/'+relative+'.o'
    obj = out / obj_rel
    deps = out/(obj.stem+'.d')
    argv = [*args,'-MMD','-MF',str(deps),'-c',str(src/relative),'-o',str(obj)]
    run(argv)
    cmdlog.append(argv)
    d = shlex.split(deps.read_text().replace('\\\n',' ').split(':',1)[1])
    consumed.update(Path(v).relative_to(src).as_posix() for v in d if Path(v).is_relative_to(src))
    compiled.append({'source':relative,'object':obj_rel,'object_sha256':digest(obj)})
gui = out/compiled[1]['object']
symbols = run(['nm','-S',str(gui)],text=True,capture_output=True).stdout
for part in (' T jkGuiMultiplayer_BotConnect',' U SDL_Delay',' U jkBot_OnJoined',' U sithMulti_SendJoinRequest'):
    if part not in symbols:
        raise ValueError('Missing expected GUI symbol: ' + part)
# Retain canonical -lfoo input in the redistributable recovery receipt.
# Runtime SONAME links in a build-private directory supply missing host development symlinks.
libdir = out/'system-link-names'
libdir.mkdir()
libraries = run(['/sbin/ldconfig','-p'],text=True,capture_output=True).stdout.splitlines()
link = load(out/'link.json')
for v in set(link):
    if not re.fullmatch(r'-l[\w.+-]+', v):
        continue
    soname = ctypes.util.find_library(v[2:])
    if not soname:
        continue
    library = next((row.split(' => ')[1] for row in libraries if row.strip().split(' ')[0] == soname and 'x86-64' in row),None)
    if library:
        (libdir / ('lib'+v[2:]+'.so')).symlink_to(library)
run(link, cwd=out, env=dict(os.environ,LIBRARY_PATH=str(libdir)))
(out/'jk-bot-client-relinked').rename(out/'jk-bot-client')
shutil.copy2(out/'GameNetworkingSockets/lib/libGameNetworkingSockets.so',out/'libGameNetworkingSockets.so')
recorded = set(base['compiled_sources']) | consumed
sources = {k:digest(src/k) for k in sorted(recorded)}
changed = {k:v for k,v in base['compiled_sources'].items() if sources[k]!=v}
if not set(changed).issubset(consumed):
    raise ValueError('Changed non-rebuilt source: ' + str(set(changed)-consumed))
package_provenance = {'native_unmodified':False,'method':'Recompile bot driver and multiplayer GUI from pinned patched source, using verified published objects and static dependencies for remaining units.','compiled_sources':sources,'binary_sha256':digest(out/'jk-bot-client'),'link':link}
save(out/'recovery-build.json',package_provenance)
save(out/'pair-build.json',{'compiler':run(['cc','--version'],text=True,capture_output=True).stdout.splitlines()[0], 'base_commit':base['base_commit'],'sdl_commit':'f87239e71e42da91ca317a12eefb82cfbf3393eb','input_archive_sha256':digest(archive),'source_patch_sha256':digest(repo/'native/bot-client.patch'),'input_prefix_source_changes':changed,'compiled':compiled,'commands':cmdlog,'hashes':{'globals.h':digest(tools_root/'generated/globals.h'),'flags.make':digest(flags_file),'jk-bot-client':digest(out/'jk-bot-client'),'libGameNetworkingSockets.so':digest(out/'libGameNetworkingSockets.so')},'bot_connect_compiled':True,'live_session':False})
print(out/'jk-bot-client')

"""Package native outputs, license notices, and LGPL relinking materials."""
from pathlib import Path
import hashlib, io, json, shlex, shutil, subprocess, sys, tarfile
repo=Path(sys.argv[1]).resolve();build=Path(sys.argv[2]).resolve()
native=Path(__file__).resolve().parent;project=native.parent
runtime=project/'bin/linux-x86_64';runtime.mkdir(parents=True,exist_ok=True)
base='74e4657c4f1751d09af9ad9e056acb8f41997acb'
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()==base
for name in ['openjkdf2','libGameNetworkingSockets.so']:
    shutil.copy2(build/name,runtime/name)
licenses=[
 'LICENSE.md','src/external/libsmacker/COPYING','src/external/libsmusher/LICENSE',
 'src/external/fcaseopen/LICENSE.txt','src/external/nativefiledialog-extended/LICENSE',
 '3rdparty/json/LICENSE.MIT','lib/zlib/LICENSE','lib/libpng/LICENSE',
 'lib/glew/LICENSE.txt','lib/freeglut/COPYING','lib/physfs/LICENSE.txt',
 'lib/GameNetworkingSockets/LICENSE','lib/protobuf/LICENSE',
 'lib/protobuf/third_party/utf8_range/LICENSE','lib/SDL/LICENSE.txt',
 'lib/SDL/src/hidapi/LICENSE.txt','lib/SDL/src/hidapi/LICENSE-bsd.txt',
 'lib/SDL/src/hidapi/LICENSE-orig.txt','lib/SDL/src/video/yuv2rgb/LICENSE',
 'lib/SDL_mixer/LICENSE.txt','lib/SDL_mixer/src/timidity/COPYING',
 'lib/SDL_mixer/src/dr_libs/LICENSE','lib/SDL_mixer/external/ogg/COPYING',
 'lib/SDL_mixer/external/vorbis/COPYING','lib/SDL_mixer/external/opus/COPYING',
 'lib/SDL_mixer/external/opus/LICENSE_PLEASE_READ.txt',
 'lib/SDL_mixer/external/opusfile/COPYING']
for relative in licenses:
    path=project/'licenses/native'/relative;path.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(repo/relative,path)
# Exact linkable application objects plus the statically linked LGPL library
# source let recipients modify libsmacker and relink the application locally.
link=shlex.split((build/'CMakeFiles/openjkdf2.dir/link.txt').read_text());link[0]='c++'
relink=[];archive_paths={}
for arg in link:
    if arg.startswith('-L') or arg.startswith('-Wl,-rpath,'):continue
    if arg=='openjkdf2':relink.append('openjkdf2-relinked');continue
    path=Path(arg)
    if arg.endswith(('.o','.a','.so')) and not path.is_absolute():
        source=build/path;assert source.is_file(),source;archive_paths[arg]=source.resolve()
    relink.append(arg)
rebuild_script='''#!/usr/bin/env python3
"""Recompile bundled libsmacker source and relink supplied application objects."""
from pathlib import Path
import json, subprocess
root=Path(__file__).resolve().parent
for name in ['smacker','smk_bitstream','smk_hufftree']:
    subprocess.run(['cc','-O2','-fshort-wchar','-c',str(root/'libsmacker'/f'{name}.c'),'-o',str(root/'CMakeFiles/sith_engine.dir/src/external/libsmacker'/f'{name}.c.o')],check=True)
subprocess.run(json.loads((root/'link.json').read_text()),cwd=root,check=True)
print(root/'openjkdf2-relinked')
'''
with tarfile.open(native/'relink-linux-x86_64.tar.gz','w:gz') as tar:
    for name,path in sorted(archive_paths.items()):tar.add(path,arcname=name,recursive=False)
    for path in sorted((repo/'src/external/libsmacker').iterdir()):
        if path.is_file():tar.add(path,arcname='libsmacker/'+path.name,recursive=False)
    for name in ['engine_config.h','types_enums.h']:
        tar.add(repo/'src'/name,arcname='libsmacker/'+name,recursive=False)
    tar.add(repo/'LICENSE.md',arcname='libsmacker/ENGINE_LICENSE.md',recursive=False)
    for name,content in [('link.json',json.dumps(relink,indent=2)),('relink.py',rebuild_script)]:
        data=content.encode();info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o755 if name.endswith('.py') else 0o644
        tar.addfile(info,io.BytesIO(data))
manifest={'repository':'https://gitlab.com/codalilitari/OpenJKDF2-MotS-Fixes','base_commit':base,
 'patch':'native/crossplay-dedicated.patch','platform':'Linux x86_64','build_environment':{'distribution':Path('/etc/os-release').read_text(),'compiler':subprocess.check_output(['cc','--version'],text=True).splitlines()[0]},
 'source_pins':subprocess.check_output(['git','submodule','status','--recursive'],cwd=repo,text=True).splitlines(),
 'files':{},'system_libraries':subprocess.check_output(['ldd',str(runtime/'openjkdf2')],text=True).splitlines()}
for path in [runtime/'openjkdf2',runtime/'libGameNetworkingSockets.so',native/'crossplay-dedicated.patch',native/'relink-linux-x86_64.tar.gz']:
    manifest['files'][str(path.relative_to(project))]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}
(native/'BUILD.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps(manifest['files'],indent=2))

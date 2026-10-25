#!/usr/bin/env python3
"""Package optional bot client, corresponding patch and LGPL relink inputs."""
from pathlib import Path
import argparse, hashlib, io, json, shlex, shutil, subprocess, tarfile
BASE='74e4657c4f1751d09af9ad9e056acb8f41997acb'
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('build',type=Path)
 a=p.parse_args();source=a.source.resolve();build=a.build.resolve();native=Path(__file__).resolve().parent;project=native.parent
 if subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()!=BASE:raise SystemExit('Wrong engine base')
 subprocess.run(['git','apply','--reverse','--check',str(native/'bot-client.patch')],cwd=source,check=True)
 recovered=(build/'recovery-build.json').is_file();receipt={}
 if recovered:
  receipt=json.loads((build/'recovery-build.json').read_text())
  if receipt['native_unmodified']:raise SystemExit('Human fixture is not a bot')
  for name,sha in receipt['compiled_sources'].items():
   if digest(source/name)!=sha:raise SystemExit('Source changed since compilation: '+name)
  binary=build/'jk-bot-client'
  if digest(binary)!=receipt['binary_sha256']:raise SystemExit('Binary changed since compilation')
  link=receipt['link'];method=receipt['method']
 else:
  binary=build/'openjkdf2';link=shlex.split((build/'CMakeFiles/openjkdf2.dir/link.txt').read_text())
  method='Complete CMake build from pinned engine source with bot-client.patch only.'
 runtime=project/'bin/bots-linux-x86_64';runtime.mkdir(parents=True,exist_ok=True)
 for src,name in [(binary,'jk-bot-client'),(build/'libGameNetworkingSockets.so','libGameNetworkingSockets.so')]:
  temporary=runtime/(name+'.new');shutil.copy2(src,temporary);temporary.replace(runtime/name)
 relink=[];members={};output=False
 for i,arg in enumerate(link):
  if i==0:relink.append('c++');continue
  if arg.startswith('-L') or arg.startswith('-Wl,-rpath,'):continue
  if output:relink.append('jk-bot-client-relinked');output=False;continue
  if arg=='-o':relink.append(arg);output=True;continue
  path=Path(arg)
  if arg.endswith(('.o','.a','.so')):
   original=path if path.is_absolute() else build/path
   if not original.is_file():raise SystemExit('Missing link input: '+str(original))
   if path.is_absolute():
    if path.name=='libGLEW.a':arg='system-static/libGLEW.a';members[arg]=original
    elif path.name=='libopenal.so':arg='-lopenal'
    else:raise SystemExit('Unclassified absolute link input: '+str(path))
   else:members[arg]=original
  relink.append(arg)
 relink.append('-Wl,-rpath,$ORIGIN')
 rebuild='''#!/usr/bin/env python3
"""Modify libsmacker then relink the supplied bot application objects."""
from pathlib import Path
import json,subprocess
root=Path(__file__).resolve().parent
for name in ['smacker','smk_bitstream','smk_hufftree']:
 subprocess.run(['cc','-O2','-fshort-wchar','-c',str(root/'libsmacker'/f'{name}.c'),'-o',str(root/'CMakeFiles/sith_engine.dir/src/external/libsmacker'/f'{name}.c.o')],check=True)
subprocess.run(json.loads((root/'link.json').read_text()),cwd=root,check=True)
print(root/'jk-bot-client-relinked')
'''
 archive=native/'bot-relink-linux-x86_64.tar.gz'
 with tarfile.open(archive,'w:gz') as tar:
  for name,path in sorted(members.items()):tar.add(path,arcname=name,recursive=False)
  for path in sorted((source/'src/external/libsmacker').iterdir()):
   if path.is_file():tar.add(path,arcname='libsmacker/'+path.name,recursive=False)
  for name in ['engine_config.h','types_enums.h']:tar.add(source/'src'/name,arcname='libsmacker/'+name,recursive=False)
  tar.add(source/'LICENSE.md',arcname='libsmacker/ENGINE_LICENSE.md',recursive=False)
  for name,value in [('link.json',json.dumps(relink,indent=2)+'\n'),('relink.py',rebuild)]:
   data=value.encode();info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o755 if name.endswith('.py') else 0o644;tar.addfile(info,io.BytesIO(data))
 seed=json.loads((native/'BUILD.json').read_text())
 manifest={'repository':seed['repository'],'base_commit':BASE,'patch':'native/bot-client.patch',
  'platform':'Linux x86_64','reconstructed_after_scratch_reset':True,'method':method,
  'compiler':subprocess.check_output(['cc','--version'],text=True).splitlines()[0],
  'distribution':Path('/etc/os-release').read_text(),'source_pins':seed['source_pins'],
  'compiled_sources':receipt.get('compiled_sources',{}),'files':{},
  'relink_inputs':{k:digest(v) for k,v in sorted(members.items())},'game_assets_included':False,'server_modified':False}
 for path in [runtime/'jk-bot-client',runtime/'libGameNetworkingSockets.so',native/'bot-client.patch',archive]:
  manifest['files'][str(path.relative_to(project))]={'sha256':digest(path),'bytes':path.stat().st_size}
 (native/'BOT_BUILD.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest['files'],indent=2))
if __name__=='__main__':main()

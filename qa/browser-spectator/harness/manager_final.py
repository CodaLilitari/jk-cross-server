import datetime,hashlib,json,os,sys,time,unittest
from pathlib import Path
repo=Path('/workspace/scratch/55e850edc256/jk-browser-spectator')
out=Path(__file__).parent
os.chdir(repo);sys.path.insert(0,str(repo));os.environ['PYTHONDONTWRITEBYTECODE']='1'
suite=unittest.defaultTestLoader.discover('tests',pattern='test*.py')
expected=suite.countTestCases();started=datetime.datetime.now(datetime.timezone.utc).isoformat();begin=time.monotonic()
files=[p for d in ('manager','web_gateway','tests') for p in (repo/d).rglob('*') if p.is_file() and p.suffix in ('.py','.js','.html','.css','.jksg')]
hashes={str(p.relative_to(repo)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
with (out/'manager-final.log').open('w') as stream:
 result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
changes=[n for n,h in hashes.items() if hashlib.sha256((repo/n).read_bytes()).hexdigest()!=h]
receipt={'started_utc':started,'finished_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'elapsed_seconds':round(time.monotonic()-begin,3),'command':[sys.executable,str(Path(__file__).resolve())],'expected_cases':expected,'tests_run':result.testsRun,'failures':[{'test':str(t),'traceback':s} for t,s in result.failures],'errors':[{'test':str(t),'traceback':s} for t,s in result.errors],'skipped':[{'test':str(t),'reason':s} for t,s in result.skipped],'successful':result.wasSuccessful() and result.testsRun==expected and not changes,'source_sha256':hashes,'source_changed_during_verification':changes,'log_sha256':hashlib.sha256((out/'manager-final.log').read_bytes()).hexdigest()}
(out/'manager-final.json').write_text(json.dumps(receipt,indent=2)+'\n')
# Direct file descriptor avoids any leaked sys.stdout/stderr redirection in a fixture.
os.write(1,(json.dumps({k:v for k,v in receipt.items() if k not in ('source_sha256','failures','errors')})+'\n').encode())
raise SystemExit(0 if receipt['successful'] else 1)

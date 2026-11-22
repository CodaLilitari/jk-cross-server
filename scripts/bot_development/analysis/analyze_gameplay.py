"""Summarize clip-bounded gameplay, equipment choices, and horizontal confinement."""
import argparse
import collections
import gzip
import hashlib
import json
import math
import re
from pathlib import Path

from analyze_speedvideo import unique_fresh
from analyze_trial import sectors_from_numeric, contains


def analyze(path, geom, verbose=False):
    data = json.loads(gzip.decompress(path.read_bytes()))
    result = data['result']
    qual = data['qualification']
    a=result['recording_start_trace_seconds']; b=result['recording_return_trace_seconds']; end=a+result['capture']['duration_seconds']; mid=(a+b)/2
    console_offset=qual['console_clock_origin_monotonic']-(qual['recording_start_monotonic']-a)
    report={'build':result['build'],'input_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'clip_window':[b,end],'console_offset_to_trace_seconds':console_offset,'rows':{},'directed_count':len(data['directed_commands'])}
    R=lambda x:round(x,3)
    def spans(rows,key):
     episodes=[];prev=None
     for row in rows:
      k=key(row)
      if prev is None or not row['connected'] or k!=episodes[-1]['value']:
       episodes.append({'value':k,'life':row['life'],'start':row['t'],'end':row['t'],'n':0})
      episodes[-1]['end']=row['t'];episodes[-1]['n']+=1
      prev=row
     for e in episodes: e['span']=R(e['end']-e['start'])
     return episodes
    for name,obs in data['observations'].items():
     states=list(unique_fresh(obs)); clipped=[o for o in states if b<=o['wall_seconds']<=end]
     rows=[];prev=None;stalls=[];anchor=None;ammogains=[];gear=[];fire=[];status=[];warmfire=[];previousammo=None
     for o in clipped:
      s=o['state'];t=R(o['wall_seconds']-mid);p=s['position'];life=(o['world_epoch'],o['life_epoch']);alive=s['health']>0;game=s['game_time']
      m=[sector for sector in geom if contains(p,sector)]
      wet=any(sector[1]&2 for sector in m); dry=any(not sector[1]&2 for sector in m)
      env='ambiguous' if wet and dry else 'wet' if wet else 'dry' if dry else 'unmapped'
      connected=prev and prev['life']==life and t-prev['t']<=.8 and 0<game-prev['game']<=1.0
      if not alive or not connected or anchor and math.dist(anchor['position'],p[:2])>.13:
       if anchor and prev['t']-anchor['t']>=2:
        stalls.append({'t':anchor['t'],'span':R(prev['t']-anchor['t']),'life':prev['life'],'sectors':sorted(anchor['sectors'])})
       anchor=None
      if alive:
       if anchor is None:anchor={'t':t,'position':p[:2],'sectors':set()}
       anchor['sectors'].update([sec[0] for sec in m])
      if alive and connected and prev['alive']:
       delta={k:R(v-previousammo[k]) for k,v in s['ammo'].items() if v>previousammo[k]}
       if delta:ammogains.append({'t':t,'life':life,'delta':delta,'weapon':s['weapon']})
      previousammo=s['ammo']
      row={'t':t,'game':game,'life':life,'alive':alive,'weapon':s['weapon'],'env':env,'connected':bool(connected),'target':s['target'] is not None,'mode':s['mode'],'ammo':s['ammo'],'position':p}
      rows.append(row);prev=row
     if anchor and prev['t']-anchor['t']>=2:stalls.append({'t':anchor['t'],'span':R(prev['t']-anchor['t']),'life':prev['life'],'sectors':sorted(anchor['sectors'])})
     for ct,_,msg in qual['console'][name]:
      trace_t=ct+console_offset;t=R(trace_t-mid);event={'t':t,**dict(re.findall(r'(\w+)=(\S+)',msg))};event['game']=event.get('t');event['t']=t
      if not b<=trace_t<=end:
       if trace_t<b and 'BOT_FIRE_INPUT' in msg:warmfire.append(event)
       continue
      if 'BOT_GEAR' in msg:gear.append(event)
      if 'BOT_FIRE_INPUT' in msg:fire.append(event)
      if 'BOT_STATUS' in msg:status.append(event)
     lives=collections.Counter(str(row['life']) for row in rows if row['alive']); live=[row for row in rows if row['alive']]
     weps=collections.Counter(row['weapon'] for row in live);env=collections.Counter(row['env'] for row in live)
     ds=[o['state'] for o in [clipped[0],clipped[-1]]]
     scored={'from':[ds[0]['kills'],ds[0]['deaths']],'to':[ds[1]['kills'],ds[1]['deaths']]}
     envspan=spans(rows,lambda row:row['env'] if row['alive'] else 'dead')
     wepspan=spans(rows,lambda row:row['weapon'] if row['alive'] else 'dead')
     moved=sum(math.dist(x['position'],y['position']) for x,y in zip(rows,rows[1:]) if y['connected'] and x['alive'] and y['alive'])
     target_alive=sum(o['target'] for o in live)
     report['rows'][name]={'n':len(rows),'fresh_living_states':len(live),'living_with_target':target_alive,'lives':lives,'living_weapons':dict(weps),'living_environment':dict(env),'sampled_same_life_travel_units':R(moved),'score':scored,'environment_spans':envspan,'weapon_spans':wepspan,'candidate_stalls':stalls,'ammo_increases':ammogains,'equipment_log':gear,'fire_input_changes':fire,'status':status,'warmup_fire_input_changes':warmfire,'modes':dict(collections.Counter(row['mode'] for row in live))}
     if verbose:
      print(name,len(rows),len(live),weps,env,lives,target_alive,scored,'moved',round(moved,1))
      print('stalls',len(stalls),sum(s['span'] for s in stalls), sorted(stalls,key=lambda r:-r['span'])[:4]);print('wet long',[(e['start'],e['end'],e['value']) for e in envspan if e['value']!='dead' and e['span']>=7])
      print('gun long',[(e['start'],e['end'],e['value']) for e in wepspan if e['span']>=5])
      print('fire',collections.Counter((r['weapon'],r['alternate']) for r in fire),'warmup',collections.Counter((r['weapon'],r['alternate']) for r in warmfire))
      print('gear',collections.Counter(r.get('reason','plan') for r in gear),'pack-plans',[(r['t'],r['item']) for r in gear if r.get('pack')=='1'],'air',[(r['t'],r.get('item'),r.get('reason')) for r in gear if 'air' in r.get('reason','') or 'return' in r.get('reason','')]);print('ammo',collections.Counter(k for event in ammogains for k in event['delta']))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace', type=Path, help='Exported gzip JSON trial wrapper')
    parser.add_argument('output', type=Path)
    parser.add_argument('--map', type=Path, required=True, help='Numeric export of your owned JKL')
    parser.add_argument('--verbose', action='store_true', help='Also print the original human summary')
    args = parser.parse_args()
    report = analyze(args.trace, sectors_from_numeric(args.map), args.verbose)
    args.output.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8')

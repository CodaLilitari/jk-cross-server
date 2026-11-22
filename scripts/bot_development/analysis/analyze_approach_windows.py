"""Inspect post-failure observations; these do not prove floor support or effective attacks."""
import argparse
from collections import Counter
import json
import gzip
import math
from pathlib import Path
from analyze_speedvideo import unique_fresh
from analyze_trial import sectors_from_numeric, contains


def numeric_items(mapfile):
    rows = mapfile.read_text().splitlines()
    # The final exact-count block is the exported map's entity list.
    index = next(i for i in range(len(rows) - 1, 0, -1)
                 if rows[i].isdigit() and int(rows[i]) == len(rows) - i - 1)
    return [row.split() for row in rows[index + 1:]]


def analyze(trace, detail, geometry, items):
    d=json.loads(gzip.decompress(trace.read_bytes())); res=d['result']; a=res['recording_start_trace_seconds'];b=res['recording_return_trace_seconds'];mid=(a+b)/2; end=a+res['capture']['duration_seconds']; detail=json.loads(detail.read_text())
    out={}
    for seat,obs in d['observations'].items():
        samples=[]
        for o in unique_fresh(obs):
            if not b<=o['wall_seconds']<=end:continue
            s=o['state']; secs=tuple(g[0] for g in geometry if contains(s['position'],g))
            samples.append({'t':round(o['wall_seconds']-mid,3),'game':s['game_time'],'life':[o['world_epoch'],o['life_epoch']],'sectors':secs,'pos':s['position'],'health':s['health'],'shields':s['shields'],'ammo':s['ammo'],'weapon':s['weapon'],'target':s['target'] is not None})
        info=detail['rows'][seat]; log=info['equipment_log']; windows=[]
        for event in [e for e in log if e['event']=='failed-approach']:
            failure=float(event['game']);deadline=float(event['retry']);bank=int(event['bank']);wet=int(event['water'])
            ref=min(samples,key=lambda r:abs(r['game']-failure))
            window=[r for r in samples if failure<=r['game']<deadline and r['life']==ref['life'] and r['health']>0]
            if not window:continue
            post=next((i for i,row in enumerate(window) if row['sectors']==(bank,)),None)
            after=window[post:] if post is not None else []
            edges=[]; prior_bank=None;on_wet=False
            for i,row in enumerate(after):
                if i and (row['t']-after[i-1]['t']>.8 or row['game']-after[i-1]['game']>1):prior_bank=None;on_wet=False
                if row['sectors']==(bank,):
                    prior_bank=row;on_wet=False
                if row['sectors']==(wet,) and prior_bank and not on_wet:
                    if row['t']-prior_bank['t']<=1.2:
                        # Latest plan/clear are separate; selection can persist or be cleared.
                        past=[e for e in log if e['event'] in ('plan','clear') and e['t']<=row['t']]
                        last=past[-1] if past else None;lastplan=last if last and last['event']=='plan' else None
                        item=int(lastplan['item']) if lastplan else -1
                        ident={'slot':item,'template':items[item][-1],'sector':int(items[item][1])} if lastplan and lastplan.get('pack')=='0' and 0<=item<len(items) else None
                        edges.append({'last_pure_bank':prior_bank,'first_pure_wet':row,'last_gear_event':last,'map_item':ident,'secs_since_failure':round(row['game']-failure,3)})
                    on_wet=True
            summary={}
            if after:
                summary={'first_bank_after_failure':after[0],'max_horizontal_distance_from_first_bank':round(max(math.dist(after[0]['pos'][:2],r['pos'][:2]) for r in after),3),'pure_sector_counts':dict(Counter(str(r['sectors']) for r in after)),'target_states_after_first_bank':sum(r['target'] for r in after),'fresh_living_states_after_first_bank':len(after),'new_entries':edges}
            last=window[-1]; entry_gear=[g for g in log if event['t']<=g['t']<=last['t'] and g['event'] in ('plan','clear')]
            fires=[e for e in info['fire_input_changes'] if event['t']<=e['t']<=last['t']]
            increases=[e for e in info['ammo_increases'] if event['t']<=e['t']<=last['t']]
            windows.append({'failure':event,'life':ref['life'],'window_end':last['t'],'sample_horizon_game_s':round(last['game']-failure,3),'states_at_failure':ref,'returned_bank_summary':summary,'gear_in_window':entry_gear,'fire_changes':fires,'ammo_increases':increases})
        out[seat]=windows
    return {'build':res['build'],'seats':out}
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace', type=Path)
    parser.add_argument('detail', type=Path, help='Matching analyze_gameplay.py report')
    parser.add_argument('--map', type=Path, required=True, help='Numeric export of your owned JKL')
    args = parser.parse_args()
    print(json.dumps(analyze(args.trace, args.detail, sectors_from_numeric(args.map),
                             numeric_items(args.map)), indent=2))

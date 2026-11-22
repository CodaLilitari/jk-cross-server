"""Add sampled health, equipment and approach context to prolonged sector visits."""
import argparse
import collections
import gzip
import json
from pathlib import Path
from analyze_speedvideo import unique_fresh
from analyze_trial import sectors_from_numeric, contains


def analyze(trace, detail, columns, geometry, seats, column=54, bank=41):
    data = json.loads(gzip.decompress(trace.read_bytes()))
    res = data['result']
    mid = (res['recording_start_trace_seconds'] + res['recording_return_trace_seconds']) / 2
    candidates = [item for item in json.loads(columns.read_text()) if item['label'] == res['label']]
    if len(candidates) != 1:
        raise ValueError('Expected one column summary matching this trial label')
    spans = candidates[0]['seats']
    states = json.loads(detail.read_text())['rows']
    out={}
    for who in seats:
        rs=[]
        for o in unique_fresh(data['observations'][who]):
            t=round(o['wall_seconds']-mid,3);s=o['state'];p=s['position']
            sectors=tuple(j[0] for j in geometry if contains(p,j))
            rs.append(dict(t=t,life=[o['world_epoch'],o['life_epoch']],alive=s['health']>0,pos=p,sectors=sectors,state=s))
        episodes=[]
        for e in spans[who][f'pure_sector{column}_extended_spans']:
            selected=[r for r in rs if e['start']<=r['t']<=e['end']]
            first=selected[0]; stateset=[r['state'] for r in selected]
            prior=[r for r in rs if r['alive'] and r['life']==e['life'] and r['t']<e['start']]
            prior41=next((r for r in reversed(prior) if r['sectors']==(bank,)),None)
            recentstatus=[s for s in states[who]['status'] if s['t']<e['start'] and s['sector']==str(bank)]
            gears=[g for g in states[who]['equipment_log'] if g['t']<e['start'] and g['event']=='plan']
            fails=[g for g in states[who]['equipment_log'] if g['t']<e['start'] and g['event']=='failed-approach']
            def lite(r):
                return {k:r[k] for k in ('t','pos','sectors','life')} if r else None
            episodes.append({**e,"samples":len(selected),"hp_range":[min(s['health'] for s in stateset),max(s['health'] for s in stateset)],"shield_range":[min(s['shields'] for s in stateset),max(s['shields'] for s in stateset)],"power_values":sorted({s['ammo']['power'] for s in stateset}),"rail_values":sorted({s['ammo']['rail'] for s in stateset}),"selected_weapon_bins":dict(collections.Counter(s['weapon'] for s in stateset)),"states_with_target":sum(s['target'] is not None for s in stateset),"first_living_sample_seen_this_life":lite(prior[0] if prior else first),f"last_mapped_{bank}":lite(prior41),"last_mapped_before_entry":lite(prior[-1] if prior else None),f"most_recent_clip_native_sector{bank}_status":recentstatus[-1] if recentstatus else None,"last_plan_before_entry":gears[-1] if gears else None,"most_recent_failed_approach":fails[-1] if fails else None})
        out[who]=episodes
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace', type=Path)
    parser.add_argument('detail', type=Path, help='Matching analyze_gameplay.py report')
    parser.add_argument('columns', type=Path, help='review_column.py JSON containing this trial label')
    parser.add_argument('output', type=Path)
    parser.add_argument('--map', type=Path, required=True, help='Numeric export of your owned JKL')
    parser.add_argument('--seat', action='append', required=True, help='Seat to inspect; repeat as needed')
    parser.add_argument('--sector', type=int, default=54)
    parser.add_argument('--bank', type=int, default=41)
    args = parser.parse_args()
    result = analyze(args.trace, args.detail, args.columns, sectors_from_numeric(args.map),
                     args.seat, args.sector, args.bank)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')

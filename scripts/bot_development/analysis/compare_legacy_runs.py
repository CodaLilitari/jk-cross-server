"""Preserved first-120-second comparison used by early trials; see README limits."""
import argparse
from pathlib import Path
import gzip
import hashlib
import json
import math
import sys


def load(path):
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == '.gz' else raw)


def analyse(path):
    data = load(path)
    fresh = {
        name: [o for o in rows if o['native_active'] and o['age_seconds'] <= 1]
        for name, rows in data['observations'].items()
    }
    start = max(rows[0]['wall_seconds'] for rows in fresh.values())
    end = start + 120
    result = {'build': data.get('result', {}).get('build'),
              'wasm_sha256': data.get('result', {}).get('shipped_wasm_sha256'),
              'private_input_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'qualified': data['qualification']['qualified'],
              'window_seconds': 120,
              'bots': {}}
    for name, rows in fresh.items():
        rows = [o for o in rows if start <= o['wall_seconds'] <= end]
        episodes = []
        anchor = None
        first = last = None
        weapons = set()
        pull_edges = 0
        previous_pull = False

        def finish():
            if first is not None and last-first >= 2:
                episodes.append({'start': round(first-start, 3),
                                 'duration': round(last-first, 3)})

        for o in rows:
            t = o['wall_seconds']
            s = o['state']
            pull = bool(s['force_mask'] & 8)
            if pull and not previous_pull:
                pull_edges += 1
            previous_pull = pull
            if s['health'] <= 0:
                finish()
                anchor = None
                first = last = None
                continue
            weapons.add(s['weapon'])
            position = s['position'][:2]
            if anchor is None or t-last > .8 or math.dist(anchor, position) > .13:
                finish()
                anchor, first = position, t
            last = t
        finish()
        result['bots'][name] = {
            'fresh_samples': len(rows),
            'sample_span_seconds': round(rows[-1]['wall_seconds']-rows[0]['wall_seconds'], 3),
            'candidate_stall_seconds': round(sum(e['duration'] for e in episodes), 3),
            'longest_candidate_stall_seconds': max((e['duration'] for e in episodes), default=0),
            'candidate_stalls': episodes,
            'observed_pull_activation_edges': pull_edges,
            'selected_weapon_bins_alive': sorted(weapons),
            'final_score': {k: rows[-1]['state'][k] for k in ('kills', 'deaths')},
        }
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('traces', nargs='+', type=Path)
    args = parser.parse_args()
    output = {'method': 'First 120 seconds after all four seats publish fresh native observations. Alive samples within 0.13 horizontal map units of an anchor for at least 2 seconds are candidate stalls; gaps over 0.8 seconds reset the anchor. These samples do not distinguish all intentional pauses, Grip immobility, or bad routes. The two matches are unseeded and do not establish human competitive strength. Pull edges are sampled activation transitions, not a count of successful disarms.',
              'runs': [analyse(p) for p in args.traces]}
    print(json.dumps(output, indent=2))

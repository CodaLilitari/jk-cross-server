"""Analyze observed wet episodes using a caller-supplied numeric map export."""
from pathlib import Path
import argparse
import gzip
import json
import re


def sectors_from_numeric(path):
    rows = iter(path.read_text().splitlines())
    vertices = [list(map(float, next(rows).split())) for _ in range(int(next(rows)))]
    for _ in range(int(next(rows))):
        next(rows)
    faces = []
    for _ in range(int(next(rows))):
        row = next(rows).split()
        count = int(row[2])
        faces.append((vertices[int(row[3])], list(map(float, row[3 + count:]))))
    sectors = []
    for ident in range(int(next(rows))):
        row = next(rows).split()
        first, count = map(int, row[-2:])
        sectors.append((ident, int(row[0]), list(map(float, row[1:7])), faces[first:first + count]))
    return sectors


def contains(position, sector):
    _, _, bounds, faces = sector
    return all(bounds[i] - .001 <= position[i] <= bounds[i + 3] + .001 for i in range(3)) and all(
        sum((position[i] - vertex[i]) * normal[i] for i in range(3)) >= -.001
        for vertex, normal in faces
    )


def analyze(path, geometry):
    raw = path.read_bytes()
    data = json.loads(gzip.decompress(raw) if path.suffix == '.gz' else raw)
    result = {'build': data.get('result', {}).get('build'), 'bots': {}}
    for name, rows in data['observations'].items():
        fresh = [row for row in rows if row['native_active'] and row['age_seconds'] <= 1]
        episodes, episode = [], None
        for row in fresh:
            state = row['state']
            sectors = [sector for sector in geometry if contains(state['position'], sector)]
            wet = [sector[0] for sector in sectors if sector[1] & 2]
            t = state['game_time']
            if episode is not None and (not wet or state['health'] <= 0 or row['life_epoch'] != episode['life'] or t - episode['last'] > 1):
                episode['next_sample'] = {'game_time': t, 'position': state['position'], 'health': state['health'],
                                          'sectors': [sector[0] for sector in sectors], 'life': row['life_epoch']}
                episode['sectors'] = sorted(episode['sectors'])
                episodes.append(episode)
                episode = None
            if wet and state['health'] > 0:
                if episode is None:
                    episode = {'start': t, 'life': row['life_epoch'], 'start_hp': state['health'], 'minimum_hp': state['health'], 'sectors': set(), 'samples': 0}
                episode.update(last=t, minimum_hp=min(episode['minimum_hp'], state['health']))
                episode['sectors'].update(wet)
                episode['samples'] += 1
        if episode:
            episode['sectors'] = sorted(episode['sectors'])
            episodes.append(episode)
        console = data['qualification']['console'][name]
        jumps = [row for row in console if 'BOT_FORCE_INPUT ' in row[2] and 'bin=21 ' in row[2]]
        result['bots'][name] = {'fresh_samples': len(fresh),
            'seeing_active_samples': sum(bool(row['state']['force_mask'] & 4) for row in fresh),
            'jump_active_samples': sum(bool(row['state']['force_mask'] & 1) for row in fresh),
            'jump_requests': jumps, 'wet_position_episodes': episodes}
    result['limits'] = 'Sector membership inferred from sampled center positions, not live physics flags or floor attachment. Missing samples, combat, breath state and transitions prevent classifying every death or proving a supported landing from this output alone.'
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace', type=Path)
    parser.add_argument('--map', type=Path, required=True, help='Numeric export of your owned JKL')
    args = parser.parse_args()
    geometry = sectors_from_numeric(args.map)
    print(json.dumps(analyze(args.trace, geometry), indent=2))

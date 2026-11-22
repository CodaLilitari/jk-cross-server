"""Export an owned JKL into the numeric geometry format used by the diagnostics."""
import argparse
import importlib.util
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('jkl', type=Path, help='Your extracted map JKL')
    parser.add_argument('output', type=Path, help='Keep this generated geometry outside the repository')
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[3]
    source = repo / 'native/tests/stock_water_replay/geometry.py'
    spec = importlib.util.spec_from_file_location('bot_replay_geometry', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.write_geometry(args.jkl, args.output)


if __name__ == '__main__':
    main()

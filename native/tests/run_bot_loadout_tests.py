#!/usr/bin/env python3
"""Check legal saved JK characters without engine libraries or game assets."""
from pathlib import Path
import argparse
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--cc", default="cc")
    args = parser.parse_args()
    source = args.source.resolve()
    if not (source / "src/AI/jkBotLoadout.h").is_file():
        parser.error("Apply native/bot-client.patch to the pinned engine first.")
    with tempfile.TemporaryDirectory(prefix="jk-bot-loadout-") as directory:
        binary = Path(directory) / "test_bot_loadout"
        subprocess.run([args.cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
                        "-I" + str(source / "src"),
                        str(Path(__file__).with_name("test_bot_loadout.c")),
                        "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    main()

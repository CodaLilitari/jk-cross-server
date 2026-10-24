#!/usr/bin/env python3
"""Prepare a dedicated Wine prefix from the user's original DirectPlay 5 files.

No game files or runtime binaries are downloaded. Existing unrelated prefixes
are refused. The generated launcher starts the original DPLAYSVR helper before
the gateway, then cleans up the helper process it started when the gateway exits.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

FILES = {
    "dplay.dll": "7f3978149dd401c33ab0cf34bf776d794005dccf8307cce5006710976c6df545",
    "dplayx.dll": "d31af8884552fd839661df03b16c0205d35ecdc610e278c2c12c616f28f38924",
    "dpwsockx.dll": "35ab9668eb501642bb2551a22dbd84a76f97d24a7fcc5ff8b8806af5fb52cd17",
    "dplaysvr.exe": "836862ad78fb9a0eaf6c91aa85890abf92257e256533e55ec7088c7820f3b357",
}
MARKER = "jk-cross-server-runtime.json"


def media_files(directory: Path) -> dict[str, Path]:
    found = {}
    for name, digest in FILES.items():
        matches = [p for p in directory.iterdir() if p.name.casefold() == name]
        if len(matches) != 1 or not matches[0].is_file():
            raise ValueError(f"Expected exactly one {name} in {directory}")
        path = matches[0]
        with path.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != digest:
            raise ValueError(f"{path.name} differs from the qualified DirectPlay 5 runtime. Use a manually prepared prefix for another runtime version.")
        found[name] = path
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directx", type=Path, required=True, help="Original disc DIRECTX directory with the four qualified files")
    parser.add_argument("--prefix", type=Path, required=True, help="New dedicated Wine prefix")
    parser.add_argument("--wine", default="wine", help="32-bit-capable Wine executable or launcher")
    parser.add_argument("--base-prefix", type=Path, help="Optional clean, initialized win32 prefix for portable Wine workflows")
    parser.add_argument("--check-only", action="store_true", help="Verify media and print the plan without changing a prefix")
    args = parser.parse_args()
    prefix = args.prefix.expanduser().resolve()
    wine = shutil.which(args.wine)
    if not wine:
        raise ValueError("Wine executable/launcher was not found; pass --wine with its full path.")
    wine = os.path.abspath(wine)
    sources = media_files(args.directx.expanduser().resolve())
    probe = Path(__file__).with_name("wait_helper.exe")
    if not probe.is_file():
        raise ValueError("Build directplay/wait_helper.exe with make before preparing Wine.")
    manifest = {"format": 1, "runtime": "original DirectPlay 5, qualified hashes", "prefix": str(prefix),
                "wine": wine, "files": FILES, "launcher": str(prefix / "wine-dplay"), "stage": "planned"}
    base = args.base_prefix.expanduser().resolve() if args.base_prefix else None
    if base:
        registry_text = (base / "system.reg").read_text(encoding="utf-8")
        if "#arch=win32" not in registry_text or prefix == base or prefix.is_relative_to(base):
            raise ValueError("Use a clean initialized win32 base prefix and a separate destination.")
        manifest["base_prefix"] = str(base)
    if args.check_only:
        print(json.dumps(manifest, indent=2))
        return 0
    marker = prefix / MARKER
    if prefix.exists() and any(prefix.iterdir()) and not marker.is_file():
        raise ValueError("Choose a new dedicated prefix. This helper will not change an unrelated existing Wine prefix.")
    if base and not marker.is_file():
        if prefix.exists():
            prefix.rmdir()  # Only an empty destination can reach this branch.
        shutil.copytree(base, prefix, symlinks=True)
    elif base and json.loads(marker.read_text()).get("base_prefix") != str(base):
        raise ValueError("This prefix was prepared from a different base; choose a new destination.")
    prefix.mkdir(parents=True, mode=0o700, exist_ok=True)
    if base:
        drives = prefix / "dosdevices"
        drives.mkdir(exist_ok=True)
        drive_c = drives / "c:"
        if drive_c.is_symlink():
            drive_c.unlink()
        elif drive_c.exists():
            raise ValueError("The cloned prefix has an unexpected non-symlink C: drive.")
        drive_c.symlink_to("../drive_c")
    marker.write_text(json.dumps(manifest, indent=2) + "\n")
    target = prefix / "drive_c/windows/system32"
    env = os.environ.copy()
    env.update(WINEPREFIX=str(prefix), WINEARCH="win32", WINEDLLOVERRIDES="mscoree,mshtml=")
    env.setdefault("WINEDEBUG", "-all")
    if not base:
        subprocess.run([wine, "wineboot", "--init"], env=env, check=True, timeout=120)
    if not target.is_dir():
        raise ValueError("Wine did not create the expected 32-bit system directory.")
    for name, source in sources.items():
        temporary = target / (name + ".jk-cross-copy")
        shutil.copy2(source, temporary)
        # Replace a Wine builtin symlink itself, never overwrite its target.
        temporary.replace(target / name)
    registry = Path(__file__).with_name("directplay5.reg").resolve()
    subprocess.run([wine, "regedit", "/S", str(registry)], env=env, check=True, timeout=60)
    launcher = prefix / "wine-dplay"
    shutil.copy2(probe, prefix / "wait_helper.exe")
    body = Path(__file__).with_name("wine_launcher.py.in").read_text(encoding="utf-8")
    launcher.write_text(f"#!/usr/bin/env python3\nWINE = {wine!r}\nPREFIX = {str(prefix)!r}\n" + body, encoding="utf-8")
    launcher.chmod(0o700)
    manifest["stage"] = "prepared"
    marker.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))
    print("Set the panel's Wine executable to the generated launcher and Wine prefix to this prefix.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f"DirectPlay setup failed: {exc}", file=sys.stderr)
        raise SystemExit(1)

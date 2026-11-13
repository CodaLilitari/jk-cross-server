#!/usr/bin/env python3
"""Build platform downloads from a verified updater ZIP without inspecting Git.

Every platform contains the complete, byte-identical updater payload plus a
platform entry README. Input members are validated in memory, never extracted.
Use an output directory outside any source checkout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import tempfile
import zipfile


ARCHIVE_ROOT = "jk-cross-server/"
FIXED_DATE = (1980, 1, 1, 0, 0, 0)
MAX_BYTES = 512 * 1024 * 1024
MAX_FILES = 10_000
EXECUTABLES = {"start-server.sh", "Start-Server.command", "bin/linux-x86_64/openjkdf2",
               "bin/bots-linux-x86_64/jk-bot-client"}
REQUIRED = EXECUTABLES | {
    "VERSION", "app.py", "LICENSE", "NOTICE.md", "release-manifest.json", "SHA256SUMS",
    "bin/linux-x86_64/libGameNetworkingSockets.so",
    "bin/bots-linux-x86_64/libGameNetworkingSockets.so",
    "Start-Server.ps1", "packaging/Dockerfile", "packaging/compose.yaml",
    "packaging/container_runtime.py", ".dockerignore", "docs/PLATFORMS.md",
    "web_gateway/requirements-lock.txt",
}
VERSION_RE = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?")
WINDOWS_DEVICES = {"con", "prn", "aux", "nul", "conin$", "conout$"} | {
    prefix + suffix for prefix in ("com", "lpt") for suffix in "123456789¹²³"
}


class PlatformReleaseError(ValueError):
    """An input or destination cannot safely produce the declared release."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_payload(source: Path) -> tuple[str, dict[str, tuple[bytes, int]]]:
    files = {}
    seen = set()
    total = 0
    with zipfile.ZipFile(source) as archive:
        members = archive.infolist()
        if len(members) > MAX_FILES:
            raise PlatformReleaseError("Input exceeds the file-count limit.")
        for member in members:
            name = member.filename
            parts = name.split("/")
            if (not name.startswith(ARCHIVE_ROOT) or "\\" in name or ":" in name
                    or any(part in ("", ".", "..") for part in parts)
                    or any(part.endswith((".", " ")) or part.split(".")[0].casefold() in WINDOWS_DEVICES
                           for part in parts)
                    or any(char in '<>"|?*' for char in name)
                    or any(ord(char) < 32 or ord(char) == 127 for char in name)):
                raise PlatformReleaseError(f"Unsafe archive path: {name!r}")
            relative = name[len(ARCHIVE_ROOT):]
            if relative.casefold() in seen:
                raise PlatformReleaseError(f"Duplicate or case-colliding path: {name}")
            seen.add(relative.casefold())
            mode = member.external_attr >> 16
            if not stat.S_ISREG(mode) or stat.S_IMODE(mode) not in (0o644, 0o755):
                raise PlatformReleaseError(f"Expected a regular 0644/0755 file: {name}")
            total += member.file_size
            if total > MAX_BYTES:
                raise PlatformReleaseError("Input exceeds the uncompressed size limit.")
            files[relative] = (archive.read(member), stat.S_IMODE(mode))
    missing = REQUIRED - files.keys()
    if missing:
        raise PlatformReleaseError("Required payload files are missing: " + ", ".join(sorted(missing)))
    if "platform-readme.md" in seen:
        raise PlatformReleaseError("Input already has a PLATFORM-README.md; use the original updater ZIP.")
    try:
        version = files["VERSION"][0].decode("ascii").strip()
        manifest = json.loads(files["release-manifest.json"][0])
    except (UnicodeError, ValueError) as exc:
        raise PlatformReleaseError("Unreadable VERSION or release manifest.") from exc
    if not VERSION_RE.fullmatch(version):
        raise PlatformReleaseError("VERSION must contain a safe semantic version.")
    if not isinstance(manifest, dict) or manifest.get("schema") != 1 or manifest.get("version") != version:
        raise PlatformReleaseError("Release manifest schema/version mismatch.")
    managed = manifest.get("files")
    if not isinstance(managed, dict) or set(managed) != files.keys() - {"release-manifest.json", "SHA256SUMS"}:
        raise PlatformReleaseError("Release manifest does not cover the exact payload.")
    for name, entry in managed.items():
        data, mode = files[name]
        if (not isinstance(entry, dict) or entry.get("sha256") != sha256(data)
                or entry.get("mode") != mode):
            raise PlatformReleaseError(f"Release manifest checksum/mode mismatch: {name}")
    expected_sums = "".join(f"{sha256(data)}  {name}\n" for name, (data, _mode)
                            in sorted(files.items()) if name != "SHA256SUMS").encode("utf-8")
    if files["SHA256SUMS"][0] != expected_sums:
        raise PlatformReleaseError("Payload checksum file is stale or incomplete.")
    for name in EXECUTABLES:
        if files[name][1] != 0o755:
            raise PlatformReleaseError(f"Executable permission missing from updater payload: {name}")
    return version, files


def platform_readme(platform: str, version: str) -> bytes:
    intro = f"# JK Cross Server {version}: {platform}\n\n"
    common = """
This is the complete server distribution, including bots and host spectator
code. Commercial game files are not included. Extract the whole ZIP and read
docs/PLATFORMS.md for requirements, setup, data persistence and known limits.
See docs/QUALIFICATION.md for the scope of runtime checks actually completed.
"""
    if platform == "windows-docker":
        instructions = """
Install and start Docker Desktop with Linux containers. In PowerShell, change
to this extracted directory and run (replace the example game-data path):

```powershell
.\\Start-Server.ps1 -GameData 'C:\\Games\\Jedi Knight'
```

Open http://127.0.0.1:8765. This runs the Linux x86-64 engine in Docker;
it is not a native Windows server port. Stop with `.\\Start-Server.ps1 -Command stop`.
"""
    elif platform == "macos-docker":
        instructions = """
Install and start Docker Desktop. In Terminal, change to this extracted
directory and run (replace the example game-data path):

```sh
sh ./Start-Server.command --game-data '/Users/you/Games/Jedi Knight'
```

Open http://127.0.0.1:8765. This runs the Linux x86-64 engine in Docker;
it is not a native macOS port. Apple Silicon uses linux/amd64 emulation,
with performance/compatibility requiring host validation. Stop with
`sh ./Start-Server.command stop`.
"""
    else:
        instructions = """
The bundled engine is native Linux x86-64. Follow the native Python 3.11+
environment, graphics libraries and game-data setup in docs/PLATFORMS.md.
From that environment, start the control panel with `python app.py`, then open
http://127.0.0.1:8765 and configure your game-data path and map.

Docker Engine with Compose v2 is an optional route:

```sh
sh ./start-server.sh --game-data '/home/you/Games/Jedi Knight'
```

Stop the Docker container with `sh ./start-server.sh stop`.
"""
    return (intro + common + instructions).encode("utf-8")


def build_platform_releases(source: Path, output_dir: Path) -> dict:
    version, files = read_payload(source)
    output_dir = output_dir.resolve()
    if any((parent / ".git").exists() for parent in (output_dir, *output_dir.parents)):
        raise PlatformReleaseError("Use an output directory outside a Git checkout.")
    output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for platform in ("windows-docker", "macos-docker", "linux-x86_64"):
        target = output_dir / f"JK_Cross_Server_{version}-{platform}.zip"
        checksum = target.with_suffix(".zip.sha256")
        for destination in (target, checksum):
            if destination.is_symlink() or destination.exists() and not destination.is_file():
                raise PlatformReleaseError(f"Refusing to replace non-regular output: {destination}")
        temp = None
        try:
            with tempfile.NamedTemporaryFile(prefix=".platform-", dir=output_dir, delete=False) as stream:
                temp = Path(stream.name)
            entries = files | {"PLATFORM-README.md": (platform_readme(platform, version), 0o644)}
            with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
                for name, (data, mode) in sorted(entries.items()):
                    info = zipfile.ZipInfo(ARCHIVE_ROOT + name, date_time=FIXED_DATE)
                    info.create_system = 3
                    info.external_attr = (stat.S_IFREG | mode) << 16
                    info.compress_type = zipfile.ZIP_DEFLATED
                    archive.writestr(info, data, compresslevel=9)
            digest = sha256(temp.read_bytes())
            temp.chmod(0o644)
            temp.replace(target)
            checksum.write_text(f"{digest}  {target.name}\n", encoding="ascii", newline="\n")
        finally:
            if temp is not None:
                temp.unlink(missing_ok=True)
        results.append({"platform": platform, "archive": str(target), "bytes": target.stat().st_size,
                        "sha256": digest, "checksum": str(checksum)})
    return {"version": version, "source": str(source.resolve()), "artifacts": results}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Existing verified updater ZIP")
    parser.add_argument("--output-dir", required=True, type=Path, help="External release output directory")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(build_platform_releases(args.input, args.output_dir), indent=2))
        return 0
    except (PlatformReleaseError, OSError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"Platform release build failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())

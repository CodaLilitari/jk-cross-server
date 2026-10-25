#!/usr/bin/env python3
"""Build the updater's reproducible ZIP from tracked release files.

Stage new distributable files first. Run --refresh-manifest after edits, then
--check or --output-dir PATH. Only the refresh command writes repository files.
This tool needs a Git checkout; it never discovers payload files recursively.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tempfile
import zipfile


MANIFEST = "release-manifest.json"
CHECKSUMS = "SHA256SUMS"
ARCHIVE_ROOT = "jk-cross-server"
FIXED_DATE = (1980, 1, 1, 0, 0, 0)
MAX_PAYLOAD_BYTES = 512 * 1024 * 1024
MAX_FILES = 10_000
REQUIRED = {"VERSION", "app.py", "LICENSE", "NOTICE.md", "web_gateway/requirements-lock.txt"}
SAFE_DOTFILES = {".gitignore", ".gitattributes", ".gitlab-ci.yml"}
LOCAL_DIRECTORIES = {
    "config", "runtime", "venv", "env", "__pycache__", "node_modules",
    "dist", "build", "deliverables", "downloads", "game-data", "game_data",
    "mots-data", "mods", "wine", "wine-prefix", "prefix", "secrets", "authority",
}
PRIVATE_NAMES = {
    "credentials.json", "credentials.yml", "credentials.yaml", "auth.json",
    "tokens.json", "token.json", "secrets.json", "secrets.yaml", "secrets.yml",
    "server.json", "instance.json", "settings.json",
    "keys.sqlite3", "keys.sqlite3-journal", "keys.sqlite3-wal", "keys.sqlite3-shm",
    "id_rsa", "id_ed25519", "id_ecdsa", "authorized_keys", "known_hosts",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".iso", ".gob", ".goo", ".pem", ".key", ".p12", ".pfx"}
VERSION_RE = re.compile(
    r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)


class ReleaseError(ValueError):
    """A package cannot be produced without changing its intended contents."""


@dataclass(frozen=True)
class PayloadFile:
    data: bytes
    mode: int


@dataclass(frozen=True)
class Snapshot:
    version: str
    files: dict[str, PayloadFile]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def excluded(name: str) -> bool:
    """Do not publish local state or credentials even if accidentally staged."""
    path = PurePosixPath(name)
    parts = path.parts
    if any(part.startswith(".") for part in parts) and name not in SAFE_DOTFILES:
        return True
    if any(part.lower() in LOCAL_DIRECTORIES for part in parts[:-1]):
        return True
    lower = path.name.lower()
    return (
        lower in PRIVATE_NAMES
        or lower == ".env"
        or lower.startswith(".env.")
        or lower.startswith("jk-admin-key-") and lower.endswith(".cog")
        or path.suffix.lower() in EXCLUDED_SUFFIXES
        or lower.startswith("jk_cross_server_") and lower.endswith((".zip", ".zip.sha256"))
    )


def _safe_name(name: str) -> None:
    parts = name.split("/")
    if (not name or name.startswith("/") or "\\" in name or ":" in name
            or any(part in ("", ".", "..") for part in parts)
            or any(ord(char) < 32 or ord(char) == 127 for char in name)):
        raise ReleaseError(f"Unsupported tracked path: {name!r}")


def _git(root: Path, *args: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args], check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ReleaseError("Release packaging requires a readable Git checkout.") from exc
    return result.stdout


def collect_payload(root: Path) -> Snapshot:
    """Read one consistent payload snapshot, using the Git index as allowlist."""
    root = root.resolve()
    top = Path(os.fsdecode(_git(root, "rev-parse", "--show-toplevel")).strip()).resolve()
    if top != root:
        raise ReleaseError("The source root must be the root of the Git checkout.")
    entries = _git(root, "ls-files", "--stage", "-z").split(b"\0")
    files: dict[str, PayloadFile] = {}
    seen: set[str] = set()
    total = 0
    for entry in entries:
        if not entry:
            continue
        try:
            header, raw_name = entry.split(b"\t", 1)
            mode, _object_id, stage = header.split(b" ")
            name = raw_name.decode("utf-8")
        except (ValueError, UnicodeError) as exc:
            raise ReleaseError("The Git index contains an unsupported path or entry.") from exc
        _safe_name(name)
        if stage != b"0":
            raise ReleaseError(f"Resolve the Git conflict before packaging: {name}")
        if name in (MANIFEST, CHECKSUMS) or excluded(name):
            continue
        if mode not in (b"100644", b"100755"):
            raise ReleaseError(f"Only regular tracked files may be packaged: {name}")
        if name.casefold() in seen:
            raise ReleaseError(f"Case-insensitive filename collision: {name}")
        seen.add(name.casefold())
        current = root
        try:
            for part in PurePosixPath(name).parts:
                current = current / part
                info = current.lstat()
                if stat.S_ISLNK(info.st_mode):
                    raise ReleaseError(f"Symlinked payload paths are not supported: {name}")
            if not stat.S_ISREG(info.st_mode):
                raise ReleaseError(f"Payload is not a regular file: {name}")
            total += info.st_size
            if total > MAX_PAYLOAD_BYTES or len(files) >= MAX_FILES:
                raise ReleaseError("Release payload exceeds its size or file-count limit.")
            data = current.read_bytes()
        except OSError as exc:
            raise ReleaseError(f"Cannot read tracked payload file: {name}") from exc
        if len(data) != info.st_size:
            raise ReleaseError(f"Payload changed while it was being read: {name}")
        files[name] = PayloadFile(data, 0o755 if mode == b"100755" else 0o644)
    missing = REQUIRED - files.keys()
    if missing:
        raise ReleaseError("Required release files are not tracked: " + ", ".join(sorted(missing)))
    try:
        version = files["VERSION"].data.decode("ascii").strip()
    except UnicodeError as exc:
        raise ReleaseError("VERSION must contain an ASCII semantic version.") from exc
    if not VERSION_RE.fullmatch(version):
        raise ReleaseError("VERSION must be a semantic version without a leading v or build metadata.")
    prerelease = version.partition("-")[2]
    if any(item.isdigit() and len(item) > 1 and item.startswith("0") for item in prerelease.split(".")):
        raise ReleaseError("Numeric prerelease identifiers cannot have leading zeros.")
    return Snapshot(version, files)


def metadata(snapshot: Snapshot) -> dict[str, PayloadFile]:
    manifest = {
        "schema": 1,
        "version": snapshot.version,
        "files": {
            name: {"sha256": sha256(item.data), "mode": item.mode}
            for name, item in sorted(snapshot.files.items())
        },
    }
    raw_manifest = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    covered = dict(snapshot.files, **{MANIFEST: PayloadFile(raw_manifest, 0o644)})
    sums = "".join(f"{sha256(item.data)}  {name}\n" for name, item in sorted(covered.items()))
    return {MANIFEST: covered[MANIFEST], CHECKSUMS: PayloadFile(sums.encode("utf-8"), 0o644)}


def _atomic_write(path: Path, data: bytes) -> None:
    if path.is_symlink() or path.exists() and not path.is_file():
        raise ReleaseError(f"Refusing to replace a non-regular output: {path}")
    temp = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".release-", dir=path.parent, delete=False) as stream:
            temp = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temp.chmod(0o644)
        temp.replace(path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def refresh_metadata(root: Path) -> Snapshot:
    snapshot = collect_payload(root)
    for name, item in metadata(snapshot).items():
        _atomic_write(root / name, item.data)
    return snapshot


def check_metadata(root: Path, snapshot: Snapshot | None = None) -> Snapshot:
    snapshot = snapshot or collect_payload(root)
    for name, expected in metadata(snapshot).items():
        path = root / name
        if path.is_symlink() or not path.is_file() or path.read_bytes() != expected.data:
            raise ReleaseError(f"{name} is missing or stale. Run --refresh-manifest after staging new release files.")
    return snapshot


def build_release(root: Path, output_dir: Path) -> dict[str, object]:
    snapshot = check_metadata(root)
    files = snapshot.files | metadata(snapshot)
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / f"JK_Cross_Server_{snapshot.version}.zip"
    checksum = archive.with_suffix(archive.suffix + ".sha256")
    for path in (archive, checksum):
        if path.is_symlink() or path.exists() and not path.is_file():
            raise ReleaseError(f"Refusing to replace a non-regular output: {path}")
    temp = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".release-", dir=output_dir, delete=False) as stream:
            temp = Path(stream.name)
        with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
            for name, item in sorted(files.items()):
                info = zipfile.ZipInfo(f"{ARCHIVE_ROOT}/{name}", date_time=FIXED_DATE)
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | item.mode) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                bundle.writestr(info, item.data, compresslevel=9)
        digest = sha256(temp.read_bytes())
        temp.chmod(0o644)
        temp.replace(archive)
        _atomic_write(checksum, f"{digest}  {archive.name}\n".encode("ascii"))
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)
    return {"version": snapshot.version, "files": len(files), "archive": str(archive.resolve()),
            "bytes": archive.stat().st_size, "sha256": digest, "checksum": str(checksum.resolve())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[1])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--refresh-manifest", action="store_true", help="Refresh managed-file manifest and checksums")
    mode.add_argument("--check", action="store_true", help="Verify manifest and checksums without writing files")
    parser.add_argument("--output-dir", type=Path, help="Output ZIP and checksum here (default: source-root/dist)")
    args = parser.parse_args(argv)
    if args.check and args.output_dir:
        parser.error("--check cannot be combined with --output-dir")
    root = args.source_root.resolve()
    try:
        if args.refresh_manifest:
            snapshot = refresh_metadata(root)
            if args.output_dir is None:
                print(json.dumps({"version": snapshot.version, "managed_files": len(snapshot.files), "refreshed": [MANIFEST, CHECKSUMS]}))
                return 0
        if args.check:
            snapshot = check_metadata(root)
            print(json.dumps({"version": snapshot.version, "managed_files": len(snapshot.files), "ok": True}))
        else:
            print(json.dumps(build_release(root, args.output_dir or root / "dist"), indent=2))
        return 0
    except (ReleaseError, OSError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"Release build failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())

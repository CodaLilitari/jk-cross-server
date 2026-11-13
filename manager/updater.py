"""Verified GitLab release updates for ZIP installations.

Standard-library-only so recovery can run before importing server modules.
Updates never run pip, a downloaded script, or a shell command.
"""
from __future__ import annotations
import asyncio
from contextlib import contextmanager
import datetime as dt
from functools import total_ordering
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import time
import tokenize
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import uuid
import zipfile

try:
    import fcntl
except ImportError:
    fcntl = None

PROJECT_ID = 88054997
PROJECT_PATH = "codalilitari/jk-cross-server"
PROJECT_URL = "https://gitlab.com/" + PROJECT_PATH
API_URL = f"https://gitlab.com/api/v4/projects/{PROJECT_ID}/releases"
MANIFEST = "release-manifest.json"
SUMS = "SHA256SUMS"
MAX_METADATA = 4 * 1024 * 1024
MAX_ARCHIVE = 128 * 1024 * 1024
MAX_UNPACKED = 512 * 1024 * 1024
MAX_FILES = 20000
RESERVED = {".git", ".jk-update", ".venv", "config", "runtime", "state", "authority"}


class UpdateError(ValueError):
    """An update cannot safely be installed."""


class InstallationBusy(UpdateError):
    """Another session/update holds the installation lock; retry later."""


@total_ordering
class Version:
    """SemVer precedence, including development releases/numeric identifiers."""
    _pattern = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
                          r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
                          r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?")

    def __init__(self, text):
        if not isinstance(text, str) or len(text) > 100:
            raise UpdateError("Release version must be a semantic version.")
        self.text = text.removeprefix("v")
        match = self._pattern.fullmatch(self.text)
        if not match:
            raise UpdateError("Release version must be a semantic version.")
        self.core = tuple(int(value) for value in match.group(1, 2, 3))
        self.pre = tuple(match.group(4).split(".")) if match.group(4) else ()
        if any(value.isdigit() and len(value) > 1 and value[0] == "0" for value in self.pre):
            raise UpdateError("Numeric prerelease identifiers cannot have leading zeroes.")

    def __eq__(self, other):
        if not isinstance(other, Version):
            return NotImplemented
        return self.core == other.core and self.pre == other.pre

    def __lt__(self, other):
        if not isinstance(other, Version):
            return NotImplemented
        if self.core != other.core:
            return self.core < other.core
        if not self.pre or not other.pre:
            return bool(self.pre) and not other.pre
        for left, right in zip(self.pre, other.pre):
            if left == right:
                continue
            if left.isdigit() and right.isdigit():
                return int(left) < int(right)
            if left.isdigit() != right.isdigit():
                return left.isdigit()
            return left < right
        return len(self.pre) < len(other.pre)


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise UpdateError("Duplicate JSON field in update metadata.")
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=unique)
    except (ValueError, UnicodeError) as exc:
        raise UpdateError("Invalid JSON update metadata.") from exc


def _relative(name):
    if (not isinstance(name, str) or not name or len(name) > 2048 or
            "\\" in name or ":" in name or any(ord(c) < 32 for c in name)):
        raise UpdateError("Invalid path in release metadata.")
    path = PurePosixPath(name)
    if path.is_absolute() or str(path) != name or any(part in (".", "..") for part in path.parts):
        raise UpdateError("Release paths must be ordinary relative file paths.")
    if path.parts[0].casefold() in RESERVED:
        raise UpdateError("Release includes a reserved local-data path.")
    filename = path.name.casefold()
    if ("authority" in (part.casefold() for part in path.parts[:-1]) or
            filename.startswith("jk-admin-key-") and filename.endswith(".cog") or
            filename in ("keys.sqlite3", "keys.sqlite3-journal", "keys.sqlite3-wal", "keys.sqlite3-shm")):
        raise UpdateError("Release includes private administrator credential storage.")
    return name


def _no_path_collisions(names):
    folded = set()
    for name in sorted(names):
        key = name.casefold()
        if key in folded:
            raise UpdateError("Release has duplicate or case-ambiguous paths.")
        folded.add(key)
    for name in folded:
        if any(str(parent) in folded for parent in PurePosixPath(name).parents if str(parent) != "."):
            raise UpdateError("Release changes a file into a directory; install it manually.")


def _manifest(raw):
    value = _json(raw)
    if not isinstance(value, dict) or value.get("schema") != 1:
        raise UpdateError("Unsupported release manifest schema.")
    Version(value.get("version"))
    files = value.get("files")
    if not isinstance(files, dict) or not 1 <= len(files) <= MAX_FILES:
        raise UpdateError("Release manifest has an invalid file count.")
    for name, record in files.items():
        _relative(name)
        if (name in (MANIFEST, SUMS) or not isinstance(record, dict) or
                set(record) != {"sha256", "mode"} or
                not isinstance(record["sha256"], str) or
                not re.fullmatch(r"[0-9a-f]{64}", record["sha256"]) or
                type(record["mode"]) is not int or record["mode"] not in (0o644, 0o755)):
            raise UpdateError("Invalid file record in release manifest.")
    if "VERSION" not in files:
        raise UpdateError("Release manifest is missing VERSION.")
    _no_path_collisions(files)
    return value


def _checksums(raw, expected):
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeError as exc:
        raise UpdateError("Invalid SHA256SUMS text.") from exc
    found = {}
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match or match[2] in found:
            raise UpdateError("Invalid or duplicate SHA256SUMS entry.")
        found[match[2]] = match[1]
    if found != expected:
        raise UpdateError("SHA256SUMS does not match the release manifest.")


def _trusted_url(url):
    if not isinstance(url, str):
        raise UpdateError("Update asset URL is missing.")
    parts = urlsplit(url)
    if (parts.scheme != "https" or parts.username or parts.password or
            parts.port not in (None, 443) or parts.hostname != "gitlab.com"):
        raise UpdateError("Update assets must use this GitLab project's HTTPS URLs.")
    path = unquote(parts.path)
    if (parts.fragment or "\\" in path or any(ord(c) < 32 for c in path) or
            any(part in (".", "..") for part in path.split("/"))):
        raise UpdateError("Update URL has an ambiguous path.")
    prefixes = (f"/api/v4/projects/{PROJECT_ID}/", f"/api/v4/projects/{PROJECT_PATH}/",
                f"/{PROJECT_PATH}/-/releases/")
    if not any(path.startswith(prefix) for prefix in prefixes):
        raise UpdateError("Update URL is outside the configured GitLab project.")


class _Redirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        _trusted_url(newurl)
        return super().redirect_request(request, fp, code, message, headers, newurl)


def fetch_public(url, limit):
    """Bounded anonymous HTTPS request. No local GitLab credentials are used."""
    _trusted_url(url)
    request = Request(url, headers={"User-Agent": "JK-Cross-Server-Updater/1", "Accept": "application/json, */*"})
    started = time.monotonic()
    try:
        with build_opener(_Redirects()).open(request, timeout=20) as response:
            declared = response.headers.get("Content-Length")
            if declared and int(declared) > limit:
                raise UpdateError("Update response exceeds its size limit.")
            chunks, total = [], 0
            while True:
                chunk = response.read(min(256 * 1024, limit + 1 - total))
                if not chunk:
                    return b"".join(chunks)
                total += len(chunk)
                if total > limit or time.monotonic() - started > 120:
                    raise UpdateError("Update response exceeded its size or time limit.")
                chunks.append(chunk)
    except HTTPError as exc:
        raise UpdateError(f"GitLab returned HTTP {exc.code}; the installed server is unchanged.") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise UpdateError("Could not reach GitLab. Check the network and try again.") from exc


def _sync_dir(path):
    if os.name == "posix":
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _write(path, data, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fchmod(stream.fileno(), mode)
        os.fsync(stream.fileno())


def _sync_tree(root):
    # Persist newly created staging/backup directory entries before the journal
    # permits modification of the live installation.
    directories = [root, *(path for path in root.rglob("*") if path.is_dir())]
    for directory in sorted(directories, key=lambda path: len(path.parts), reverse=True):
        _sync_dir(directory)


def _atomic_json(path, value):
    temporary = path.with_name(path.name + ".new")
    _write(temporary, (json.dumps(value, indent=2) + "\n").encode())
    os.replace(temporary, path)
    _sync_dir(path.parent)


class ReleaseUpdater:
    """Release checks and transactional install; the caller controls downtime."""
    def __init__(self, root: Path, state_dir: Path, *, protected_paths=(), fetcher=None):
        self.root = Path(root).resolve()
        self.state_dir = Path(state_dir).resolve()
        self.set_protected_paths(protected_paths)
        self.work = self.root / ".jk-update"
        self.journal = self.work / "journal.json"
        self.fetcher = fetcher or fetch_public
        self.running_version = self._version()
        self.latest = None
        self.last_checked = None
        self.error = None
        self.checking = self.installing = False
        self.receipt = None
        self._operation = asyncio.Lock()
        self._session_fd = None

    def set_protected_paths(self, paths):
        self.protected_paths = [self.state_dir, *(Path(p).resolve() for p in paths if p)]

    def _version(self):
        try:
            text = (self.root / "VERSION").read_text(encoding="utf-8").strip()
            return Version(text).text
        except (OSError, UnicodeError, UpdateError):
            return "unknown"

    def _block_reason(self):
        if fcntl is None:
            return "Automatic installation requires the Linux/POSIX ZIP installation. Download the release manually."
        checkout = (self.root / ".git").exists()
        for parent in self.root.parents:
            marker = parent / ".git"
            # Some managed environments mount empty placeholder directories.
            # An ancestor marks a real checkout only if it has Git metadata.
            if marker.is_dir() and (marker / "HEAD").is_file():
                checkout = True
            elif marker.is_file():
                try:
                    checkout = checkout or marker.read_bytes()[:4096].startswith(b"gitdir:")
                except OSError:
                    checkout = True
        if checkout:
            return "This is a Git checkout. Update it with Git to preserve local work and history."
        if not (self.root / MANIFEST).is_file():
            return "This installation has no release manifest. Install the new ZIP manually once to enable updates."
        return None

    def status(self):
        current = self._version()
        available = False
        try:
            available = bool(self.latest and Version(self.latest["version"]) > Version(current))
        except UpdateError:
            pass
        reason = self._block_reason()
        return {"current_version": current, "running_version": self.running_version,
                "latest_version": self.latest["version"] if self.latest else None,
                "update_available": available, "checking": self.checking, "installing": self.installing,
                "error": self.error, "last_checked": self.last_checked,
                "release_url": self.latest["release_url"] if self.latest else PROJECT_URL + "/-/releases",
                "restart_required": current != self.running_version,
                "install_supported": reason is None, "install_block_reason": reason,
                "receipt": self.receipt}

    def _request(self, url, limit):
        _trusted_url(url)
        data = self.fetcher(url, limit)
        if not isinstance(data, bytes) or len(data) > limit:
            raise UpdateError("Update response is invalid or exceeds its size limit.")
        return data

    def _check(self):
        candidates = []
        now = dt.datetime.now(dt.timezone.utc)
        for page in range(1, 4):
            url = f"{API_URL}?per_page=100&order_by=released_at&sort=desc&page={page}"
            releases = _json(self._request(url, MAX_METADATA))
            if not isinstance(releases, list) or len(releases) > 100:
                raise UpdateError("GitLab returned an invalid release list.")
            for release in releases:
                if not isinstance(release, dict) or release.get("upcoming_release"):
                    continue
                try:
                    tag = release["tag_name"]
                    version = Version(tag)
                    released = dt.datetime.fromisoformat(release["released_at"].replace("Z", "+00:00"))
                    if released.tzinfo is None or released > now:
                        continue
                    filename = f"JK_Cross_Server_{version.text}.zip"
                    links = release["assets"]["links"]
                    selected = {}
                    for name in (filename, filename + ".sha256"):
                        matching = [link for link in links if isinstance(link, dict) and link.get("name") == name]
                        if len(matching) != 1:
                            raise UpdateError("Release does not have a unique packaged ZIP and checksum.")
                        link = matching[0]
                        target = link.get("direct_asset_url") or link.get("url")
                        _trusted_url(target)
                        selected[name] = target
                    candidates.append({"version": version.text, "tag": tag, "filename": filename,
                                       "archive_url": selected[filename], "checksum_url": selected[filename + ".sha256"],
                                       "release_url": PROJECT_URL + "/-/releases/" + quote(tag, safe="")})
                except (KeyError, TypeError, ValueError, AttributeError):
                    continue  # Unrelated tags/incomplete releases are not install targets.
            if len(releases) < 100:
                break
        return max(candidates, key=lambda item: Version(item["version"])) if candidates else None

    async def check(self):
        async with self._operation:
            self.checking, self.error = True, None
            try:
                self.latest = await asyncio.to_thread(self._check)
                self.last_checked = _now()
            except Exception as exc:
                self.error = str(exc) if isinstance(exc, UpdateError) else "Could not check GitLab for updates."
                self.last_checked = _now()
            finally:
                self.checking = False
        return self.status()

    def _ensure_work(self):
        if self.work.is_symlink():
            raise UpdateError("The update working directory must not be a symbolic link.")
        self.work.mkdir(mode=0o700, exist_ok=True)
        # Persist root -> .jk-update before any live file can be replaced.
        _sync_dir(self.root)

    def _open_lock(self, exclusive):
        if fcntl is None:
            raise UpdateError("This platform does not support installation locking.")
        self._ensure_work()
        descriptor = os.open(self.work / "lock", os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            fcntl.flock(descriptor, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(descriptor)
            raise InstallationBusy("Another session or updater is using this installation. Stop all its sessions before updating.") from exc
        return descriptor

    @contextmanager
    def _exclusive(self):
        descriptor = self._open_lock(True)
        try:
            yield
        finally:
            os.close(descriptor)

    def acquire_session_lease(self):
        if self._session_fd is None and fcntl is not None:
            descriptor = self._open_lock(False)
            if self._version() != self.running_version or self.journal.exists():
                os.close(descriptor)
                raise UpdateError("Restart the control panel to finish the installed update before starting a session.")
            self._session_fd = descriptor

    def release_session_lease(self):
        if self._session_fd is not None:
            os.close(self._session_fd)
            self._session_fd = None

    def _destination(self, name):
        _relative(name)
        path = self.root / name
        for part in (path, *path.parents):
            if part == self.root:
                break
            if part.is_symlink():
                raise UpdateError(f"Managed path is a symbolic link: {name}")
            if part != path and part.exists() and not part.is_dir():
                raise UpdateError(f"Managed path has a local non-directory parent: {name}")
        for protected in self.protected_paths:
            if path == protected or protected in path.parents or path in protected.parents:
                raise UpdateError(f"Release overlaps configured local data: {name}")
        return path

    def _load_installed(self):
        raw = self._destination(MANIFEST).read_bytes()
        value = _manifest(raw)
        if value["version"] != self._version():
            raise UpdateError("Installed VERSION and release manifest differ; use a fresh release ZIP.")
        expected = {name: record["sha256"] for name, record in value["files"].items()}
        expected[MANIFEST] = _digest(raw)
        _checksums(self._destination(SUMS).read_bytes(), expected)
        for name, record in value["files"].items():
            path = self._destination(name)
            if not path.is_file() or _digest(path.read_bytes()) != record["sha256"]:
                raise UpdateError(f"Locally modified or missing managed file: {name}. Preserve your edits and update manually.")
        return value

    def _unpack(self, data, stage, version, *, backup_bytes=0):
        try:
            archive = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as exc:
            raise UpdateError("The downloaded release is not a valid ZIP archive.") from exc
        with archive:
            records = {}
            total = 0
            for info in archive.infolist():
                if not info.filename.startswith("jk-cross-server/"):
                    raise UpdateError("Release ZIP has an unexpected root folder.")
                name = info.filename[len("jk-cross-server/"):]
                if info.is_dir():
                    if name:
                        _relative(name.rstrip("/"))
                    continue
                _relative(name)
                kind = stat.S_IFMT(info.external_attr >> 16)
                if kind not in (0, stat.S_IFREG) or info.flag_bits & 1:
                    raise UpdateError("Release ZIP may contain only ordinary unencrypted files.")
                if name in records:
                    raise UpdateError("Release ZIP contains duplicate files.")
                records[name] = info
                total += info.file_size
                if len(records) > MAX_FILES + 2 or total > MAX_UNPACKED:
                    raise UpdateError("Release ZIP exceeds its unpacking limits.")
            _no_path_collisions(records)
            if shutil.disk_usage(self.root).free < total + backup_bytes + 16 * 1024 * 1024:
                raise UpdateError("Not enough free disk space to stage the update and retain a backup.")
            if MANIFEST not in records or SUMS not in records:
                raise UpdateError("Release ZIP is missing its manifest or checksums.")
            if records[MANIFEST].file_size > MAX_METADATA or records[SUMS].file_size > MAX_METADATA:
                raise UpdateError("Release metadata exceeds its size limit.")
            raw = archive.read(records[MANIFEST])
            value = _manifest(raw)
            if value["version"] != version:
                raise UpdateError("Release manifest version does not match the GitLab release.")
            if set(records) != set(value["files"]) | {MANIFEST, SUMS}:
                raise UpdateError("Release ZIP contents do not match the release manifest.")
            expected = {name: item["sha256"] for name, item in value["files"].items()}
            expected[MANIFEST] = _digest(raw)
            sums = archive.read(records[SUMS])
            _checksums(sums, expected)
            for name, info in records.items():
                contents = archive.read(info)
                if name != SUMS and _digest(contents) != expected[name]:
                    raise UpdateError(f"Release file checksum failed: {name}")
                mode = value["files"].get(name, {}).get("mode", 0o644)
                _write(stage / name, contents, mode)
            if (stage / "VERSION").read_text(encoding="utf-8").strip() != version:
                raise UpdateError("Packaged VERSION does not match the release manifest.")
            for name in value["files"]:
                if name.endswith(".py"):
                    try:
                        with tokenize.open(stage / name) as source:
                            compile(source.read(), name, "exec")
                    except (SyntaxError, UnicodeError) as exc:
                        raise UpdateError(f"Release code is incompatible with this Python: {name}") from exc
            return value

    def _validate_journal(self, value):
        if (not isinstance(value, dict) or value.get("schema") != 1 or
                value.get("phase") not in ("applying", "committed") or
                not isinstance(value.get("transaction"), str) or
                not re.fullmatch(r"transaction-[0-9a-f]{32}", value["transaction"]) or
                not isinstance(value.get("paths"), list) or len(value["paths"]) > MAX_FILES + 2 or
                not isinstance(value.get("previous"), dict)):
            raise UpdateError("Update recovery journal is invalid; restore the saved backup manually.")
        for name in value["paths"]:
            self._destination(name)
        _no_path_collisions(value["paths"])
        if not set(value["previous"]).issubset(value["paths"]):
            raise UpdateError("Update recovery journal has inconsistent paths.")
        for record in value["previous"].values():
            if (not isinstance(record, dict) or set(record) != {"sha256", "mode"} or
                    not re.fullmatch(r"[0-9a-f]{64}", str(record["sha256"])) or
                    type(record["mode"]) is not int or record["mode"] not in (0o644, 0o755)):
                raise UpdateError("Update recovery journal has invalid backup records.")
        return value

    def _sync_install_directories(self, names):
        # Only visit ancestors of managed paths, never unrelated local data.
        # Sync deepest first so new nested entries are durable through root.
        directories = {self.root}
        for name in names:
            parent = (self.root / name).parent
            while parent != self.root:
                if parent.is_dir():
                    directories.add(parent)
                parent = parent.parent
        for directory in sorted(directories, key=lambda path: len(path.parts), reverse=True):
            _sync_dir(directory)

    def _rollback(self, journal):
        transaction = self.work / journal["transaction"]
        backup = transaction / "backup"
        # Check the whole backup before changing even one installed file.
        for name, record in journal["previous"].items():
            source = backup / name
            if source.is_symlink() or not source.is_file() or _digest(source.read_bytes()) != record["sha256"]:
                raise UpdateError("Update backup is incomplete. Restore the installation manually before starting.")
        for name in journal["paths"]:
            destination = self._destination(name)
            if name in journal["previous"]:
                record = journal["previous"][name]
                temporary = transaction / "restore" / name
                _write(temporary, (backup / name).read_bytes(), record["mode"])
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(temporary, destination)
            elif destination.exists():
                destination.unlink()
            if destination.parent.is_dir():
                _sync_dir(destination.parent)
        self._sync_install_directories(journal["paths"])
        self.receipt = {"outcome": "rolled_back", "previous_version": journal["previous_version"],
                        "target_version": journal["target_version"], "completed_at": _now()}
        _atomic_json(self.work / "last-receipt.json", self.receipt)
        self.journal.unlink()
        _sync_dir(self.work)
        shutil.rmtree(transaction)

    def _finish(self, journal):
        transaction = self.work / journal["transaction"]
        last = self.work / "last-backup"
        if transaction.exists():
            if last.is_symlink():
                raise UpdateError("The retained backup path must not be a symbolic link.")
            if last.exists():
                shutil.rmtree(last)
            transaction.rename(last)
        self.journal.unlink(missing_ok=True)
        _sync_dir(self.work)

    def recover(self):
        """Recover before server imports; return True if the launcher must re-exec."""
        if not self.work.exists():
            return False
        rolled_back = False
        self._ensure_work()
        transactions = [path for path in self.work.glob("transaction-*")
                        if re.fullmatch(r"transaction-[0-9a-f]{32}", path.name)]
        if self.journal.exists() or transactions:
            with self._exclusive():
                if self.journal.exists():
                    journal = self._validate_journal(_json(self.journal.read_bytes()))
                    if journal["phase"] == "applying":
                        self._rollback(journal)
                        rolled_back = True
                    else:
                        self._finish(journal)
                # Interrupted download/staging has not changed installed files.
                for transaction in transactions:
                    if transaction.exists() and not transaction.is_symlink():
                        shutil.rmtree(transaction)
        receipt = self.work / "last-receipt.json"
        if receipt.is_file():
            self.receipt = _json(receipt.read_bytes())
        self.running_version = self._version()
        return rolled_back

    def _install(self, target):
        reason = self._block_reason()
        if reason:
            raise UpdateError(reason)
        with self._exclusive():
            if self.journal.exists():
                raise UpdateError("An interrupted update needs recovery. Restart the control panel first.")
            current = self._load_installed()
            if Version(target["version"]) <= Version(current["version"]):
                raise UpdateError("This release is already installed or older; downgrades are not automatic.")
            try:
                checksum_text = self._request(target["checksum_url"], 4096).decode("ascii").strip()
            except UnicodeError as exc:
                raise UpdateError("Release checksum sidecar is not valid ASCII.") from exc
            match = re.fullmatch(r"([0-9a-fA-F]{64}) [ *]" + re.escape(target["filename"]), checksum_text)
            if not match:
                raise UpdateError("Release checksum sidecar does not identify the expected ZIP.")
            archive = self._request(target["archive_url"], MAX_ARCHIVE)
            archive_digest = _digest(archive)
            if archive_digest != match[1].lower():
                raise UpdateError("Downloaded release checksum failed; the installed server is unchanged.")
            previous_names = set(current["files"]) | {MANIFEST, SUMS}
            size = sum(self._destination(name).stat().st_size for name in previous_names)
            if shutil.disk_usage(self.root).free < size + 16 * 1024 * 1024:
                raise UpdateError("Not enough free disk space to stage the update and retain a backup.")
            transaction = self.work / ("transaction-" + uuid.uuid4().hex)
            transaction.mkdir(mode=0o700)
            journal = None
            try:
                stage = transaction / "stage"
                upcoming = self._unpack(archive, stage, target["version"], backup_bytes=size)
                for dependency in ("web_gateway/requirements-lock.txt", "web_gateway/requirements.txt"):
                    if current["files"].get(dependency) != upcoming["files"].get(dependency):
                        raise UpdateError("This release changes Python dependencies. Install the release and its dependency lock manually.")
                target_names = set(upcoming["files"]) | {MANIFEST, SUMS}
                all_names = previous_names | target_names
                _no_path_collisions(all_names)
                for name in all_names:
                    destination = self._destination(name)
                    if name not in previous_names and destination.exists():
                        raise UpdateError(f"New release file would overwrite local content: {name}")
                previous = {}
                for name in previous_names:
                    source = self._destination(name)
                    contents = source.read_bytes()
                    mode = current["files"].get(name, {}).get("mode", 0o644)
                    previous[name] = {"sha256": _digest(contents), "mode": mode}
                    _write(transaction / "backup" / name, contents, mode)
                _sync_tree(transaction)
                # VERSION and manifests are committed last, after the payload.
                ordered = sorted(all_names - {"VERSION", MANIFEST, SUMS}) + [SUMS, MANIFEST, "VERSION"]
                journal = {"schema": 1, "transaction": transaction.name, "phase": "applying",
                           "previous_version": current["version"], "target_version": upcoming["version"],
                           "paths": ordered, "previous": previous}
                _atomic_json(self.journal, journal)
                for name in ordered:
                    destination = self._destination(name)
                    if name in target_names:
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        os.replace(stage / name, destination)
                    else:
                        destination.unlink()
                    _sync_dir(destination.parent)
                self._sync_install_directories(ordered)
                self._load_installed()
                self.receipt = {"outcome": "installed", "previous_version": current["version"],
                                "target_version": upcoming["version"], "archive_sha256": archive_digest,
                                "completed_at": _now(), "backup_directory": str(self.work / "last-backup" / "backup")}
                _atomic_json(self.work / "last-receipt.json", self.receipt)
                journal["phase"] = "committed"
                _atomic_json(self.journal, journal)
                self._finish(journal)
                return self.receipt
            except BaseException:
                if journal is not None and self.journal.exists():
                    persisted = self._validate_journal(_json(self.journal.read_bytes()))
                    if persisted["phase"] == "applying":
                        self._rollback(persisted)
                elif transaction.exists():
                    shutil.rmtree(transaction)
                raise

    async def install(self):
        """Install last checked release. Caller must hold the session lock."""
        async with self._operation:
            if not self.latest:
                raise UpdateError("Check GitLab for an update first.")
            self.installing, self.error = True, None
            worker = asyncio.create_task(asyncio.to_thread(self._install, dict(self.latest)))
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                # A thread cannot be cancelled. Finish or roll back before the
                # application releases its session lock during shutdown.
                await worker
                raise
            except Exception as exc:
                self.error = str(exc) if isinstance(exc, (UpdateError, OSError)) else "Update failed; check the retained update receipt."
                if isinstance(exc, UpdateError):
                    raise
                raise UpdateError(self.error) from exc
            finally:
                self.installing = False
        return self.status()

"""Persistent chat-admin credentials and bounded connection-bound proof policy.

Credentials are created only by an explicit issue/rotate call. The server keeps
HMAC-equivalent secrets in a private SQLite store, outside game/run directories.
No method returns secret material except the one-time issue/rotate download.
"""
from __future__ import annotations

from collections import deque
from contextlib import contextmanager
import datetime as dt
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import stat
import time

from tools.admin_key import CAPABILITIES, HEX16, HEX32, HEX64, canonical, render_credential


class AuthorityError(ValueError):
    """Safe to return to the authenticated local panel; never contains a secret."""


def _label(value):
    if not isinstance(value, str):
        raise AuthorityError("An admin credential needs a label.")
    value = value.strip()
    if not 1 <= len(value) <= 80 or any(not 32 <= ord(c) <= 126 for c in value):
        raise AuthorityError("Use 1–80 printable ASCII characters for the credential label.")
    return value


def _caps(value):
    if (not isinstance(value, (list, tuple)) or not 1 <= len(value) <= len(CAPABILITIES)
            or any(not isinstance(c, str) or c not in CAPABILITIES for c in value)
            or len(set(value)) != len(value)):
        raise AuthorityError("Choose the next-level capability, the kick capability, or both.")
    return sorted(value)


def _stamp(value):
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise AuthorityError("Admin credential storage is invalid.")
    try:
        return dt.datetime.fromtimestamp(value, dt.timezone.utc).isoformat(timespec="seconds")
    except (ValueError, OverflowError, OSError):
        raise AuthorityError("Admin credential storage is invalid.") from None


class AuthorityStore:
    MAX_RECORDS = 2048
    MAX_DATABASE_BYTES = 8 * 1024 * 1024

    def __init__(self, directory: Path, *, clock=time.time):
        # absolute(), not resolve(): symlinks must remain detectable.
        self.directory = Path(directory).absolute()
        self.path = self.directory / "keys.sqlite3"
        self._clock = clock

    def _check_ancestors(self):
        for item in reversed((self.directory, *self.directory.parents)):
            try:
                st = item.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
                raise AuthorityError("Admin authority paths must be real directories, not symbolic links.")

    @staticmethod
    def _private_file(path, *, directory=False):
        st = path.lstat()
        wanted = stat.S_ISDIR if directory else stat.S_ISREG
        mode = 0o700 if directory else 0o600
        if (not wanted(st.st_mode) or stat.S_IMODE(st.st_mode) != mode
                or (hasattr(os, "getuid") and st.st_uid != os.getuid())
                or (not directory and st.st_nlink != 1)):
            raise AuthorityError("Admin authority permissions or file ownership are unsafe.")
        return st

    def _check_paths(self, *, create=False):
        self._check_ancestors()
        if not self.directory.exists():
            if not create:
                return False
            self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._private_file(self.directory, directory=True)
        # A rollback journal can survive a crash. Never follow an injected link.
        for suffix in ("-journal", "-wal", "-shm"):
            sidecar = self.path.with_name(self.path.name + suffix)
            if sidecar.exists() or sidecar.is_symlink():
                self._private_file(sidecar)
        if self.path.exists() or self.path.is_symlink():
            st = self._private_file(self.path)
            if st.st_size > self.MAX_DATABASE_BYTES:
                raise AuthorityError("Admin credential storage exceeds its supported size.")
            return True
        return False

    @contextmanager
    def _connection(self, *, write=False, create=False):
        connection = None
        created = False
        try:
            exists = self._check_paths(create=create)
            if not exists:
                if not create:
                    yield None, False
                    return
                flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
                fd = os.open(self.path, flags, 0o600)
                os.close(fd)
                created = True
            mode = "rw" if write else "ro"
            connection = sqlite3.connect(self.path.as_uri() + "?mode=" + mode,
                                         uri=True, timeout=2, isolation_level=None)
            connection.row_factory = sqlite3.Row
            if write:
                connection.execute("PRAGMA journal_mode=DELETE")
                connection.execute("PRAGMA synchronous=FULL")
                connection.execute("BEGIN IMMEDIATE")
            yield connection, created
            if write:
                connection.commit()
        except AuthorityError:
            if connection is not None and write:
                connection.rollback()
            raise
        except (OSError, sqlite3.Error, UnicodeError, ValueError, TypeError):
            if connection is not None and write:
                connection.rollback()
            raise AuthorityError("Admin credential storage is unavailable or invalid.") from None
        finally:
            if connection is not None:
                connection.close()
            # On a failed first transaction leave the file fail-closed. Never
            # silently replace an existing identity or regenerate credentials.

    def _initialize(self, connection):
        connection.execute("CREATE TABLE metadata (name TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("""CREATE TABLE credentials (
            key_id TEXT PRIMARY KEY, label TEXT NOT NULL, secret BLOB NOT NULL,
            capabilities TEXT NOT NULL, created_at INTEGER NOT NULL,
            revoked_at INTEGER, last_used_at INTEGER, rotated_from TEXT)
        """)
        connection.executemany("INSERT INTO metadata(name,value) VALUES (?,?)",
                               (("version", "1"), ("server_id", secrets.token_hex(16))))

    @staticmethod
    def _server_id(connection):
        values = dict(connection.execute("SELECT name,value FROM metadata"))
        if set(values) != {"version", "server_id"} or values["version"] != "1" or not HEX32.fullmatch(values["server_id"]):
            raise AuthorityError("Admin credential storage schema is invalid.")
        return values["server_id"]

    @staticmethod
    def _record(row, server_id):
        try:
            caps = json.loads(row["capabilities"])
            if (not isinstance(row["key_id"], str) or not HEX16.fullmatch(row["key_id"])
                    or not isinstance(row["secret"], bytes) or len(row["secret"]) != 32
                    or _label(row["label"]) != row["label"] or _caps(caps) != caps
                    or (row["rotated_from"] is not None and not HEX16.fullmatch(row["rotated_from"]))):
                raise AuthorityError("Admin credential storage is invalid.")
            return {"id": row["key_id"], "server_id": server_id, "label": row["label"],
                    "capabilities": caps, "created_at": _stamp(row["created_at"]),
                    "revoked_at": _stamp(row["revoked_at"]), "last_used_at": _stamp(row["last_used_at"]),
                    "rotated_from": row["rotated_from"],
                    "status": "revoked" if row["revoked_at"] is not None else "active"}
        except (ValueError, TypeError, KeyError, IndexError):
            raise AuthorityError("Admin credential storage is invalid.") from None

    def _validated(self, connection):
        """Validate the whole bounded ledger before any use or mutation."""
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if tables != {"metadata", "credentials"}:
            raise AuthorityError("Admin credential storage schema is invalid.")
        server_id = self._server_id(connection)
        rows = connection.execute("SELECT * FROM credentials ORDER BY created_at,key_id LIMIT ?",
                                  (self.MAX_RECORDS + 1,)).fetchall()
        if len(rows) > self.MAX_RECORDS:
            raise AuthorityError("Admin credential storage contains too many records.")
        metadata = [self._record(row, server_id) for row in rows]
        return server_id, rows, metadata

    def metadata(self):
        result = {"version": 1, "server_id": None, "credentials": [],
                  "supported_capabilities": list(CAPABILITIES)}
        with self._connection() as (connection, _):
            if connection is None:
                return result
            result["server_id"], _, result["credentials"] = self._validated(connection)
        return result

    def _issue(self, connection, server_id, label, capabilities, *, rotated_from=None):
        if connection.execute("SELECT COUNT(*) FROM credentials").fetchone()[0] >= self.MAX_RECORDS:
            raise AuthorityError("The credential record limit has been reached; retain revocation records when archiving this authority.")
        key_id = None
        for _ in range(16):
            candidate = secrets.token_hex(8)
            if not connection.execute("SELECT 1 FROM credentials WHERE key_id=?", (candidate,)).fetchone():
                key_id = candidate
                break
        if key_id is None:
            raise AuthorityError("Unable to allocate a new credential identifier.")
        secret = secrets.token_bytes(32)
        created_at = int(self._clock())
        connection.execute("INSERT INTO credentials VALUES (?,?,?,?,?,NULL,NULL,?)",
                           (key_id, label, secret, canonical(capabilities), created_at, rotated_from))
        row = connection.execute("SELECT * FROM credentials WHERE key_id=?", (key_id,)).fetchone()
        metadata = self._record(row, server_id)
        text = render_credential({"format": "JKADMIN-KEY", "version": 1, "server_id": server_id,
                                  "key_id": key_id, "secret": secret.hex(), "label": label,
                                  "capabilities": capabilities})
        return {"metadata": metadata, "credential": text, "filename": f"jk-admin-key-{key_id}.cog"}

    def issue(self, label, capabilities):
        label, capabilities = _label(label), _caps(capabilities)
        with self._connection(write=True, create=True) as (connection, created):
            if created:
                self._initialize(connection)
            server_id, _, _ = self._validated(connection)
            result = self._issue(connection, server_id, label, capabilities)
        return result

    def revoke(self, key_id):
        if not isinstance(key_id, str) or not HEX16.fullmatch(key_id):
            raise AuthorityError("Invalid admin credential identifier.")
        with self._connection(write=True) as (connection, _):
            if connection is None:
                raise AuthorityError("Unknown admin credential.")
            server_id, _, _ = self._validated(connection)
            row = connection.execute("SELECT * FROM credentials WHERE key_id=?", (key_id,)).fetchone()
            if row is None:
                raise AuthorityError("Unknown admin credential.")
            self._record(row, server_id)
            connection.execute("UPDATE credentials SET revoked_at=COALESCE(revoked_at,?) WHERE key_id=?",
                               (int(self._clock()), key_id))
            row = connection.execute("SELECT * FROM credentials WHERE key_id=?", (key_id,)).fetchone()
            result = self._record(row, server_id)
        return result

    def rotate(self, key_id):
        if not isinstance(key_id, str) or not HEX16.fullmatch(key_id):
            raise AuthorityError("Invalid admin credential identifier.")
        with self._connection(write=True) as (connection, _):
            if connection is None:
                raise AuthorityError("Unknown admin credential.")
            server_id, _, _ = self._validated(connection)
            row = connection.execute("SELECT * FROM credentials WHERE key_id=?", (key_id,)).fetchone()
            if row is None:
                raise AuthorityError("Unknown admin credential.")
            previous = self._record(row, server_id)
            if previous["status"] != "active":
                raise AuthorityError("A revoked credential cannot be rotated; explicitly issue a new credential.")
            result = self._issue(connection, server_id, previous["label"], previous["capabilities"], rotated_from=key_id)
            connection.execute("UPDATE credentials SET revoked_at=? WHERE key_id=?", (int(self._clock()), key_id))
        return result

    def _active_record(self, key_id):
        """Internal only: includes an HMAC-equivalent secret, never serialize it."""
        if not isinstance(key_id, str) or not HEX16.fullmatch(key_id):
            return None
        with self._connection() as (connection, _):
            if connection is None:
                return None
            _, rows, metadata = self._validated(connection)
            for row, info in zip(rows, metadata):
                if row["key_id"] == key_id:
                    return (info, bytes(row["secret"])) if info["status"] == "active" else None
            return None

    def _mark_used(self, key_id):
        with self._connection(write=True) as (connection, _):
            if connection is None:
                return False
            self._validated(connection)
            changed = connection.execute("UPDATE credentials SET last_used_at=? WHERE key_id=? AND revoked_at IS NULL",
                                         (int(self._clock()), key_id)).rowcount
        return changed == 1


class GameAuthority:
    CHALLENGE_SECONDS = 120
    SESSION_SECONDS = 15 * 60
    MAX_PENDING = 128
    MAX_SESSIONS = 128
    MAX_RATE_PEERS = 256
    RATE_WINDOW = 60
    BEGIN_LIMIT = 4
    PROOF_LIMIT = 8
    GLOBAL_BEGIN_LIMIT = 64

    def __init__(self, store: AuthorityStore, *, clock=time.monotonic):
        self.store = store
        self._clock = clock
        self._epoch = secrets.token_bytes(16)
        self._dummy_secret = secrets.token_bytes(32)
        self._pending = {}
        self._sessions = {}
        self._rates = {}
        self._global_begins = deque()

    @staticmethod
    def _peer(peer_id, generation):
        return (peer_id, generation) if (type(peer_id) is int and 2 <= peer_id <= 0xFFFFFFFF
                                        and type(generation) is int and 1 <= generation <= 0xFFFFFFFF) else None

    def _prune(self, now):
        self._pending = {p: value for p, value in self._pending.items() if value["expires"] > now}
        self._sessions = {p: value for p, value in self._sessions.items() if value["expires"] > now}
        for key in list(self._rates):
            queue = self._rates[key]
            while queue and queue[0] <= now - self.RATE_WINDOW:
                queue.popleft()
            if not queue:
                del self._rates[key]
        while self._global_begins and self._global_begins[0] <= now - self.RATE_WINDOW:
            self._global_begins.popleft()

    def _rate(self, peer, action, limit, now):
        key = (peer, action)
        if key not in self._rates:
            if len(self._rates) >= self.MAX_RATE_PEERS:
                return False
            self._rates[key] = deque()
        queue = self._rates[key]
        if len(queue) >= limit:
            return False
        queue.append(now)
        return True

    def begin(self, peer_id, generation):
        now = self._clock()
        self._prune(now)
        peer = self._peer(peer_id, generation)
        if peer is None:
            return "Admin authentication failed."
        if (len(self._global_begins) >= self.GLOBAL_BEGIN_LIMIT
                or not self._rate(peer, "begin", self.BEGIN_LIMIT, now)):
            return "Admin authentication rate limited; wait before trying again."
        self._global_begins.append(now)
        try:
            metadata = self.store.metadata()
        except AuthorityError:
            return "Admin authentication is unavailable."
        if not metadata["server_id"] or not any(row["status"] == "active" for row in metadata["credentials"]):
            return "No active admin credentials have been issued."
        if peer not in self._pending and len(self._pending) >= self.MAX_PENDING:
            return "Admin authentication is busy; try again later."
        nonce = secrets.token_hex(16)
        self._sessions.pop(peer, None)
        self._pending[peer] = {"server_id": metadata["server_id"], "nonce": nonce,
                               "expires": now + self.CHALLENGE_SECONDS, "epoch": self._epoch}
        return f"JKADMIN1:{metadata['server_id']}:{nonce}"

    def prove(self, peer_id, generation, key_id, mac):
        now = self._clock()
        self._prune(now)
        peer = self._peer(peer_id, generation)
        if peer is None:
            return "Admin authentication failed."
        pending = self._pending.pop(peer, None)  # Every submitted proof consumes its challenge.
        if not self._rate(peer, "prove", self.PROOF_LIMIT, now):
            return "Admin authentication rate limited; wait before trying again."
        if pending is None or pending["epoch"] != self._epoch:
            return "Admin authentication failed; request a new challenge."
        if not isinstance(key_id, str) or not HEX16.fullmatch(key_id):
            return "Admin authentication failed; request a new challenge."
        try:
            record = self.store._active_record(key_id)
            secret = record[1] if record else self._dummy_secret
            message = f"JKADMIN1\n{pending['server_id']}\n{pending['nonce']}\n{key_id}".encode("ascii")
            expected = hmac.new(secret, message, hashlib.sha256).digest()
            valid_format = isinstance(mac, str) and HEX64.fullmatch(mac) is not None
            supplied = bytes.fromhex(mac) if valid_format else bytes(32)
            valid_mac = hmac.compare_digest(expected, supplied)
            if (not record or not valid_format or not valid_mac
                    or not hmac.compare_digest(record[0]["server_id"], pending["server_id"])):
                return "Admin authentication failed; request a new challenge."
            if peer not in self._sessions and len(self._sessions) >= self.MAX_SESSIONS:
                return "Admin authentication is busy; try again later."
            if not self.store._mark_used(key_id):
                return "Admin authentication failed; request a new challenge."
        except AuthorityError:
            return "Admin authentication is unavailable."
        self._sessions[peer] = {"key_id": key_id, "server_id": pending["server_id"],
                                "expires": now + self.SESSION_SECONDS, "epoch": self._epoch}
        return "Admin authenticated for 15 minutes on this connection."

    def authorized(self, peer_id, generation, capability=None):
        now = self._clock()
        self._prune(now)
        peer = self._peer(peer_id, generation)
        grant = self._sessions.get(peer)
        if not grant or grant["epoch"] != self._epoch or (capability is not None and capability not in CAPABILITIES):
            return False
        try:
            record = self.store._active_record(grant["key_id"])
        except AuthorityError:
            record = None
        if not record or record[0]["server_id"] != grant["server_id"]:
            self._sessions.pop(peer, None)
            return False
        return capability is None or capability in record[0]["capabilities"]

    def logout(self, peer_id, generation):
        peer = self._peer(peer_id, generation)
        self._pending.pop(peer, None)
        self._sessions.pop(peer, None)

    def reset(self):
        self._epoch = secrets.token_bytes(16)
        self._pending.clear()
        self._sessions.clear()
        self._rates.clear()
        self._global_begins.clear()

    def status(self):
        self._prune(self._clock())
        for peer in tuple(self._sessions):
            self.authorized(*peer)
        return {"pending_challenges": len(self._pending), "authenticated_connections": len(self._sessions)}

"""Prepared host offers for unchanged JKDF2Web cloudflare-38 clients.

Matches maps.js/mods.js at a7c0211ca408eabd97a7c82fbdcae9450c3a0b9c.
Only startup-selected episode/mod snapshots are addressable. Network requests
contain a kind/hash, never a filesystem path.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import stat
import struct
from types import MappingProxyType

MAGIC, VERSION, HEADER = b"JKMT", 1, 16
INFO_REQUEST, INFO, CHUNK_REQUEST, CHUNK = 1, 2, 3, 4
MAP, MOD = 0, 1
CHUNK_DIRECT, CHUNK_RELAY = 16384, 49152
MAX_CHUNKS_PER_REQUEST = 128
MAX_MAP_BYTES, MAX_MOD_BYTES = 100 * 1024**2, 250 * 1024**2
MAX_MOD_FILES, MAX_REFS, GOB_ENTRY, MAX_DEPTH = 10000, 65536, 136, 8
RETAIL_EPISODES = frozenset(("jk1", "jk1ctf", "jk1mp", "jk1demo", "jk1mpdem",
                           "jk1mpdemo", "jkm", "jkm_kfy", "jkm_mp", "jkm_saber"))
RETAIL_FILES = {
    "gob": ("episode/JK1.gob", "episode/JK1CTF.gob", "episode/JK1MP.gob",
            "episode/jk1demo.gob", "episode/jk1mpdem.gob", "episode/jk1mpdemo.gob",
            "resource/Res1hi.gob", "resource/Res1low.gob", "resource/Res2.gob",
            "resource/res1demo.gob", "resource/res1.gob"),
    "goo": ("episode/JKM.goo", "episode/JKM_KFY.goo", "episode/JKM_MP.goo",
            "episode/JKM_SABER.goo", "resource/Jkmres.goo", "resource/JKMsndLO.goo",
            "resource/jkmsnd.goo"),
}
EXCLUDED_EXTENSIONS = frozenset(("exe", "dll", "ico", "ini", "txt", "url", "pdf",
                                "htm", "html", "zip", "rar", "7z", "bak", "tmp"))
ENGINE_EXTENSIONS = frozenset(("gob", "goo", "jkl", "cog", "mat", "3do", "pup",
                               "key", "snd", "wav", "bm", "cmp", "sft", "spr",
                               "par", "ai", "dat", "uni", "jkt", "jkm"))


class AssetPreparationError(ValueError):
    """Selected content cannot be described by the existing browser format."""


@dataclass(frozen=True)
class Entry:
    offset: int
    size: int
    name: str = ""


def valid_episode_name(name):
    return (isinstance(name, str) and 1 <= len(name) <= 31 and name[0] != "." and
            ".." not in name and not re.search(r'[\/\\:*?"<>|\x00-\x1f]', name))


def packable(rel):
    parts = rel.split("/")
    if any(p.startswith(".") or p.lower() == "__macosx" for p in parts):
        return False
    base = parts[-1].lower()
    return (base not in ("thumbs.db", "desktop.ini") and
            not ("." in base and base.rsplit(".", 1)[-1] in EXCLUDED_EXTENSIONS))


def valid_relative_path(rel):
    if not isinstance(rel, str) or not 1 <= len(rel) <= 127 or not re.fullmatch(r"[\x20-\x7e]+", rel):
        return False
    parts = rel.split("/")
    return len(parts) <= MAX_DEPTH + 1 and all(
        p not in ("", ".", "..") and not re.search(r'[\\:*?"<>|]', p) and
        p[-1] not in (" ", ".") for p in parts)


def clean_mod_name(name):
    raw = str(name or "").encode("utf-16-le", errors="surrogatepass")
    units = struct.unpack("<" + "H" * (len(raw) // 2), raw)
    value = "".join(chr(c) if 32 <= c <= 126 else "?" for c in units).strip()
    return (value or "mod")[:63]


def _find(root, relative):
    """Only fixed retail names or the validated configured episode are used."""
    path = root
    for component in relative.split("/"):
        if not path.is_dir():
            return None
        matches = [p for p in path.iterdir() if p.name.casefold() == component.casefold()]
        if len(matches) > 1:
            raise AssetPreparationError(f"Ambiguous filename case: {relative}")
        if not matches:
            return None
        path = matches[0]
        if path.is_symlink():
            raise AssetPreparationError(f"Stage regular asset files before sharing: {relative}")
    return path


def _stamp(path):
    s = path.stat()
    if not stat.S_ISREG(s.st_mode):
        raise AssetPreparationError(f"Not a regular asset file: {path.name}")
    return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns


def _read_stable(path, limit):
    before = _stamp(path)
    if before[2] > limit:
        raise AssetPreparationError(f"Asset exceeds the browser size limit: {path.name}")
    data = path.read_bytes()
    if len(data) != before[2] or _stamp(path) != before:
        raise AssetPreparationError(f"Asset changed while preparing: {path.name}")
    return data


def _parse_gob(read, size):
    if size < 16:
        return None
    header = read(0, 12)
    if len(header) != 12 or header[:4] != b"GOB " or struct.unpack_from("<I", header, 4)[0] != 20:
        return None
    offset = struct.unpack_from("<I", header, 8)[0]
    if offset + 4 > size:
        return None
    raw = read(offset, 4)
    if len(raw) != 4:
        return None
    count = struct.unpack("<I", raw)[0]
    if offset + 4 + count * GOB_ENTRY > size:
        return None
    table = read(offset + 4, count * GOB_ENTRY)
    if len(table) != count * GOB_ENTRY:
        return None
    entries = []
    for i in range(count):
        at = i * GOB_ENTRY
        start, length = struct.unpack_from("<Ii", table, at)
        if length < 0 or start + length > size:
            return None
        name = table[at + 8:at + GOB_ENTRY].split(b"\0", 1)[0].decode("latin-1")
        entries.append(Entry(start, length, name))
    return tuple(entries)


def parse_gob(data):
    return _parse_gob(lambda at, n: bytes(data[at:at + n]), len(data))


class RetailIndex:
    """Lookup by actual content, including installed-name aliases, not names."""
    def __init__(self, root, ext):
        self.by_size, self.stamps, self.hashed = {}, {}, {}
        seen = set()
        for relative in RETAIL_FILES[ext]:
            path = _find(root, relative)
            if not path or not path.is_file():
                continue
            stamp = _stamp(path)
            if stamp[:2] in seen:
                continue
            seen.add(stamp[:2])
            with path.open("rb") as f:
                def read(at, n):
                    f.seek(at)
                    return f.read(n)
                entries = _parse_gob(read, stamp[2])
            if entries is None:
                continue
            self.stamps[path] = stamp
            for entry in (*entries, Entry(0, stamp[2])):
                if entry.size:
                    self.by_size.setdefault(entry.size, []).append((path, entry))

    def matches(self, data):
        size = len(data)
        if size not in self.by_size:
            return None
        wanted = hashlib.sha256(data).digest()
        if size not in self.hashed:
            hashes = set()
            for path, entry in self.by_size[size]:
                if _stamp(path) != self.stamps[path]:
                    raise AssetPreparationError(f"Retail reference changed: {path.name}")
                h, remaining = hashlib.sha256(), entry.size
                with path.open("rb") as f:
                    f.seek(entry.offset)
                    while remaining:
                        part = f.read(min(1024 * 1024, remaining))
                        if not part:
                            raise AssetPreparationError(f"Incomplete retail reference: {path.name}")
                        h.update(part)
                        remaining -= len(part)
                if _stamp(path) != self.stamps[path]:
                    raise AssetPreparationError(f"Retail reference changed: {path.name}")
                hashes.add(h.digest())
            self.hashed[size] = hashes
        return wanted if wanted in self.hashed[size] else None


def plan_share(data, ranges, retail):
    """Reference table plus the complement of the union of retail ranges."""
    view, refs, custom = memoryview(data), [], 0
    for entry in ranges:
        if not entry.size:
            continue
        if entry.offset < 0 or entry.offset + entry.size > len(data):
            raise AssetPreparationError("Asset range is outside its archive")
        sha = retail.matches(view[entry.offset:entry.offset + entry.size])
        if sha is None:
            custom += 1
        else:
            refs.append((entry.offset, entry.size, sha))
    if not custom:
        return None, 0, 0, "retail-only"
    refs.sort(key=lambda r: (r[0], -r[1]))
    kept, end = [], 0
    for ref in refs:
        if kept and ref[0] + ref[1] <= end:
            continue
        kept.append(ref)
        end = max(end, ref[0] + ref[1])
    if len(kept) > MAX_REFS:
        return None, 0, 0, "too-many-files"
    refs_bytes = 4 + 40 * len(kept)
    chunks = [struct.pack("<I", len(kept))]
    chunks.extend(struct.pack("<II", offset, size) + sha for offset, size, sha in kept)
    pos = 0
    for offset, size, _ in kept:
        if offset > pos:
            chunks.append(view[pos:offset])
        pos = max(pos, offset + size)
    if pos < len(data):
        chunks.append(view[pos:])
    return b"".join(chunks), refs_bytes, len(kept), "ok"


def list_mod_files(root):
    if not root.is_dir() or root.is_symlink():
        raise AssetPreparationError("The staged active mod must be a regular directory")
    files = []
    def walk(directory, relative, depth):
        for child in directory.iterdir():
            rel = f"{relative}/{child.name}" if relative else child.name
            if not packable(rel):
                continue
            if child.is_symlink():
                raise AssetPreparationError(f"A mod asset is a symbolic link: {rel}")
            if child.is_dir():
                if depth >= MAX_DEPTH:
                    raise AssetPreparationError(f"Mod path exceeds the browser depth limit: {rel}")
                walk(child, rel, depth + 1)
            elif child.is_file():
                if not valid_relative_path(rel):
                    raise AssetPreparationError(f"Mod filename is not supported by the browser: {rel}")
                if child.name.casefold() == "jkmremasteredassets.goo":
                    raise AssetPreparationError("Keep JKMRemasteredAssets.goo in resource/, not the selected mod folder; the browser requires its own matching pack")
                files.append((rel, child, _stamp(child)[2]))
                if len(files) > 50000:
                    raise AssetPreparationError("The active mod exceeds 50,000 fingerprintable files")
            else:
                raise AssetPreparationError(f"Mod asset is not a regular file: {rel}")
    walk(root, "", 0)
    files.sort(key=lambda f: f[0])
    seen = set()
    for rel, _, _ in files:
        lower = rel.lower()
        if lower in seen:
            raise AssetPreparationError(f"Duplicate mod filename after case folding: {rel}")
        seen.add(lower)
    for rel, _, _ in files:
        parts = rel.lower().split("/")
        if any("/".join(parts[:i]) in seen for i in range(1, len(parts))):
            raise AssetPreparationError(f"Conflicting mod file and directory: {rel}")
    if sum(f[2] for f in files) > 1024**3:
        raise AssetPreparationError("The active mod exceeds the browser's 1 GiB fingerprint limit")
    return files


def pack_files(files):
    """Deterministic GOB pack; caller supplies the intended lexical order."""
    files = list(files)
    offset = 12 + sum(len(data) for _, data in files)
    out = bytearray(offset + 4 + GOB_ENTRY * len(files))
    struct.pack_into("<4sII", out, 0, b"GOB ", 20, offset)
    struct.pack_into("<I", out, offset, len(files))
    at, entries = 12, []
    for i, (name, data) in enumerate(files):
        if not valid_relative_path(name):
            raise AssetPreparationError(f"Invalid packed asset name: {name}")
        out[at:at + len(data)] = data
        row = offset + 4 + GOB_ENTRY * i
        struct.pack_into("<II", out, row, at, len(data))
        encoded = name.encode("ascii")
        out[row + 8:row + 8 + len(encoded)] = encoded
        entries.append(Entry(at, len(data), name))
        at += len(data)
    return bytes(out), tuple(entries)


def _pack_mod(files, download_enabled):
    """Fingerprint large local-only mods without allocating a 1 GiB pack."""
    payload_size = sum(f[2] for f in files)
    status = "too-many-files" if len(files) > MAX_MOD_FILES else "too-big" if payload_size > MAX_MOD_BYTES else "ok"
    table_offset = 12 + payload_size
    table = bytearray(4 + GOB_ENTRY * len(files))
    struct.pack_into("<I", table, 0, len(files))
    header = struct.pack("<4sII", b"GOB ", 20, table_offset)
    total = table_offset + len(table)
    out = bytearray(total) if status == "ok" and download_enabled else None
    if out is not None:
        out[:12] = header
    h, at, entries = hashlib.sha256(header), 12, []
    for i, (rel, path, size) in enumerate(files):
        before = _stamp(path)
        if before[2] != size:
            raise AssetPreparationError(f"Mod asset changed while preparing: {rel}")
        row = 4 + i * GOB_ENTRY
        struct.pack_into("<II", table, row, at, size)
        name = rel.encode("ascii")
        table[row + 8:row + 8 + len(name)] = name
        entries.append(Entry(at, size, rel))
        remaining = size
        with path.open("rb") as f:
            while remaining:
                part = f.read(min(1024 * 1024, remaining))
                if not part:
                    raise AssetPreparationError(f"Incomplete mod asset: {rel}")
                h.update(part)
                if out is not None:
                    out[at:at + len(part)] = part
                at += len(part)
                remaining -= len(part)
        if before != _stamp(path):
            raise AssetPreparationError(f"Mod asset changed while preparing: {rel}")
    h.update(table)
    if out is not None:
        out[table_offset:] = table
    return bytes(out) if out is not None else None, tuple(entries), h.hexdigest(), total, status


def mod_ranges(data, entries):
    ranges = []
    for entry in entries:
        ranges.append(entry)
        if not re.search(r"\.go[bo]$", entry.name, re.IGNORECASE):
            continue
        inner = parse_gob(memoryview(data)[entry.offset:entry.offset + entry.size])
        if inner:
            ranges.extend(Entry(entry.offset + e.offset, e.size) for e in inner)
    return ranges


def _check_effective_content(root, episode_name):
    """Reject active content outside the two advertised content namespaces."""
    allowed = {Path(p).name.casefold() for paths in RETAIL_FILES.values() for p in paths if p.startswith("resource/")}
    allowed.add("jkmremasteredassets.goo")
    def harmless(path):
        return (any(part.startswith(".") for part in path.relative_to(root).parts) or
                path.name.lower() in ("thumbs.db", "desktop.ini", "readme", "license", "copying", "authors", "credits", "changelog") or
                path.suffix.lower().lstrip(".") in EXCLUDED_EXTENSIONS | {"md", "rst", "nfo"} or path.suffix.lower() == ".cd")
    resource = _find(root, "resource")
    if resource:
        for path in resource.rglob("*"):
            if path.is_symlink():
                raise AssetPreparationError("Stage regular resource files before browser sharing")
            if not path.is_file() or harmless(path):
                continue
            if path.parent == resource and path.name.casefold() in allowed:
                continue
            raise AssetPreparationError(f"Unadvertised resource override: {path.relative_to(resource)}. Move custom assets into the configured active mod folder")
    root_mods = _find(root, "mods")
    if root_mods:
        for path in root_mods.rglob("*"):
            if path.is_symlink():
                raise AssetPreparationError("Stage regular mod files before browser sharing")
            if not path.is_file() or harmless(path):
                continue
            if path.parent == root_mods and path.name.casefold() == "jkmremasteredassets.goo":
                continue
            raise AssetPreparationError(f"Unadvertised mods/ override: {path.relative_to(root_mods)}. Use the configured active mod folder")
    loose_episode = _find(root, f"episode/{episode_name}")
    if loose_episode and loose_episode.is_dir() and any(p.is_file() and not harmless(p) for p in loose_episode.rglob("*")):
        raise AssetPreparationError("Loose selected-episode overrides cannot accompany browser sharing; put them in the selected episode archive or active mod folder")


@dataclass(frozen=True)
class Offer:
    kind: int
    info: dict
    stream: bytes | None = None
    retail_references: int = 0
    file_count: int = 0

    def __post_init__(self):
        object.__setattr__(self, "info", MappingProxyType(dict(self.info)))

    @property
    def identifier(self):
        sha = self.info.get("sha256")
        return bytes.fromhex(sha[:16]) if sha else None


def _offer(kind, name, ext, data, entries, retail, ranges=None):
    stream, refs_bytes, refs_count, status = plan_share(data, ranges if ranges is not None else entries, retail)
    info = {"status": status, "name": name, "ext": ext, "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}
    if stream is not None:
        info.update(streamSize=len(stream), refsBytes=refs_bytes)
    return Offer(kind, info, stream, refs_count, len(entries))


class AssetProvider:
    """Prepared byte snapshots; no request handler opens a source file."""
    def __init__(self, *, mode, episode_name, offers, mod_name="", session_tail=b"",
                 download_enabled=True, remastered=None):
        self.mode, self.episode_name = mode, episode_name
        self.offers = MappingProxyType(dict(offers))
        self.mod_name, self.session_tail = mod_name, session_tail
        self.download_enabled = bool(download_enabled)
        self.remastered = remastered

    def info(self, kind):
        offer = self.offers.get(kind)
        info = dict(offer.info) if offer else {"status": "none"}
        if kind == MOD and not self.download_enabled and info["status"] == "ok":
            info["status"] = "disabled"
        return info

    def find(self, identifier):
        if not self.download_enabled:
            return None
        return next((o for o in self.offers.values() if o.stream is not None and o.identifier == identifier), None)

    def summary(self):
        def describe(offer):
            if not offer:
                return None
            i = offer.info
            return {"name": i.get("name", ""), "ext": i.get("ext", ""),
                    "status": "disabled" if not self.download_enabled and i["status"] == "ok" else i["status"],
                    "size": i.get("size", 0), "sha256": i.get("sha256", ""),
                    "stream_size": i.get("streamSize", 0), "retail_references": offer.retail_references,
                    "file_count": offer.file_count}
        return {"download_enabled": self.download_enabled, "game": "mots" if self.mode else "jk",
                "map": describe(self.offers.get(MAP)), "mod": describe(self.offers.get(MOD)),
                "remastered": dict(self.remastered) if self.remastered else None}


def _build(game_root, episode_name, mode, mod_root, mod_name, download_enabled):
    if mode not in (0, 1) or not valid_episode_name(episode_name):
        raise AssetPreparationError("Invalid game mode or selected episode name")
    root = game_root.resolve(strict=True)
    _check_effective_content(root, episode_name)
    ext = "goo" if mode else "gob"
    retail = RetailIndex(root, ext)
    info, offers = {"name": episode_name, "ext": ext, "status": "none"}, {}
    episode = _find(root, f"episode/{episode_name}.{ext}")
    if episode_name.lower() in RETAIL_EPISODES:
        offers[MAP] = Offer(MAP, {**info, "status": "retail"})
    elif episode and episode.is_file():
        if _stamp(episode)[2] > MAX_MAP_BYTES:
            offers[MAP] = Offer(MAP, {**info, "status": "too-big"})
        else:
            data = _read_stable(episode, MAX_MAP_BYTES)
            entries = parse_gob(data)
            offers[MAP] = (_offer(MAP, episode_name, ext, data, entries, retail) if entries is not None
                           else Offer(MAP, {**info, "status": "not-gob"}))
    else:
        offers[MAP] = Offer(MAP, info)
    if not download_enabled and offers[MAP].stream is not None:
        old = offers[MAP]
        offers[MAP] = Offer(old.kind, old.info, None, old.retail_references, old.file_count)
    fingerprint = None
    if mod_root is not None:
        files = list_mod_files(mod_root)
        data, entries, sha, total, status = _pack_mod(files, download_enabled)
        mod_name = clean_mod_name(mod_name or mod_root.name)
        offer = (_offer(MOD, mod_name, ext, data, entries, retail, mod_ranges(data, entries))
                 if data is not None else Offer(MOD, {"status": status, "name": mod_name,
                            "ext": ext, "size": total, "sha256": sha}, file_count=len(entries)))
        offers[MOD] = offer
        fingerprint = bytes.fromhex(sha)
    else:
        mod_name = ""
    remastered, pack_fingerprint = None, b""
    if mode:
        for dirname in ("mods", "resource"):
            pack = _find(root, dirname + "/JKMRemasteredAssets.goo")
            if pack and pack.is_file():
                h, before = hashlib.sha256(), _stamp(pack)
                with pack.open("rb") as f:
                    for part in iter(lambda: f.read(1024 * 1024), b""):
                        h.update(part)
                if before != _stamp(pack):
                    raise AssetPreparationError("Remastered pack changed while preparing")
                pack_fingerprint = h.digest()[:16]
                remastered = {"name": "JKMRemasteredAssets.goo", "status": "local-required",
                              "size": before[2], "sha256": h.hexdigest(), "fingerprint": pack_fingerprint.hex()}
                break
    tail = b""
    if fingerprint or pack_fingerprint:
        name = mod_name.encode("ascii") if fingerprint else b""
        flags = (1 if fingerprint else 0) | (2 if pack_fingerprint else 0)
        tail = b"JKMD" + bytes((2, flags, len(name))) + (fingerprint or b"") + pack_fingerprint + name
    return AssetProvider(mode=mode, episode_name=episode_name, offers=offers, mod_name=mod_name,
                         session_tail=tail, download_enabled=download_enabled, remastered=remastered)


async def build_asset_provider(game_root, episode_name, mode, mod_root=None, mod_name="", download_enabled=True):
    """Build off-loop before engine launch, from a regular staged content tree."""
    return await asyncio.to_thread(_build, Path(game_root), episode_name, mode,
                                   Path(mod_root) if mod_root is not None else None,
                                   mod_name, download_enabled)


def frame(message_type, destination, kind, body=b""):
    return struct.pack("<II4sBBBB", 1, destination, MAGIC, message_type, VERSION, kind, 0) + body


def info_frame(provider, destination, kind):
    body = json.dumps(provider.info(kind), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return frame(INFO, destination, kind, body)


def chunk_frames(provider, destination, packet):
    """Yield only the requested range; the hash chooses between current offers."""
    if len(packet) != HEADER + 20:
        return
    offer = provider.find(packet[HEADER:HEADER + 8])
    if offer is None:
        return
    size, first, count = struct.unpack_from("<III", packet, HEADER + 8)
    if size not in (CHUNK_DIRECT, CHUNK_RELAY):
        return
    count = min(count, MAX_CHUNKS_PER_REQUEST)
    for index in range(first, min(first + count, (len(offer.stream) + size - 1) // size)):
        part = offer.stream[index * size:(index + 1) * size]
        yield frame(CHUNK, destination, offer.kind, offer.identifier + struct.pack("<I", index) + part)

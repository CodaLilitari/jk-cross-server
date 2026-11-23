#!/usr/bin/env python3
"""Preserve a stopped memory run as disjoint archives and a create-only receipt.

Existing build inputs are supplied by the pinned public outcome build archive.
Only model.json and policy.py from model artifact directories may be public.
The evidence archive contains the remaining raw files, beneath the run name.
"""
import argparse
from contextlib import ExitStack
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tarfile
from tempfile import NamedTemporaryFile


BUILD_SHA256 = "6c0cc363ca28040eaec778031bd154249152f1783483b8b56bf288ed9b9febb6"
LICENSES = {"licenses/MIT.txt", "licenses/OpenJKDF2-LICENSE.md"}
MODEL_FILES = {"model.json", "policy.py"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def safe_name(name):
    require(all(part not in ("", ".", "..") and re.fullmatch(r"[A-Za-z0-9._+-]+", part)
                for part in name.split("/")), f"unsafe relative name {name!r}")
    return name


def record(stream):
    digest = hashlib.sha256()
    size = 0
    while chunk := stream.read(1024 * 1024):
        digest.update(chunk)
        size += len(chunk)
    return {"bytes": size, "sha256": digest.hexdigest()}


def file_record(path):
    with path.open("rb") as stream:
        return record(stream)


def raw_inventory(root):
    inventory = {}
    modes = {}
    # iterdir propagates filesystem errors. Refuse all symlinks, including directories.
    def visit(directory):
        for path in directory.iterdir():
            name = safe_name(path.relative_to(root).as_posix())
            mode = path.lstat().st_mode
            if stat.S_ISDIR(mode):
                visit(path)
            else:
                require(stat.S_ISREG(mode), f"indirect or non-regular input {name}")
                inventory[name] = file_record(path)
                modes[name] = stat.S_IMODE(mode)
    visit(root)
    return inventory, modes


def canonical(value):
    # Matches motor_memory.json_bytes and the run's raw_inventory_sha256 definition.
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def model_members(run, names):
    groups = {}
    for name in names:
        if name.startswith("models/"):
            bits = name.split("/")
            require(len(bits) == 3 and bits[2] in MODEL_FILES, f"unexpected model file {name}")
            groups.setdefault(bits[1], set()).add(bits[2])
            data = (run / name).read_bytes()
            data.decode("utf-8")
            require(not any(marker in data for marker in (os.fsencode(run), b"/tmp/", b"/workspace/",
                        b"/home/", b"map.numeric", b"build/replay")), f"private reference in {name}")
    require(groups and all(files == MODEL_FILES for files in groups.values()), "incomplete model pair")
    return {f"models/{artifact}/{member}" for artifact, files in groups.items() for member in files}


def archive_members(path, prefix="", licenses=False):
    records = {}
    modes = {}
    extra = {}
    with tarfile.open(path, "r|gz") as archive:
        for info in archive:
            name = safe_name(info.name)
            require(info.isreg() and not info.issparse(), f"non-regular archive member {name}")
            require(name.startswith(prefix), f"unexpected member prefix {name}")
            name = safe_name(name[len(prefix):])
            require(name not in records and name not in extra, f"duplicate archive member {name}")
            with archive.extractfile(info) as stream:
                data = record(stream)
            require(data["bytes"] == info.size, f"archive member length {name}")
            if licenses and name in LICENSES:
                extra[name] = data
            else:
                records[name] = data
                modes[name] = info.mode
    return records, modes, extra


def verify_members(records, modes, expected, raw, raw_modes):
    require(set(records) == expected, "archive file selection mismatch")
    for name, data in records.items():
        require(data == raw[name] and modes[name] == raw_modes[name], f"member mismatch {name}")


def write_archive(path, run, expected, raw, modes, prefix):
    with path.open("wb") as output, gzip.GzipFile(filename="", fileobj=output, mode="wb", mtime=0,
                                                 compresslevel=6) as compressed:
        with tarfile.open(fileobj=compressed, mode="w|", format=tarfile.PAX_FORMAT) as archive:
            for name in sorted(expected):
                info = tarfile.TarInfo(prefix + name)
                info.mode = modes[name]
                info.size = raw[name]["bytes"]
                with (run / name).open("rb") as stream:
                    archive.addfile(info, stream)


def archive_record(output, staged, members, inventory):
    return {"filename": output.name, **file_record(staged), "raw_files": len(members),
            "raw_bytes": sum(inventory[name]["bytes"] for name in members)}


def preserve(run, build, candidates, evidence, receipt):
    run = run.absolute()
    build = build.absolute()
    require(run.resolve(strict=True) == run and run.is_dir(), "indirect run directory")
    require(build.resolve(strict=True) == build and build.is_file(), "indirect build archive")
    prefix = safe_name(run.name) + "/"
    outputs = [path.absolute() for path in (candidates, evidence, receipt)]
    require(len(set(outputs)) == len(outputs), "overlapping output paths")
    for dst in outputs:
        require(dst.parent.resolve(strict=True) == dst.parent, "indirect output parent")
        require(not dst.is_relative_to(run), "output within raw inventory")
        if os.path.lexists(dst):
            raise FileExistsError(dst)

    raw, modes = raw_inventory(run)
    models = model_members(run, raw)
    require(file_record(build)["sha256"] == BUILD_SHA256, "public build archive digest mismatch")
    reused, build_modes, licenses = archive_members(build, licenses=True)
    require(set(licenses) == LICENSES and len(reused) == 96 and
            all(name.startswith("build/") and name in raw for name in reused), "unexpected build archive")
    verify_members(reused, build_modes, set(reused), raw, modes)
    rest = set(raw) - models - set(reused)
    require(len(raw) == len(rest) + len(models) + len(reused), "overlapping member selections")

    with ExitStack() as temporary:
        staged = []
        for dst in outputs:
            with NamedTemporaryFile(dir=dst.parent, prefix="." + dst.name + ".", delete=False) as handle:
                temp = Path(handle.name)
            temporary.callback(temp.unlink, missing_ok=True)
            staged.append(temp)
        for temp, selected, member_prefix in [(staged[0], models, ""), (staged[1], rest, prefix)]:
            write_archive(temp, run, selected, raw, modes, member_prefix)
            restored, archived_modes, _ = archive_members(temp, member_prefix)
            verify_members(restored, archived_modes, selected, raw, modes)
        require((raw, modes) == raw_inventory(run), "raw inventory changed while archiving")
        summary = {
            "schema": 1, "run": run.name, "raw_inventory_sha256": hashlib.sha256(canonical(raw)).hexdigest(),
            "raw_inventory_encoding": "SHA-256 of UTF-8 JSON mapping relative path to {bytes,sha256}; sorted keys, compact separators, no trailing newline",
            "retained_files": len(raw), "retained_bytes": sum(r["bytes"] for r in raw.values()),
            "archives": {
                "candidates": {**archive_record(outputs[0], staged[0], models, raw),
                               "model_artifacts": len(models) // 2, "member_prefix": ""},
                "existing_build_inputs": {**archive_record(build, build, reused, raw), "member_prefix": "",
                                          "archive_members": len(reused) + len(licenses),
                                          "excluded_license_members": licenses},
                "private_evidence": {**archive_record(outputs[1], staged[1], rest, raw),
                                     "member_prefix": prefix,
                                     "additional_build_files": sum(n.startswith("build/") for n in rest)}
            }
        }
        staged[2].write_text(json.dumps(summary, sort_keys=True, indent=2, allow_nan=False) + "\n",
                             encoding="utf-8")
        # Link complete files without clobbering preexisting output. Publish the receipt last.
        with ExitStack() as rollback:
            for temp, dst, mode in zip(staged, outputs, (0o644, 0o600, 0o644)):
                temp.chmod(mode)
                os.link(temp, dst)
                rollback.callback(dst.unlink)
            rollback.pop_all()
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("run", "build", "candidates", "evidence", "receipt"):
        parser.add_argument("--" + flag, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(preserve(**vars(args)), indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Verify and install a caller-supplied, hashed eight-file JKWeb runtime overlay.

An overlay is a diagnostic runtime snapshot, not a complete Git checkout.
The payload format is the gzip JSON envelope used by the refinement trials.
"""
import argparse
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

ALLOWED = {"web_bots/index.html", "bin/bots-jkweb/openjkdf2.js", "bin/bots-jkweb/openjkdf2.wasm",
           "web_bots/BUILD.json", "web_bots/serve.py", "web_bots/client.js", "web_bots/launch_chrome.py",
           "bots/companion.py"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def install(base, target, payload, expected_base, expected_commit, expected_size, expected_sha):
    base, target = base.resolve(), target.resolve()
    if target.exists() or target == base or base in target.parents:
        raise ValueError("Use a new destination outside the baseline checkout")
    prior = json.loads((base / "deployed-build.json").read_text())
    if prior["commit"] != expected_base or set(prior["files"]) != ALLOWED:
        raise ValueError("Unexpected baseline identity or file set")
    for name, digest in prior["files"].items():
        if sha((base / name).read_bytes()) != digest:
            raise ValueError("Baseline differs: " + name)
    data = payload.read_bytes()
    if len(data) != expected_size or sha(data) != expected_sha:
        raise ValueError("Overlay payload size or digest differs")
    bundle = json.loads(gzip.decompress(data))
    manifest = bundle["manifest"]
    if (manifest["commit"] != expected_commit or set(manifest["files"]) != ALLOWED
            or set(bundle["files"]) != ALLOWED):
        raise ValueError("Unexpected overlay identity or file set")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="runtime-overlay-", dir=target.parent) as temp:
        staged = Path(temp) / "checkout"
        shutil.copytree(base, staged, ignore=shutil.ignore_patterns("__pycache__", ".git"))
        for name, encoded in bundle["files"].items():
            data = base64.b64decode(encoded, validate=True)
            if sha(data) != manifest["files"][name]:
                raise ValueError("Runtime file digest differs: " + name)
            file = staged / name
            if staged not in file.resolve().parents:
                raise ValueError("Runtime file escapes staged checkout")
            file.write_bytes(data)
        (staged / "deployed-build.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        if target.exists():
            raise FileExistsError("Destination appeared during installation")
        os.rename(staged, target)
    return {"commit": expected_commit, "runtime_files_verified": len(ALLOWED),
            "wasm_sha256": manifest["files"]["bin/bots-jkweb/openjkdf2.wasm"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-checkout", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--payload", required=True, type=Path)
    parser.add_argument("--base-commit", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--bytes", required=True, type=int)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    print(json.dumps(install(args.base_checkout, args.target, args.payload, args.base_commit,
                             args.commit, args.bytes, args.sha256)))


if __name__ == "__main__":
    main()

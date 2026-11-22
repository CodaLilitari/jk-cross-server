#!/usr/bin/env python3
"""Check packaged JKWeb artifacts, apply the pinned patch, and reproduce the relink.

The source checkout is read only. Temporary verification files are retained at the
printed stage directory. No tracked QA receipt is rewritten by this helper.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def child(root, name):
    path = (root / name).resolve()
    if root not in path.parents:
        raise ValueError("Manifest path escapes its root: " + name)
    return path


def verify(root, engine, work_dir=None, source_only=False, compiler=None):
    root, engine = root.resolve(), engine.resolve()
    manifest_path = root / "web_bots/BUILD.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    for name, expected in manifest["files"].items():
        data = child(root, name).read_bytes()
        if len(data) != expected["bytes"] or sha(data) != expected["sha256"]:
            raise ValueError("Packaged input differs: " + name)
    if work_dir:
        work_dir.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="jk-web-verify-", dir=work_dir))
    source = stage / "source"
    source.mkdir()
    archive = subprocess.check_output(["git", "archive", manifest["base_commit"]], cwd=engine)
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
        stream.extractall(source, filter="data")
    patch = child(root, manifest["patch"])
    subprocess.run(["git", "apply", "--check", str(patch)], cwd=source, check=True)
    subprocess.run(["git", "apply", str(patch)], cwd=source, check=True)
    for name, expected in manifest["changed_sources"].items():
        if sha(child(source, name).read_bytes()) != expected:
            raise ValueError("Patched source hash differs: " + name)
    relink_result = None
    if not source_only:
        relink = stage / "relink"
        relink.mkdir()
        with tarfile.open(child(root, manifest["relink"])) as stream:
            stream.extractall(relink, filter="data")
        config = json.loads((relink / "link.json").read_text())
        command = list(config["link"])
        if compiler:
            command[0] = str(compiler.resolve())
        version = subprocess.check_output([command[0], "--version"], text=True)
        if manifest["emscripten"] not in version.splitlines()[0].split():
            raise ValueError("Emscripten version differs from BUILD.json")
        with (stage / "relink.log").open("w") as log:
            subprocess.run(command, cwd=relink, stdout=log, stderr=subprocess.STDOUT, check=True)
        for name in ("openjkdf2.js", "openjkdf2.wasm"):
            expected = manifest["files"]["bin/bots-jkweb/" + name]["sha256"]
            if sha((relink / name).read_bytes()) != expected:
                raise ValueError("Independent relink differs: " + name)
        relink_result = {"js_byte_identical": True, "wasm_byte_identical": True,
                         "recompiled_libsmacker": False}
    if manifest_path.read_bytes() != manifest_bytes:
        raise ValueError("Build manifest changed during verification")
    return {"schema": 1, "engine_repository": manifest["repository"],
            "engine_base_commit": manifest["base_commit"], "emscripten": manifest["emscripten"],
            "clean_pinned_source_accepts_patch": True,
            "changed_source_hashes_verified": len(manifest["changed_sources"]),
            "files": manifest["files"], "independent_direct_relink": relink_result,
            "source_only": source_only, "stage": str(stage),
            "live_multiplayer_tested": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True, help="jk-cross-server checkout")
    parser.add_argument("--engine", type=Path, required=True, help="Engine Git checkout containing the pinned base commit")
    parser.add_argument("--work-dir", type=Path, help="Parent of retained temporary verification files")
    parser.add_argument("--compiler", type=Path, help="Exact pinned em++ executable; SDK environment must already be configured")
    parser.add_argument("--source-only", action="store_true", help="Verify package and source; explicitly skip relinking")
    parser.add_argument("--receipt", type=Path, help="Optional new result JSON; existing files are not overwritten")
    args = parser.parse_args()
    result = verify(args.repo, args.engine, args.work_dir, args.source_only, args.compiler)
    if args.receipt:
        with args.receipt.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

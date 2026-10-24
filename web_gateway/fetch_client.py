"""Fetch an unchanged, hash-pinned published JKDF2Web build.

Downloads only HTML, JavaScript and WebAssembly engine code. No retail data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

BUILD_COMMIT = "24dc3876f32eff57c8ca98ef657698d1a30170c7"
ENGINE_SOURCE_COMMIT = "a7c0211ca408eabd97a7c82fbdcae9450c3a0b9c"
BASE = f"https://raw.githubusercontent.com/tristamus/jkdf2mp-bb-server/{BUILD_COMMIT}/cloudflare-38/public/"
FILES = {
    "index.html": (226513, "e470d21e3a351d3630b2b414ad4cd0410cbd51fde7ead772a6298e7a7a17acdc"),
    "openjkdf2.js": (532943, "4ae0de474cc2ae817c6162fe21a6ac4b73c573d311884253cf002aedc6a46bb0"),
    "openjkdf2.wasm": (3681717, "5f40d53acb6c92d11fb87342a9d06b5457f533603329bc59349298f6edfe28b6"),
}


def fetch(destination: Path) -> dict:
    destination.mkdir(parents=True, exist_ok=True)
    results = []
    for name, (size, digest) in FILES.items():
        path = destination / name
        data = path.read_bytes() if path.is_file() else b""
        if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
            request = urllib.request.Request(BASE + name, headers={"User-Agent": "JK-Cross-Server/0.1"})
            with urllib.request.urlopen(request, timeout=60) as response:
                data = response.read(size + 1)
            if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
                raise RuntimeError(f"Published build verification failed for {name}")
            temporary = destination / (name + ".download")
            temporary.write_bytes(data)
            temporary.replace(path)
        results.append({"name": name, "size": size, "sha256": digest, "modified": False})
    record = {"repository": "https://github.com/tristamus/jkdf2mp-bb-server",
              "build": "cloudflare-38", "commit": BUILD_COMMIT, "files": results,
              "engine_source_commit": ENGINE_SOURCE_COMMIT,
              "retail_assets_included": False}
    (destination / "client-provenance.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--destination", type=Path, default=Path("runtime/browser-client"))
    args = parser.parse_args()
    print(json.dumps(fetch(args.destination), indent=2))


if __name__ == "__main__":
    main()

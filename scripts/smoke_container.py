#!/usr/bin/env python3
"""Exercise the real packaged panel through Docker; no commercial game data needed."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], check=check, capture_output=True,
                          text=True, timeout=90)


def request(path="/", *, token=None, method="GET", data=None, headers=None):
    values = dict(headers or {})
    if token:
        values["Authorization"] = "Bearer " + token
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        values["Content-Type"] = "application/json"
    req = urllib.request.Request("http://127.0.0.1:8765" + path, data=body,
                                 headers=values, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def wait_for_panel():
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            status, html = request()
            match = re.search(rb'<meta name="admin-token" content="([^"]+)"', html)
            if status == 200 and match:
                return match.group(1).decode()
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(1)
    raise RuntimeError("Container control panel did not become ready within 60 seconds")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    name = "jk-cross-smoke-" + uuid.uuid4().hex[:12]
    volume = name + "-app"
    state_volume = name + "-state"
    with tempfile.TemporaryDirectory(prefix="jk-cross-smoke-") as directory:
        root = Path(directory)
        game = root / "game"
        game.mkdir()
        try:
            for attempt in range(2):
                docker("run", "--detach", "--name", name, "--platform", "linux/amd64",
                       "--publish", "127.0.0.1:8765:8766",
                       "--mount", f"type=bind,src={game},dst=/game-data,readonly",
                       "--mount", f"type=volume,src={state_volume},dst=/data",
                       "--mount", f"type=volume,src={volume},dst=/app", args.image)
                token = wait_for_panel()
                assert request("/api/status")[0] == 401, "Unauthenticated API request was accepted"
                assert request(headers={"Host": "example.invalid:8765"})[0] == 403
                assert request(headers={"Origin": "https://example.invalid"})[0] == 403
                assert request("/api/status", token=token)[0] == 200
                status, raw = request("/api/config", token=token)
                assert status == 200
                config = json.loads(raw)
                assert config["game_data"] == "/game-data"
                assert config["spectator_rendering"] is True
                assert config["web_bind"] == "0.0.0.0"
                if attempt == 0:
                    config["name"] = "Persisted smoke setting"
                    assert request("/api/config", token=token, method="PUT", data=config)[0] == 200
                    for binary in ("/app/bin/linux-x86_64/openjkdf2",
                                   "/app/bin/bots-linux-x86_64/jk-bot-client"):
                        result = docker("exec", name, "ldd", binary)
                        assert "not found" not in result.stdout, result.stdout
                        docker("exec", name, "test", "-x", binary)
                else:
                    assert config["name"] == "Persisted smoke setting", "Restart overwrote saved settings"
                docker("stop", "--time", "15", name)
                result = docker("inspect", "--format", "{{.State.ExitCode}}", name)
                assert result.stdout.strip() == "0", "Container did not shut down cleanly"
                docker("rm", name)
            print("PASS: real container panel, authentication, same-origin guard, both engine dependencies, settings persistence and graceful shutdown")
        except BaseException:
            logs = docker("logs", "--tail", "60", name, check=False)
            print(logs.stdout, logs.stderr)
            raise
        finally:
            docker("rm", "--force", name, check=False)
            docker("volume", "rm", volume, check=False)
            docker("volume", "rm", state_volume, check=False)


if __name__ == "__main__":
    main()

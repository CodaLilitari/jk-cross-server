"""Exercise platform archives and launchers without Docker or commercial data."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts/build_platform_releases.py"
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")
# Windows' bash.exe alias starts WSL; use Git Bash explicitly there.
SHELL = (str(Path("C:/Program Files/Git/bin/bash.exe"))
         if os.name == "nt" and Path("C:/Program Files/Git/bin/bash.exe").is_file()
         else shutil.which("sh") if os.name != "nt" else None)


class PlatformArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.payload = {
            "VERSION": b"0.4.0-dev\n", "app.py": b"# fixture server\n",
            "LICENSE": b"fixture license\n", "NOTICE.md": b"fixture credit\n",
            "manager/spectator.py": b"# fixture spectator\n",
            "bots/run.py": b"# fixture bot manager\n",
            "web_gateway/requirements-lock.txt": b"aiohttp==3.13.0\n",
            "bin/linux-x86_64/openjkdf2": b"fixture native engine\n",
            "bin/linux-x86_64/libGameNetworkingSockets.so": b"fixture native library\n",
            "bin/bots-linux-x86_64/jk-bot-client": b"fixture bot engine\n",
            "bin/bots-linux-x86_64/libGameNetworkingSockets.so": b"fixture bot library\n",
            "Start-Server.ps1": b"# fixture windows launcher\n",
            "Start-Server.command": b"#!/bin/sh\n",
            "start-server.sh": b"#!/bin/sh\n",
            "packaging/Dockerfile": b"FROM ubuntu:24.04\n",
            "packaging/compose.yaml": b"services: {}\n",
            "packaging/container_runtime.py": b"# fixture runtime\n",
            ".dockerignore": b".git\n", "docs/PLATFORMS.md": b"Fixture setup instructions\n",
        }
        self.executable = {"start-server.sh", "Start-Server.command",
                           "bin/linux-x86_64/openjkdf2", "bin/bots-linux-x86_64/jk-bot-client"}

    def updater(self, *, extra=None, tamper=False):
        manifest = {"schema": 1, "version": "0.4.0-dev", "files": {
            name: {"sha256": hashlib.sha256(data).hexdigest(),
                   "mode": 0o755 if name in self.executable else 0o644}
            for name, data in sorted(self.payload.items())
        }}
        files = dict(self.payload)
        files["release-manifest.json"] = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
        files["SHA256SUMS"] = "".join(
            f"{hashlib.sha256(data).hexdigest()}  {name}\n"
            for name, data in sorted(files.items())
        ).encode()
        self.expected = files.copy()
        if tamper:
            files["app.py"] = b"tampered after manifest\n"
        path = self.directory / "updater.zip"
        with zipfile.ZipFile(path, "w") as archive:
            for name, data in files.items():
                info = zipfile.ZipInfo("jk-cross-server/" + name)
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | (0o755 if name in self.executable else 0o644)) << 16
                archive.writestr(info, data)
            if extra:
                name, mode = extra
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = mode << 16
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", message="Duplicate name:", category=UserWarning)
                    archive.writestr(info, b"unexpected entry")
        return path

    def build(self, archive, output="output"):
        self.assertTrue(BUILDER.is_file(), "Platform release builder is missing")
        return subprocess.run([sys.executable, str(BUILDER), "--input", str(archive),
                               "--output-dir", str(self.directory / output)],
                              text=True, capture_output=True, timeout=30)

    def test_all_archives_preserve_complete_payload_modes_and_checksums(self):
        source = self.updater()
        first = self.build(source)
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.build(source, "repeat")
        self.assertEqual(second.returncode, 0, second.stderr)
        for platform in ("windows-docker", "macos-docker", "linux-x86_64"):
            name = f"JK_Cross_Server_0.4.0-dev-{platform}.zip"
            path = self.directory / "output" / name
            self.assertEqual(path.read_bytes(), (self.directory / "repeat" / name).read_bytes())
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(path.with_suffix(".zip.sha256").read_text(), f"{digest}  {name}\n")
            with zipfile.ZipFile(path) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(set(archive.namelist()),
                                 {"jk-cross-server/" + item for item in self.expected}
                                 | {"jk-cross-server/PLATFORM-README.md"})
                for item, data in self.expected.items():
                    self.assertEqual(archive.read("jk-cross-server/" + item), data)
                for item in self.executable:
                    mode = archive.getinfo("jk-cross-server/" + item).external_attr >> 16
                    self.assertTrue(stat.S_ISREG(mode))
                    self.assertEqual(stat.S_IMODE(mode), 0o755)
                readme = archive.read("jk-cross-server/PLATFORM-README.md").decode()
                self.assertIn("docs/PLATFORMS.md", readme)
                self.assertIn("0.4.0-dev", readme)

    def test_unsafe_or_ambiguous_archive_paths_are_rejected(self):
        for name in ("jk-cross-server/../../escape", "/absolute", "outside/app.py",
                     "jk-cross-server/a\\b", "jk-cross-server/C:bad",
                     "jk-cross-server/APP.py", "jk-cross-server/app.py"):
            with self.subTest(name=name):
                result = self.build(self.updater(extra=(name, stat.S_IFREG | 0o644)))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Platform release build failed", result.stderr)
                self.assertFalse((self.directory / "output").exists())

    def test_symlinks_are_rejected_without_extracting(self):
        result = self.build(self.updater(extra=("jk-cross-server/link", stat.S_IFLNK | 0o777)))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("regular", result.stderr)
        self.assertFalse((self.directory / "output").exists())

    def test_windows_ambiguous_names_are_rejected_even_when_manifested(self):
        for name in ("docs/file.", "docs/file ", "docs/CON.txt", "docs/file?.txt"):
            with self.subTest(name=name):
                self.payload[name] = b"unsafe on Windows\n"
                result = self.build(self.updater())
                del self.payload[name]
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Unsafe archive path", result.stderr)
                self.assertFalse((self.directory / "output").exists())

    def test_tampered_payload_is_rejected(self):
        result = self.build(self.updater(tamper=True))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checksum", result.stderr.lower())

    def test_incomplete_engine_payload_is_rejected(self):
        del self.payload["bin/bots-linux-x86_64/jk-bot-client"]
        result = self.build(self.updater())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("jk-bot-client", result.stderr)

    def test_missing_executable_mode_requires_fixed_updater(self):
        self.executable.remove("start-server.sh")
        result = self.build(self.updater())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Executable permission", result.stderr)

    def test_output_in_checkout_is_rejected(self):
        (self.directory / "checkout/.git").mkdir(parents=True)
        result = self.build(self.updater(), "checkout/releases")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("outside a Git checkout", result.stderr)
        self.assertFalse((self.directory / "checkout/releases").exists())

    def test_unmanifested_member_is_rejected(self):
        result = self.build(self.updater(extra=("jk-cross-server/new.py", stat.S_IFREG | 0o644)))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exact payload", result.stderr)


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="jk launcher ")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.game = self.directory / "game data $literal & stuff"
        self.game.mkdir()
        self.state = self.directory / "state files $literal & stuff"
        self.record = self.directory / "docker-calls.jsonl"
        self.package = self.directory / "server package $literal & stuff"
        (self.package / "packaging").mkdir(parents=True)
        (self.package / "packaging/compose.yaml").write_text("services: {}\n")

    def records(self):
        return [json.loads(line) for line in self.record.read_text(encoding="utf-8-sig").splitlines()]

    def powershell_run(self, action, mode="ok"):
        launcher = ROOT / "Start-Server.ps1"
        self.assertTrue(launcher.is_file(), "PowerShell launcher is missing")
        shutil.copyfile(launcher, self.package / launcher.name)
        launcher = self.package / launcher.name
        runner = self.directory / "run.ps1"
        runner.write_text("""param($Launcher, $Game, $State, $Log, $Action, $Mode)
$env:JK_TEST_LOG = $Log
$env:JK_TEST_DOCKER_MODE = $Mode
function global:docker {
    [pscustomobject]@{ args = @($args); game = $env:JK_GAME_DATA; state = $env:JK_STATE_DIR } |
        ConvertTo-Json -Compress | Add-Content -LiteralPath $env:JK_TEST_LOG -Encoding utf8
    $global:LASTEXITCODE = 0
    if ($args[0] -eq 'info') {
        if ($env:JK_TEST_DOCKER_MODE -eq 'windows') { 'windows' } else { 'linux' }
    }
    if ($args[0] -eq 'compose' -and $args[1] -eq 'version') { '2.32.0' }
    if ($args -contains 'up' -and $env:JK_TEST_DOCKER_MODE -eq 'fail') { $global:LASTEXITCODE = 23 }
}
& $Launcher -GameData $Game -StateDir $State -Command $Action
exit $LASTEXITCODE
""", encoding="utf-8")
        args = [POWERSHELL, "-NoProfile", "-File", str(runner), str(launcher),
                str(self.game) if action == "start" else "missing game folder",
                str(self.state), str(self.record), action, mode]
        return subprocess.run(args, text=True, capture_output=True, timeout=30)

    @unittest.skipUnless(POWERSHELL, "PowerShell is not installed")
    def test_powershell_preserves_literal_paths_and_stops_without_game_data(self):
        for action in ("start", "stop"):
            result = self.powershell_run(action)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = self.records()
        start = next(row for row in calls if "up" in row["args"])
        self.assertEqual(Path(start["game"]), self.game.resolve())
        self.assertEqual(Path(start["state"]), self.state.resolve())
        compose_index = start["args"].index("-f") + 1
        self.assertEqual(Path(start["args"][compose_index]), self.package / "packaging/compose.yaml")
        self.assertEqual(start["args"][-3:], ["up", "--build", "-d"])
        self.assertEqual(calls[-1]["args"], ["stop", "jk-cross-server"])
        self.assertTrue(self.state.is_dir())

    @unittest.skipUnless(POWERSHELL, "PowerShell is not installed")
    def test_powershell_rejects_windows_containers_and_reports_start_failure(self):
        windows = self.powershell_run("start", "windows")
        self.assertNotEqual(windows.returncode, 0)
        self.assertIn("Linux containers", windows.stderr)
        self.assertFalse(any("up" in row["args"] for row in self.records()))
        failed = self.powershell_run("start", "fail")
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("exit 23", failed.stderr)

    def unix_run(self, action, mode="ok", mac=False):
        launcher = ROOT / "start-server.sh"
        mac_launcher = ROOT / "Start-Server.command"
        self.assertTrue(launcher.is_file(), "Unix launcher is missing")
        self.assertTrue(mac_launcher.is_file(), "macOS launcher is missing")
        for script in (launcher, mac_launcher):
            shutil.copyfile(script, self.package / script.name)
        fake_bin = self.directory / "fake-bin"
        fake_bin.mkdir(exist_ok=True)
        # Capture the external process boundary; never invoke a Docker daemon.
        fake = fake_bin / "docker"
        fake.write_text("""#!/bin/sh
printf '%s\\n' "$JK_GAME_DATA" "$JK_STATE_DIR" "$@" >> "$JK_TEST_LOG"
printf '%s\\n' '--END--' >> "$JK_TEST_LOG"
case "$1" in
  info)
    case "$JK_TEST_DOCKER_MODE" in windows) printf '%s\\n' windows ;; *) printf '%s\\n' linux ;; esac ;;
esac
for argument in "$@"; do
  if [ "$argument" = up ] && [ "$JK_TEST_DOCKER_MODE" = fail ]; then exit 23; fi
done
exit 0
""", encoding="utf-8", newline="\n")
        fake.chmod(0o755)
        env = os.environ.copy()
        env["PATH"] = str(fake_bin) + os.pathsep + env["PATH"]
        env["JK_TEST_LOG"] = str(self.record)
        env["JK_TEST_DOCKER_MODE"] = mode
        env["MSYS_NO_PATHCONV"] = "1"
        env.pop("JK_GAME_DATA", None)
        env.pop("JK_STATE_DIR", None)
        command = [SHELL, str(self.package / (mac_launcher.name if mac else launcher.name)), action]
        if action == "start":
            command += ["--game-data", str(self.game), "--state-dir", str(self.state)]
        return subprocess.run(command, text=True, capture_output=True, env=env, timeout=30)

    @unittest.skipUnless(SHELL, "A POSIX shell is not installed")
    def test_unix_launchers_preserve_paths_and_forward_commands(self):
        for action in ("start", "stop"):
            result = self.unix_run(action, mac=(action == "stop"))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = [part.splitlines() for part in self.record.read_text().split("--END--\n") if part]
        start = next(row for row in calls if "up" in row)
        # Git Bash represents host paths as /c/...; retain the literal path suffix.
        self.assertTrue(start[0].endswith(self.game.name), start)
        self.assertTrue(start[1].endswith(self.state.name), start)
        self.assertEqual(start[-3:], ["up", "--build", "-d"])
        self.assertEqual(calls[-1][-2:], ["stop", "jk-cross-server"])
        self.assertTrue(self.state.is_dir())

    @unittest.skipUnless(SHELL, "A POSIX shell is not installed")
    def test_unix_rejects_windows_containers_and_propagates_start_failure(self):
        windows = self.unix_run("start", "windows")
        self.assertNotEqual(windows.returncode, 0)
        self.assertIn("Linux containers", windows.stderr)
        self.assertNotIn("\nup\n", self.record.read_text())
        failed = self.unix_run("start", "fail")
        self.assertEqual(failed.returncode, 23)

    @unittest.skipUnless(SHELL, "A POSIX shell is not installed")
    def test_missing_game_data_fails_before_starting_docker(self):
        launcher = ROOT / "start-server.sh"
        self.assertTrue(launcher.is_file(), "Unix launcher is missing")
        env = os.environ.copy()
        env.pop("JK_GAME_DATA", None)
        result = subprocess.run([SHELL, str(launcher), "--game-data", str(self.directory / "missing")],
                                env=env, text=True, capture_output=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("game-data", result.stderr.lower())


if __name__ == "__main__":
    unittest.main()

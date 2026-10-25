"""Updater checks use tiny synthetic releases, never game executables/data."""
import asyncio
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from manager.updater import (API_URL, InstallationBusy, MANIFEST, PROJECT_URL, ReleaseUpdater, SUMS,
                             UpdateError, Version, _Redirects, _trusted_url)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def payload(version, *, changed=None, removed=()):
    files = {"VERSION": (version + "\n").encode(), "app.py": b"print('old fixture')\n",
             "bin/server": b"fixture executable, never run\n", "obsolete.txt": b"old note\n",
             "web_gateway/requirements-lock.txt": b"fixture==1\n",
             "web_gateway/requirements.txt": b"fixture==1\n"}
    files.update(changed or {})
    for name in removed:
        files.pop(name)
    manifest = {"schema": 1, "version": version,
                "files": {name: {"sha256": digest(data), "mode": 0o755 if name == "bin/server" else 0o644}
                          for name, data in sorted(files.items())}}
    files[MANIFEST] = (json.dumps(manifest, indent=2) + "\n").encode()
    files[SUMS] = "".join(f"{digest(data)}  {name}\n" for name, data in sorted(files.items())).encode()
    return files


def install_fixture(root, files):
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(0o755 if name == "bin/server" else 0o644)


def archive_fixture(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            info = zipfile.ZipInfo("jk-cross-server/" + name)
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | (0o755 if name == "bin/server" else 0o644)) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    return buffer.getvalue()


def release(version):
    filename = f"JK_Cross_Server_{version}.zip"
    base = PROJECT_URL + f"/-/releases/v{version}/downloads/"
    return {"tag_name": "v" + version, "released_at": "2026-01-01T00:00:00Z", "upcoming_release": False,
            "assets": {"links": [{"name": name, "direct_asset_url": base + name}
                                 for name in (filename, filename + ".sha256")]}}


class Remote:
    def __init__(self, version="0.4.0-dev", files=None):
        self.version = version
        self.metadata = [release(version)]
        self.archive = archive_fixture(files or payload(version, changed={"app.py": b"print('new fixture')\n"}))
        self.bad_checksum = False

    def __call__(self, url, limit):
        if url.startswith(API_URL + "?"):
            return json.dumps(self.metadata).encode()
        if url.endswith(".sha256"):
            value = "0" * 64 if self.bad_checksum else digest(self.archive)
            return f"{value}  JK_Cross_Server_{self.version}.zip\n".encode()
        if url.endswith(".zip"):
            return self.archive
        raise AssertionError(url)


class VersionTests(unittest.TestCase):
    def test_semantic_precedence_and_invalid_versions(self):
        ordered = ["0.3.0-dev", "0.3.0-dev.2", "0.3.0-dev.10", "0.3.0-rc.1", "0.3.0", "0.10.0", "1.0.0"]
        self.assertEqual([v.text for v in sorted(map(Version, reversed(ordered)))], ordered)
        self.assertEqual(Version("1.0.0+one"), Version("v1.0.0+two"))
        for bad in ("v../1.0.0", "1.0", "01.0.0", "1.0.0-dev.01", None):
            with self.subTest(bad=bad), self.assertRaises(UpdateError):
                Version(bad)

    def test_exact_project_https_and_redirect_policy(self):
        _trusted_url("https://gitlab.com/api/v4/projects/codalilitari%2Fjk-cross-server/packages/generic/jk-cross-server/v0%2E3%2E0-dev/file.zip")
        for url in ("http://gitlab.com/api/v4/projects/88054997/releases", "https://gitlab.com/other/project/file.zip",
                    "https://gitlab.com.evil.invalid/api/v4/projects/88054997/releases", "https://gitlab.com:4430/api/v4/projects/88054997/releases",
                    "https://gitlab.com/api/v4/projects/88054997/../another/releases",
                    "https://user:secret@gitlab.com/api/v4/projects/88054997/releases"):
            with self.subTest(url=url), self.assertRaises(UpdateError):
                _trusted_url(url)
        with self.assertRaises(UpdateError):
            _Redirects().redirect_request(None, None, 302, "", {}, "https://other.invalid/release.zip")


class UpdaterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "install"
        self.root.mkdir()
        self.old = payload("0.3.0-dev")
        install_fixture(self.root, self.old)
        self.remote = Remote()
        self.updater = ReleaseUpdater(self.root, self.root / "runtime", fetcher=self.remote)

    async def asyncTearDown(self):
        self.updater.release_session_lease()
        self.temp.cleanup()

    def assert_old(self):
        for name, data in self.old.items():
            self.assertEqual((self.root / name).read_bytes(), data, name)

    async def test_choose_highest_semver_not_release_list_order(self):
        upcoming = dict(release("9.0.0"), upcoming_release=True)
        future = dict(release("8.0.0"), released_at="2999-01-01T00:00:00Z")
        unrelated = release("2.0.0")
        unrelated["assets"]["links"][0]["direct_asset_url"] = "https://elsewhere.invalid/package.zip"
        self.remote.metadata = [release("0.4.0-dev.2"), release("0.4.0-dev.10"), release("0.4.0"), upcoming, future, unrelated]
        result = await self.updater.check()
        self.assertEqual(result["latest_version"], "0.4.0")
        self.assertTrue(result["update_available"])
        self.assertFalse(result["checking"])

    async def test_offline_check_is_visible_and_changes_nothing(self):
        def offline(*args):
            raise UpdateError("Offline fixture")
        self.updater.fetcher = offline
        result = await self.updater.check()
        self.assertEqual(result["error"], "Offline fixture")
        self.assertFalse(result["update_available"])
        self.assert_old()

    async def test_install_preserves_local_data_modes_and_removes_obsolete_managed_file(self):
        self.remote = Remote(files=payload("0.4.0-dev", changed={"app.py": b"print('new fixture')\n", "docs/new.txt": b"new"}, removed=("obsolete.txt",)))
        self.updater.fetcher = self.remote
        local = {"config/server.json": b'{"password":"fixture-only"}', "runtime/log.txt": b"session log",
                 ".venv/local.txt": b"virtual environment", "games/custom.gob": b"game data", "notes.txt": b"local edits"}
        install_fixture(self.root, local)
        await self.updater.check()
        result = await self.updater.install()
        self.assertEqual(result["current_version"], "0.4.0-dev")
        self.assertTrue(result["restart_required"])
        self.assertFalse(result["update_available"])
        self.assertFalse((self.root / "obsolete.txt").exists())
        self.assertEqual(stat.S_IMODE((self.root / "bin/server").stat().st_mode), 0o755)
        for name, data in local.items():
            self.assertEqual((self.root / name).read_bytes(), data)
        backup = Path(result["receipt"]["backup_directory"])
        self.assertEqual((backup / "app.py").read_bytes(), self.old["app.py"])
        self.assertFalse(self.updater.journal.exists())
        self.assertEqual(len(list(self.updater.work.glob("last-backup"))), 1)
        restarted = ReleaseUpdater(self.root, self.root / "runtime", fetcher=self.remote)
        restarted.recover()
        self.assertFalse(restarted.status()["restart_required"])

    async def test_checksum_failure_never_touches_installation(self):
        self.remote.bad_checksum = True
        await self.updater.check()
        with self.assertRaisesRegex(UpdateError, "checksum failed"):
            await self.updater.install()
        self.assert_old()
        self.assertFalse(self.updater.journal.exists())

    async def test_modified_managed_file_and_untracked_collision_are_preserved(self):
        edited = b"print('local changes')\n"
        (self.root / "app.py").write_bytes(edited)
        await self.updater.check()
        with self.assertRaisesRegex(UpdateError, "Locally modified"):
            await self.updater.install()
        self.assertEqual((self.root / "app.py").read_bytes(), edited)
        (self.root / "app.py").write_bytes(self.old["app.py"])
        (self.root / "notes.txt").write_bytes(b"personal note")
        self.remote.archive = archive_fixture(payload("0.4.0-dev", changed={"notes.txt": b"release note"}))
        with self.assertRaisesRegex(UpdateError, "overwrite local content"):
            await self.updater.install()
        self.assertEqual((self.root / "notes.txt").read_bytes(), b"personal note")
        self.assert_old()

    async def test_dependency_changes_require_manual_install(self):
        self.remote.archive = archive_fixture(payload("0.4.0-dev", changed={"web_gateway/requirements-lock.txt": b"fixture==2\n"}))
        await self.updater.check()
        with self.assertRaisesRegex(UpdateError, "changes Python dependencies"):
            await self.updater.install()
        self.assert_old()

    async def test_configured_local_directory_and_symlink_are_protected(self):
        self.updater.set_protected_paths([self.root / "custom-data"])
        self.remote.archive = archive_fixture(payload("0.4.0-dev", changed={"custom-data/new.gob": b"replacement"}))
        await self.updater.check()
        with self.assertRaisesRegex(UpdateError, "configured local data"):
            await self.updater.install()
        self.assert_old()
        external = Path(self.temp.name) / "external"
        external.mkdir()
        (self.root / "extras").symlink_to(external, target_is_directory=True)
        self.remote.archive = archive_fixture(payload("0.4.0-dev", changed={"extras/new.txt": b"replacement"}))
        with self.assertRaisesRegex(UpdateError, "symbolic link"):
            await self.updater.install()
        self.assertEqual(list(external.iterdir()), [])
        self.assert_old()

    async def test_git_checkout_and_insufficient_space_do_not_install(self):
        (self.root / ".git").write_text("gitdir: elsewhere\n")
        await self.updater.check()
        self.assertFalse(self.updater.status()["install_supported"])
        with self.assertRaisesRegex(UpdateError, "Git checkout"):
            await self.updater.install()
        (self.root / ".git").unlink()
        with patch("manager.updater.shutil.disk_usage", return_value=SimpleNamespace(free=0)):
            with self.assertRaisesRegex(UpdateError, "free disk space"):
                await self.updater.install()
        self.assert_old()

    async def test_no_downgrade_or_same_version_reinstall(self):
        for version in ("0.2.0-dev", "0.3.0-dev"):
            self.updater.fetcher = Remote(version=version)
            await self.updater.check()
            self.assertFalse(self.updater.status()["update_available"])
            with self.assertRaisesRegex(UpdateError, "already installed or older"):
                await self.updater.install()
        self.assert_old()

    async def test_another_session_blocks_install_and_old_panel_cannot_start_after_update(self):
        second = ReleaseUpdater(self.root, self.root / "other-runtime", fetcher=self.remote)
        second.acquire_session_lease()
        try:
            self.updater.recover()  # Opening a second idle panel is permitted.
            await self.updater.check()
            with self.assertRaisesRegex(InstallationBusy, "Another session"):
                await self.updater.install()
        finally:
            second.release_session_lease()
        await self.updater.install()
        with self.assertRaisesRegex(UpdateError, "Restart the control panel"):
            second.acquire_session_lease()

    async def test_mid_install_failure_restores_entire_old_release(self):
        await self.updater.check()
        real_replace = os.replace
        failed = False
        def interrupted(source, destination):
            nonlocal failed
            if Path(destination) == self.root / "bin/server" and not failed:
                failed = True
                raise OSError("simulated filesystem failure")
            return real_replace(source, destination)
        with patch("manager.updater.os.replace", side_effect=interrupted):
            with self.assertRaisesRegex(UpdateError, "simulated filesystem failure"):
                await self.updater.install()
        self.assertTrue(failed)
        self.assert_old()
        self.assertFalse(self.updater.journal.exists())
        self.assertEqual(self.updater.receipt["outcome"], "rolled_back")

    async def test_bad_archive_metadata_and_python_are_rejected_before_install(self):
        cases = [payload("0.4.0-dev", changed={"../escape.txt": b"bad"}),
                 payload("0.4.0-dev", changed={"runtime/local.txt": b"bad"}),
                 payload("0.4.0-dev", changed={"app.py": b"def broken(:\n"}),
                 payload("0.5.0-dev")]
        for files in cases:
            with self.subTest(files=list(files)):
                self.remote.archive = archive_fixture(files)
                await self.updater.check()
                with self.assertRaises(UpdateError):
                    await self.updater.install()
                self.assert_old()
        self.remote.archive = archive_fixture(payload("0.4.0-dev"))
        with patch("manager.updater.MAX_UNPACKED", 1):
            with self.assertRaisesRegex(UpdateError, "unpacking limits"):
                await self.updater.install()

    async def test_forged_inner_file_and_unlisted_file_are_rejected(self):
        files = payload("0.4.0-dev")
        files["bin/server"] = b"wrong bytes"
        self.remote.archive = archive_fixture(files)
        await self.updater.check()
        with self.assertRaisesRegex(UpdateError, "file checksum failed"):
            await self.updater.install()
        files = payload("0.4.0-dev")
        files["extra.txt"] = b"unlisted"
        self.remote.archive = archive_fixture(files)
        with self.assertRaisesRegex(UpdateError, "contents do not match"):
            await self.updater.install()
        self.assert_old()


@unittest.skipUnless(os.name == "posix", "Crash recovery test uses POSIX process exit")
class CrashRecoveryTests(unittest.TestCase):
    def test_actual_process_death_recovers_before_server_start(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "install"
            root.mkdir()
            old = payload("0.3.0-dev")
            install_fixture(root, old)
            remote = Remote()
            package = base / "new.zip"
            package.write_bytes(remote.archive)
            code = r'''
import asyncio, hashlib, json, os, sys
from pathlib import Path
from manager.updater import API_URL, PROJECT_URL, ReleaseUpdater
root, archive_path = map(Path, sys.argv[1:])
data = archive_path.read_bytes()
name = 'JK_Cross_Server_0.4.0-dev.zip'
base = PROJECT_URL + '/-/releases/v0.4.0-dev/downloads/'
def fetch(url, limit):
    if url.endswith('.sha256'):
        return (hashlib.sha256(data).hexdigest() + '  ' + name + '\n').encode()
    return data
updater = ReleaseUpdater(root, root/'runtime', fetcher=fetch)
target = {'version':'0.4.0-dev', 'filename':name, 'archive_url':base+name, 'checksum_url':base+name+'.sha256'}
original = os.replace
def crash(source, destination):
    result = original(source, destination)
    if Path(destination) == root/'app.py':
        os._exit(73)
    return result
os.replace = crash
updater._install(target)
'''
            env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
            child = subprocess.run([sys.executable, "-c", code, str(root), str(package)], env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(child.returncode, 73, child.stderr)
            self.assertNotEqual((root / "app.py").read_bytes(), old["app.py"])
            recovered = ReleaseUpdater(root, root / "runtime")
            self.assertTrue(recovered.journal.exists())
            self.assertTrue(recovered.recover())
            for name, data in old.items():
                self.assertEqual((root / name).read_bytes(), data, name)
            self.assertEqual(recovered.receipt["outcome"], "rolled_back")
            self.assertFalse(recovered.journal.exists())
            self.assertFalse(recovered.status()["restart_required"])
            self.assertFalse(recovered.recover())  # A retained receipt is not a new recovery.


if __name__ == "__main__":
    unittest.main()

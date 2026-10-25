"""Verify release reproducibility, managed-file inventory and private-file boundaries."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile


SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "build_release.py"
SPEC = importlib.util.spec_from_file_location("jk_release_packaging", SOURCE)
packaging = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = packaging
SPEC.loader.exec_module(packaging)


class ReleasePackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "source"
        self.root.mkdir()
        self.git("init", "-q")
        for name, data in {
            "VERSION": b"0.3.0-dev\n",
            "app.py": b"print('fixture only')\n",
            "LICENSE": b"Fixture license\n",
            "NOTICE.md": b"Fixture attribution\n",
            "web_gateway/requirements-lock.txt": b"aiohttp==3.13.0\n",
            "bin/linux-x86_64/openjkdf2": b"fixture executable, not a game\n",
            ".gitignore": b"runtime/\n",
        }.items():
            self.write(name, data)
        self.git("add", ".")
        self.git("update-index", "--chmod=+x", "bin/linux-x86_64/openjkdf2")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True,
                              capture_output=True, text=True).stdout

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def test_reproducible_zip_has_exact_verified_payload_and_executable_modes(self):
        packaging.refresh_metadata(self.root)
        first = packaging.build_release(self.root, Path(self.temp.name) / "first")
        for path in self.root.rglob("*"):
            if path.is_file() and ".git" not in path.parts:
                os.utime(path, (1_700_000_000, 1_700_000_000))
        second = packaging.build_release(self.root, Path(self.temp.name) / "second")
        self.assertEqual(first["sha256"], second["sha256"])
        self.assertEqual(Path(first["archive"]).read_bytes(), Path(second["archive"]).read_bytes())
        with zipfile.ZipFile(first["archive"]) as bundle:
            self.assertIsNone(bundle.testzip())
            manifest = json.loads(bundle.read("jk-cross-server/release-manifest.json"))
            self.assertEqual(manifest["schema"], 1)
            self.assertEqual(manifest["version"], "0.3.0-dev")
            self.assertEqual(set(bundle.namelist()), {
                "jk-cross-server/" + name for name in manifest["files"]
            } | {"jk-cross-server/release-manifest.json", "jk-cross-server/SHA256SUMS"})
            for name, expected in manifest["files"].items():
                member = bundle.getinfo("jk-cross-server/" + name)
                self.assertEqual(hashlib.sha256(bundle.read(member)).hexdigest(), expected["sha256"])
                self.assertEqual(stat.S_IMODE(member.external_attr >> 16), expected["mode"])
                self.assertTrue(stat.S_ISREG(member.external_attr >> 16))
                self.assertEqual(member.date_time, packaging.FIXED_DATE)
            self.assertEqual(manifest["files"]["bin/linux-x86_64/openjkdf2"]["mode"], 0o755)
            checksums = bundle.read("jk-cross-server/SHA256SUMS").decode().splitlines()
            covered = {}
            for row in checksums:
                digest, name = row.split("  ", 1)
                self.assertEqual(digest, hashlib.sha256(bundle.read("jk-cross-server/" + name)).hexdigest())
                covered[name] = digest
            self.assertEqual(set(covered), set(manifest["files"]) | {"release-manifest.json"})
        self.assertEqual(Path(first["checksum"]).read_text(),
                         first["sha256"] + "  JK_Cross_Server_0.3.0-dev.zip\n")

    def test_untracked_and_accidentally_tracked_private_data_are_excluded(self):
        private = [
            "config/server.json", "runtime/session.log", ".venv/token.txt",
            ".jk-update/state.json", ".env", ".env.production",
            "instance.json", "server.json", "settings.json",
            "tools/credentials.json", "game-data/episode.jk", "mods/custom.gob",
            "qa/private-key.pem", "dist/previous.zip", "media/original.iso",
        ]
        for name in private:
            self.write(name, b"private fixture, never publish\n")
            self.git("add", "--force", name)
        self.write("untracked-source.py", b"untracked fixture\n")
        self.write("examples/public.json", b'{}\n')
        self.git("add", "examples/public.json")
        snapshot = packaging.refresh_metadata(self.root)
        self.assertIn("examples/public.json", snapshot.files)
        self.assertIn(".gitignore", snapshot.files)
        self.assertNotIn("untracked-source.py", snapshot.files)
        self.assertTrue(set(private).isdisjoint(snapshot.files))
        result = packaging.build_release(self.root, Path(self.temp.name) / "release")
        with zipfile.ZipFile(result["archive"]) as bundle:
            self.assertFalse(any(b"private fixture" in bundle.read(name) for name in bundle.namelist()))

    def test_changed_or_added_managed_files_require_explicit_refresh(self):
        packaging.refresh_metadata(self.root)
        self.write("app.py", b"print('changed fixture')\n")
        with self.assertRaisesRegex(packaging.ReleaseError, "missing or stale"):
            packaging.build_release(self.root, Path(self.temp.name) / "release")
        packaging.refresh_metadata(self.root)
        self.write("manager/new_feature.py", b"fixture = True\n")
        self.git("add", "manager/new_feature.py")
        with self.assertRaisesRegex(packaging.ReleaseError, "missing or stale"):
            packaging.check_metadata(self.root)
        packaging.refresh_metadata(self.root)
        packaging.check_metadata(self.root)

    def test_symlink_and_case_collision_are_rejected(self):
        self.write("manager/a.py", b"fixture\n")
        self.git("add", "manager/a.py")
        (self.root / "manager/a.py").unlink()
        (self.root / "manager/a.py").symlink_to(self.root / "app.py")
        with self.assertRaisesRegex(packaging.ReleaseError, "Symlinked"):
            packaging.collect_payload(self.root)
        (self.root / "manager/a.py").unlink()
        self.write("manager/a.py", b"fixture\n")
        self.write("manager/A.py", b"other fixture\n")
        self.git("add", "manager/A.py")
        with self.assertRaisesRegex(packaging.ReleaseError, "collision"):
            packaging.collect_payload(self.root)

    def test_unsafe_version_and_missing_required_payload_are_rejected(self):
        for version in (b"../../bad\n", b"v0.3.0\n", b"0.3.0-dev.01\n", b"0.3.0+local\n"):
            self.write("VERSION", version)
            with self.subTest(version=version), self.assertRaises(packaging.ReleaseError):
                packaging.collect_payload(self.root)
        self.write("VERSION", b"0.3.0-dev.2\n")
        self.assertEqual(packaging.collect_payload(self.root).version, "0.3.0-dev.2")
        self.git("rm", "--cached", "NOTICE.md")
        with self.assertRaisesRegex(packaging.ReleaseError, "Required release files"):
            packaging.collect_payload(self.root)

    def test_check_cli_is_read_only_and_reports_stale_metadata(self):
        packaging.refresh_metadata(self.root)
        before = {name: (self.root / name).stat().st_mtime_ns for name in
                  (packaging.MANIFEST, packaging.CHECKSUMS)}
        result = subprocess.run([sys.executable, str(SOURCE), "--source-root", str(self.root), "--check"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["ok"])
        self.assertEqual(before, {name: (self.root / name).stat().st_mtime_ns for name in before})
        self.write("app.py", b"changed\n")
        result = subprocess.run([sys.executable, str(SOURCE), "--source-root", str(self.root), "--check"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing or stale", result.stderr)


if __name__ == "__main__":
    unittest.main()

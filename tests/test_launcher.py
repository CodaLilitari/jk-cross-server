"""Exercise the actual panel launcher and re-exec without starting a game."""
import json
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class LauncherTests(unittest.TestCase):
    def test_real_panel_restarts_and_keeps_session_stopped(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("app.py", "VERSION"):
                shutil.copy2(source / name, root / name)
            for name in ("manager", "web_gateway"):
                shutil.copytree(source / name, root / name,
                                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            state = root / "runtime"
            state.mkdir()
            (state / "update-settings.json").write_text(json.dumps({"enabled": False, "auto_install": False}))
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            url = f"http://127.0.0.1:{port}"
            proc = subprocess.Popen([sys.executable, str(root / "app.py"), "--port", str(port)],
                                    cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            try:
                def token(previous=None):
                    deadline = time.monotonic() + 12
                    while time.monotonic() < deadline:
                        if proc.poll() is not None:
                            self.fail("Panel exited: " + proc.stdout.read())
                        try:
                            with urlopen(url, timeout=1) as response:
                                markup = response.read().decode()
                            match = re.search(r'name="admin-token" content="([^"]+)"', markup)
                            if match and match[1] != previous:
                                return match[1]
                        except (URLError, TimeoutError, ConnectionError):
                            pass
                        time.sleep(0.05)
                    self.fail("Panel did not become ready with a fresh token.")

                first = token()
                headers = {"Authorization": "Bearer " + first}
                with urlopen(Request(url + "/api/updates/restart", data=b"", headers=headers), timeout=3) as response:
                    self.assertTrue(json.load(response)["restart_pending"])
                with self.assertRaises(HTTPError) as caught:
                    urlopen(Request(url + "/api/start", data=b"", headers=headers), timeout=3)
                self.assertEqual(caught.exception.code, 400)
                self.assertIn("restarting or closing", caught.exception.read().decode())
                second = token(first)
                with urlopen(Request(url + "/api/status", headers={"Authorization": "Bearer " + second}), timeout=3) as response:
                    status = json.load(response)
                self.assertEqual(status["state"], "stopped")
                self.assertEqual(status["processes"], {})
                self.assertFalse(status["updates"]["enabled"])
                self.assertFalse(status["updates"]["restart_required"])
            finally:
                proc.terminate()
                try:
                    proc.communicate(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()

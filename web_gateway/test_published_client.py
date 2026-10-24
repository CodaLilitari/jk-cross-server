"""Optional unchanged published-JavaScript transport test, requiring Node24+."""
import asyncio
import json
import os
from pathlib import Path
import shutil
import unittest

from . import test_gateway


@unittest.skipUnless(os.environ.get("JKDF2WEB_CLIENT_DIR") and shutil.which("node"),
                     "Set JKDF2WEB_CLIENT_DIR to a fetched cloudflare-38 build and install Node24+")
class PublishedClientTransport(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_gateway.GatewayIntegration.asyncSetUp
    asyncTearDown = test_gateway.GatewayIntegration.asyncTearDown

    async def test_unchanged_published_transport(self):
        bundle = Path(os.environ["JKDF2WEB_CLIENT_DIR"]) / "openjkdf2.js"
        script = Path(__file__).with_name("check_published_client.mjs")
        process = await asyncio.create_subprocess_exec("node", str(script), str(bundle),
                                                       self.url.replace("http:", "ws:") + "/relay",
                                                       stdout=asyncio.subprocess.PIPE,
                                                       stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(process.communicate(), 15)
        self.assertEqual(process.returncode, 0, stderr.decode() + stdout.decode())
        result = json.loads(stdout.decode().strip().splitlines()[-1])
        self.assertTrue(result["passed"])
        self.assertFalse(result["transport_function_changed"])
        self.assertTrue(result["application_payload_unchanged"])
        print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    unittest.main()

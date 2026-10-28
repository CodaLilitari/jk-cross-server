"""Host observer boundary using real manager, private IPC and socketpair."""
import asyncio
import json
import os
import unittest

from aiohttp import ClientSession, web

from manager.admin import create_admin_app
from manager.config import ConfigError, validate
from manager.broker import encode, receive
from tests.test_runtime_display import RuntimeFixture


class SpectatorConfigurationTests(unittest.TestCase):
    def test_render_context_is_prepared_by_default_but_setting_is_boolean(self):
        self.assertIs(validate({}).get("spectator_rendering"), True)
        for value in (None, "true", 1, [], {}):
            with self.subTest(value=value), self.assertRaises(ConfigError):
                validate({"spectator_rendering": value})


@unittest.skipIf(os.name == "nt", "Unix inherited socketpair fixture")
class SpectatorHTTPFixture(RuntimeFixture):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.runner = web.AppRunner(create_admin_app(self.manager, port=None, token="observer-fixture-token"))
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        self.url = "http://127.0.0.1:" + str(site._server.sockets[0].getsockname()[1])
        self.client = ClientSession(headers={"Authorization": "Bearer observer-fixture-token"})

    async def asyncTearDown(self):
        await self.client.close()
        await self.runner.cleanup()
        await super().asyncTearDown()

    async def api(self, method="GET", suffix="", body=None, expected=200):
        async with self.client.request(method, self.url + "/api/spectator" + suffix, json=body) as response:
            text = await response.text()
            self.assertEqual(response.status, expected, text)
            return json.loads(text)

    async def start_observer(self):
        await self.manager.start()
        status = await self.api()
        self.assertTrue(status["available"], status)
        return status

    async def configure(self, mode="free", target=None, expected=200, status=None):
        status = status or await self.api()
        return await self.api("PUT", body={"world_epoch": status["world_epoch"],
                                           "control_epoch": status["control_epoch"],
                                           "mode": mode, "target": target}, expected=expected)

    async def frame(self, query=""):
        async with self.client.get(self.url + "/api/spectator/frame" + query) as response:
            return response.status, dict(response.headers), await response.read()

    async def wait_frame(self, sequence):
        async def wait():
            while True:
                status, headers, pixels = await self.frame()
                if status == 200 and int(headers["X-JK-Frame-Sequence"]) >= sequence:
                    return headers, pixels
                await asyncio.sleep(.01)
        return await asyncio.wait_for(wait(), 3)


class SpectatorManagerTests(SpectatorHTTPFixture):
    async def test_starts_off_and_reports_authoritative_roster(self):
        status = await self.start_observer()
        self.assertEqual(status["mode"], "off")
        self.assertFalse(status["enabled"])
        self.assertEqual(status["players"], [{"peer_id": 101, "generation": 17, "slot": 1, "name": "Fixture player"}])
        self.assertIsNotNone(self.observed()["OPENJKDF2_SPECTATOR_FD"])
        self.assertEqual(self.manager.status()["session"]["players"], 2)

    async def test_configure_and_input_use_typed_supervisor_operations(self):
        initial = await self.start_observer()
        follow = await self.configure("follow", {"peer_id": 101, "generation": 17}, status=initial)
        self.assertEqual(follow["mode"], "follow")
        self.assertEqual(follow["target"], {"peer_id": 101, "generation": 17})
        current = await self.configure(status=follow)
        await self.api("PUT", "/input", {"world_epoch": current["world_epoch"],
                      "control_epoch": current["control_epoch"], "sequence": 1,
                      "forward": 1, "right": 0, "up": 0, "yaw_delta": .1, "pitch_delta": 0})
        calls = [json.loads(line) for line in (self.manager.run_dir / "observer-requests.jsonl").read_text().splitlines()]
        self.assertTrue(all(row["source"] == 0 for row in calls))
        self.assertIn({"source": 0, "operation": 1, "bytes": 28}, calls)
        self.assertIn({"source": 0, "operation": 2, "bytes": 40}, calls)
        self.assertEqual(self.manager.status()["session"]["players"], 2)

    async def test_frame_stream_is_fragment_safe_latest_only_rgba(self):
        await self.start_observer()
        current = await self.configure()
        await self.command("observer-frame")
        headers, pixels = await self.wait_frame(1)
        self.assertEqual(pixels, bytes([1, 20, 30, 255]) * 8)
        self.assertEqual(headers["X-JK-Frame-Width"], "4")
        self.assertEqual(headers["X-JK-Frame-Height"], "2")
        self.assertEqual(int(headers["X-JK-Control-Epoch"]), current["control_epoch"])
        await self.command("observer-frame")
        headers, pixels = await self.wait_frame(2)
        self.assertEqual(pixels, bytes([2, 20, 30, 255]) * 8)
        self.assertEqual((await self.frame("?after=2"))[0], 204)
        self.assertFalse(list(self.manager.run_dir.rglob("*.rgba")))
        self.assertFalse(list(self.manager.run_dir.rglob("*.frame")))

    async def test_disable_and_world_change_reject_previous_frames(self):
        await self.start_observer()
        old = await self.configure()
        await self.command("observer-frame")
        await self.wait_frame(1)
        await self.configure("off")
        self.assertNotEqual((await self.frame())[0], 200)
        await self.configure()
        await self.command("observer-frame")
        await self.wait_frame(1)
        await self.command("observer-map")
        current = await self.api()
        self.assertGreater(current["world_epoch"], old["world_epoch"])
        self.assertNotEqual((await self.frame())[0], 200)
        await self.configure(status=old, expected=409)

    async def test_invalid_or_stale_input_does_not_reach_native(self):
        await self.start_observer()
        current = await self.configure()
        body = {"world_epoch": current["world_epoch"], "control_epoch": current["control_epoch"],
                "sequence": 1, "forward": 1, "right": 0, "up": 0, "yaw_delta": 0, "pitch_delta": 0}
        for invalid in ({**body, "forward": float("nan")}, {**body, "right": True},
                        {**body, "up": 2}, {**body, "console": "unused"}):
            await self.api("PUT", "/input", invalid, expected=400)
        await self.api("PUT", "/input", {**body, "control_epoch": 0}, expected=409)
        calls = [json.loads(line) for line in (self.manager.run_dir / "observer-requests.jsonl").read_text().splitlines()]
        self.assertNotIn(2, [row["operation"] for row in calls])

    async def test_routes_require_existing_panel_auth_and_same_origin(self):
        await self.start_observer()
        async with ClientSession() as anonymous:
            for suffix in ("", "/frame"):
                async with anonymous.get(self.url + "/api/spectator" + suffix) as response:
                    self.assertEqual(response.status, 401)
        async with self.client.get(self.url + "/api/spectator", headers={"Origin": "https://elsewhere.invalid"}) as response:
            self.assertEqual(response.status, 403)

    async def test_broker_rejects_private_observer_requests(self):
        await self.start_observer()
        reader, writer = await asyncio.open_connection("127.0.0.1", self.manager.config["broker_port"])
        try:
            writer.write(encode(1, payload=self.manager.broker.token.encode()))
            await writer.drain()
            self.assertEqual((await receive(reader))[0], 101)
            writer.write(encode(11, 0, 1, b"\x01\0\0\0\0\0\0\0"))
            await writer.drain()
            self.assertEqual((await receive(reader))[0], 199)
            self.assertTrue(self.manager.status()["session_ready"])
        finally:
            writer.close()
            await writer.wait_closed()

    async def test_bad_observer_reply_and_frame_do_not_stop_gameplay(self):
        await self.start_observer()
        await self.configure()
        await self.command("observer-malformed")
        await self.api(expected=503)
        self.assertTrue(self.manager.status()["session_ready"])
        self.assertTrue(self.manager.ipc.connected)
        await self.command("observer-normal")
        await self.api()
        await self.command("observer-oversize")
        await asyncio.sleep(.05)
        self.assertNotEqual((await self.frame())[0], 200)
        self.assertTrue(self.manager.status()["session_ready"])

    async def test_disabled_rendering_passes_no_fd_and_explains_restart(self):
        self.manager.config["spectator_rendering"] = False
        await self.manager.start()
        status = await self.api()
        self.assertFalse(status["available"])
        self.assertTrue(status["restart_required"])
        self.assertIsNone(self.observed()["OPENJKDF2_SPECTATOR_FD"])
        self.assertTrue(self.manager.status()["session_ready"])

    async def test_old_engine_without_observer_support_remains_usable(self):
        os.environ["JK_FIXTURE_SPECTATOR"] = "unsupported"
        await self.manager.start()
        await self.api(expected=503)
        self.assertTrue(self.manager.status()["session_ready"])
        self.assertTrue(self.manager.ipc.connected)

    async def test_status_polling_does_not_keep_unviewed_rendering_alive(self):
        await self.start_observer()
        current = await self.configure()
        # Exercise the real five-second lease without renewing through frames.
        deadline = asyncio.get_running_loop().time() + 7
        while asyncio.get_running_loop().time() < deadline:
            status = await self.api()
            if status["mode"] == "off":
                break
            await asyncio.sleep(.2)
        self.assertEqual(status["mode"], "off")
        self.assertGreater(status["control_epoch"], current["control_epoch"])
        self.assertTrue(self.manager.status()["session_ready"])

    async def test_applied_enable_with_lost_reply_still_expires_without_a_viewer(self):
        await self.start_observer()
        self.manager.ipc.request_timeout = .1
        await self.command("observer-drop-enable-reply")
        await self.configure(expected=503)
        # The engine applied the request even though its acknowledgement was
        # lost. A successful status query must not grant an unbounded view.
        current = await self.api()
        self.assertEqual(current["mode"], "free")
        self.assertTrue(current["enabled"])
        deadline = asyncio.get_running_loop().time() + 7
        while asyncio.get_running_loop().time() < deadline:
            status = await self.api()
            if status["mode"] == "off":
                break
            await asyncio.sleep(.2)
        self.assertEqual(status["mode"], "off")
        self.assertGreater(status["control_epoch"], current["control_epoch"])
        self.assertTrue(self.manager.status()["session_ready"])

    async def test_native_frame_age_and_render_errors_retire_old_pixels(self):
        await self.start_observer()
        await self.configure()
        await self.command("observer-frame")
        await self.wait_frame(1)
        for failure in ("stale-frame", "render-error"):
            await self.command("observer-" + failure)
            await self.api()
            self.assertNotEqual((await self.frame())[0], 200, failure)
        self.assertTrue(self.manager.status()["session_ready"])

    async def test_authenticated_frame_fetches_keep_view_open_without_new_frames(self):
        await self.start_observer()
        await self.configure()
        for _ in range(6):
            self.assertEqual((await self.frame())[0], 204)
            await asyncio.sleep(1)
        self.assertEqual((await self.api())["mode"], "free")

    async def test_observer_timeout_clears_frames_but_keeps_authenticated_game_ipc(self):
        await self.start_observer()
        await self.configure()
        await self.command("observer-frame")
        await self.wait_frame(1)
        self.manager.ipc.request_timeout = .1
        await self.command("observer-silent")
        await self.api(expected=503)
        self.assertNotEqual((await self.frame())[0], 200)
        self.assertTrue(self.manager.ipc.connected)
        self.assertTrue(self.manager.status()["session_ready"])

    async def test_input_replies_cannot_starve_authoritative_roster_refresh(self):
        await self.start_observer()
        current = await self.configure()
        await self.command("observer-empty-roster")
        for sequence in range(1, 13):
            body = {"world_epoch": current["world_epoch"], "control_epoch": current["control_epoch"],
                    "sequence": sequence, "forward": 0, "right": 0, "up": 0, "yaw_delta": 0, "pitch_delta": 0}
            async with self.client.put(self.url + "/api/spectator/input", json=body) as response:
                self.assertIn(response.status, (200, 429), await response.text())
            await asyncio.sleep(.1)
        self.assertEqual(self.manager.status()["spectator"]["players"], [])


if __name__ == "__main__":
    unittest.main()

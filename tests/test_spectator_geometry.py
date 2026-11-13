"""Geometry boundary through the owned engine, inherited Unix stream and HTTP."""
import asyncio
import json
import os
import struct
import time
import unittest

from aiohttp import ClientSession
from tests.test_spectator import SpectatorHTTPFixture


@unittest.skipIf(os.name == "nt", "Unix inherited socketpair fixture")
class SpectatorGeometryTests(SpectatorHTTPFixture):
    async def geometry(self, current, extra="", **kwargs):
        query = f'?world_epoch={current["world_epoch"]}&control_epoch={current["control_epoch"]}' + extra
        async with self.client.get(self.url + "/api/spectator/geometry" + query, **kwargs) as response:
            return response.status, dict(response.headers), await response.read()

    async def begin(self):
        await self.start_observer()
        current = await self.configure()
        self.assertEqual((await self.geometry(current))[0], 204)
        return current

    async def wait_geometry(self, current, expected=200):
        async def wait():
            while True:
                result = await self.geometry(current)
                if result[0] == expected:
                    return result
                await asyncio.sleep(.01)
        try:
            return await asyncio.wait_for(wait(), 3)
        except asyncio.TimeoutError:
            self.fail(f"Geometry fetch did not reach HTTP {expected} within three seconds.")

    def operations(self):
        return [json.loads(line) for line in (self.manager.run_dir / "observer-requests.jsonl").read_text().splitlines()]

    async def test_explicit_fetch_activates_geometry_once_without_changing_camera(self):
        await self.start_observer()
        current = await self.configure()
        for _ in range(3):
            await self.api()
            await self.frame()
        self.assertFalse(any(row["operation"] == 3 for row in self.operations()))
        before = self.manager.spectator._viewer_deadline
        self.assertEqual((await self.geometry(current))[0], 204)
        await self.geometry(current)
        calls = [row for row in self.operations() if row["operation"] == 3]
        self.assertEqual(calls, [{"source": 0, "operation": 3, "bytes": 20}])
        self.assertGreater(self.manager.spectator._viewer_deadline, before)
        after = await self.api()
        self.assertEqual(after["control_epoch"], current["control_epoch"])
        self.assertEqual(after["geometry"]["profile"], "flat-colour-v1")
        self.assertTrue(after["geometry"]["available"])
        self.assertIsNotNone(self.observed()["OPENJKDF2_SPECTATOR_GEOMETRY_FD"])

    async def test_fragmented_envelope_full_payload_age_and_latest_only(self):
        current = await self.begin()
        await self.command("geometry-normal")
        status, headers, data = await self.wait_geometry(current)
        fields = struct.unpack_from("<4s15I", data)
        self.assertEqual(fields[:9], (b"JKSG", 1, 4, 2, current["world_epoch"], current["control_epoch"], 1, 72, 0))
        self.assertEqual(len(data), 136)
        self.assertEqual(headers["Content-Type"], "application/octet-stream")
        self.assertEqual(headers["Cache-Control"], "no-store")
        await asyncio.sleep(.06)
        later = (await self.geometry(current))[2]
        self.assertGreater(struct.unpack_from("<I", later, 36)[0], fields[9])
        self.assertEqual((await self.geometry(current, "&after=1"))[0], 204)
        await self.command("geometry-empty")
        empty = (await self.wait_geometry(current))[2]
        # Wait for the newer completion, without depending on a fixed scheduler delay.
        async def latest():
            while struct.unpack_from("<I", empty := (await self.geometry(current))[2], 24)[0] != 2:
                await asyncio.sleep(.01)
            return empty
        empty = await asyncio.wait_for(latest(), 1)
        self.assertEqual(len(empty), 64)
        self.assertEqual(struct.unpack_from("<II", empty, 40), (0, 0))

    async def test_guard_and_strict_query_do_not_activate_geometry(self):
        await self.start_observer()
        current = await self.configure()
        async with ClientSession() as anonymous:
            async with anonymous.get(self.url + "/api/spectator/geometry") as response:
                self.assertEqual(response.status, 401)
        self.assertEqual((await self.geometry(current, headers={"Origin": "https://elsewhere.invalid"}))[0], 403)
        for suffix in ("", "?world_epoch=1", "?world_epoch=1&control_epoch=2&after=-1",
                       "?world_epoch=1&control_epoch=2&after=0&after=1", "?world_epoch=1&control_epoch=2&other=1"):
            async with self.client.get(self.url + "/api/spectator/geometry" + suffix) as response:
                self.assertEqual(response.status, 400)
        self.assertFalse(any(row["operation"] == 3 for row in self.operations()))

    async def test_epoch_age_superseding_and_session_checks(self):
        current = await self.begin()
        await self.command("geometry-stale")
        await asyncio.sleep(.05)
        self.assertEqual((await self.geometry(current))[0], 204)
        await self.command("geometry-normal")
        await self.wait_geometry(current)
        await self.command("observer-frame")
        await self.api()
        self.assertEqual((await self.geometry(current))[0], 204)
        await self.command("geometry-normal")
        await self.wait_geometry(current)
        self.manager.session = None
        self.assertEqual((await self.geometry(current))[0], 503)
        self.assertTrue(self.manager.ipc.connected)

    async def test_delayed_transfer_cannot_freshen_geometry(self):
        current = await self.begin()
        await self.command("geometry-delayed")
        await asyncio.sleep(2.2)
        self.assertEqual((await self.geometry(current))[0], 204)
        self.assertFalse((await self.api())["geometry"]["frame_available"])

    async def test_stale_query_and_expired_view_do_not_renew(self):
        current = await self.begin()
        before = self.manager.spectator._viewer_deadline
        self.assertEqual((await self.geometry({**current, "control_epoch": 0}))[0], 409)
        self.assertEqual(self.manager.spectator._viewer_deadline, before)
        self.manager.spectator._viewer_deadline = time.monotonic() - 1
        self.assertEqual((await self.geometry(current))[0], 409)

    async def test_bad_geometry_retires_only_geometry_not_images_or_ipc(self):
        current = await self.begin()
        await self.command("geometry-index")
        await asyncio.sleep(.05)
        status = await self.api()
        self.assertFalse(status["geometry"]["available"])
        self.assertIn("geometry", status["geometry"]["reason"].lower())
        self.assertTrue(status["available"])
        self.assertEqual((await self.geometry(current))[0], 503)
        await self.command("observer-frame")
        await self.wait_frame(2)
        self.assertTrue(self.manager.ipc.connected)
        self.assertTrue(self.manager.status()["session_ready"])

    async def test_geometry_operation_failure_keeps_image_control_fresh(self):
        current = await self.begin()
        await self.command("observer-geometry-reject")
        self.manager.spectator._geometry_renewed_at = 0
        self.assertEqual((await self.geometry(current))[0], 503)
        self.assertTrue(self.manager.spectator.status()["available"])
        await self.command("observer-normal")
        await self.command("observer-frame")
        await self.wait_frame(1)
        self.assertTrue(self.manager.ipc.connected)

    async def test_old_image_engine_never_receives_geometry_operation(self):
        os.environ["JK_FIXTURE_SPECTATOR"] = "old-image-engine"
        await self.start_observer()
        current = await self.configure()
        self.assertEqual((await self.geometry(current))[0], 503)
        self.assertFalse(any(row["operation"] == 3 for row in self.operations()))
        await self.command("observer-frame")
        await self.wait_frame(1)
        self.assertTrue(self.manager.ipc.connected)

    async def test_future_epoch_capture_cannot_poison_current_stream(self):
        current = await self.begin()
        await self.command("geometry-epoch")
        await asyncio.sleep(.05)
        self.assertEqual((await self.geometry(current))[0], 204)
        await self.command("geometry-normal")
        data = (await self.wait_geometry(current))[2]
        self.assertEqual(struct.unpack_from("<I", data, 24)[0], 2)

    async def test_authenticated_geometry_fetches_keep_view_alive_without_pixels(self):
        current = await self.begin()
        for _ in range(6):
            self.assertEqual((await self.geometry(current))[0], 204)
            await asyncio.sleep(1)
        self.assertEqual((await self.api())["mode"], "free")
        geometry_calls = [row for row in self.operations() if row["operation"] == 3]
        self.assertGreaterEqual(len(geometry_calls), 5)

    async def test_native_capture_age_and_status_input_do_not_renew_geometry(self):
        current = await self.begin()
        renewed = self.manager.spectator._geometry_renewed_at
        deadline = self.manager.spectator._viewer_deadline
        await self.command("geometry-normal")
        await self.wait_geometry(current)
        deadline = self.manager.spectator._viewer_deadline
        await self.command("observer-stale-frame")
        await self.api()
        await self.api("PUT", "/input", {"world_epoch": current["world_epoch"],
             "control_epoch": current["control_epoch"], "sequence": 1,
             "forward": 0, "right": 0, "up": 0, "yaw_delta": 0, "pitch_delta": 0})
        self.assertEqual(self.manager.spectator._viewer_deadline, deadline)
        self.assertEqual(self.manager.spectator._geometry_renewed_at, renewed)
        self.assertEqual((await self.geometry(current))[0], 204)

    async def test_hostile_headers_and_attributes_retire_only_geometry(self):
        for kind in ("oversize", "reserved", "count", "nonfinite", "alpha"):
            with self.subTest(kind=kind):
                await self.manager.stop()
                current = await self.begin()
                await self.command("geometry-" + kind)
                await asyncio.sleep(.05)
                status = await self.api()
                self.assertFalse(status["geometry"]["available"])
                self.assertTrue(status["available"])
                await self.command("observer-frame")
                await self.wait_frame(2)
                self.assertTrue(self.manager.ipc.connected)

    async def test_channel_lifecycle_and_inactive_status_shape(self):
        inactive = self.manager.status()["spectator"]["geometry"]
        self.assertEqual(set(inactive), {"available", "frame_available", "sequence", "age_ms", "reason", "profile"})
        self.assertFalse(inactive["available"])
        await self.start_observer()
        geometry = self.manager.spectator._geometry
        self.assertFalse(geometry.parent.get_inheritable())
        self.assertFalse(geometry.parent.getblocking())
        self.assertIsNone(geometry.child)
        await self.manager.stop()
        self.assertEqual(geometry.parent.fileno(), -1)
        self.assertIsNone(geometry.task)

    async def test_geometry_native_denial_reports_reason_independently(self):
        current = await self.begin()
        await self.command("observer-geometry-deny")
        await asyncio.sleep(1.05)
        self.assertEqual((await self.geometry(current))[0], 503)
        status = self.manager.spectator.status()
        self.assertFalse(status["geometry"]["available"])
        self.assertIn("rejected", status["geometry"]["reason"].lower())
        self.assertTrue(status["available"])
        calls = sum(row["operation"] == 3 for row in self.operations())
        refreshed = await self.api()
        self.assertEqual(refreshed["geometry"]["reason"], status["geometry"]["reason"])
        self.assertEqual((await self.geometry(refreshed))[0], 503)
        self.assertEqual(sum(row["operation"] == 3 for row in self.operations()), calls)
        await self.command("observer-frame")
        await self.wait_frame(1)
        self.assertTrue(self.manager.ipc.connected)

    async def test_stale_activation_epoch_can_retry_after_follow_target_departure(self):
        await self.start_observer()
        current = await self.configure("follow", {"peer_id": 101, "generation": 17})
        self.assertEqual((await self.geometry(current))[0], 204)
        await self.command("geometry-normal")
        await self.wait_geometry(current)
        await self.command("observer-geometry-epoch-transition")
        self.manager.spectator._geometry_renewed_at = 0
        self.assertEqual((await self.geometry(current))[0], 409)
        updated = await self.api()
        self.assertEqual(updated["control_epoch"], current["control_epoch"] + 1)
        self.assertEqual(updated["world_epoch"], current["world_epoch"])
        self.assertEqual(updated["mode"], "free")
        self.assertFalse(updated["geometry"]["frame_available"])
        calls_before_retry = sum(row["operation"] == 3 for row in self.operations())
        self.assertEqual((await self.geometry(updated))[0], 204)
        self.assertEqual(sum(row["operation"] == 3 for row in self.operations()), calls_before_retry + 1)
        self.assertTrue((await self.api())["geometry"]["available"])
        await self.command("geometry-normal")
        data = (await self.wait_geometry(updated))[2]
        self.assertEqual(struct.unpack_from("<II", data, 16),
                         (updated["world_epoch"], updated["control_epoch"]))
        await self.command("observer-frame")
        await self.wait_frame(2)
        self.assertTrue(self.manager.ipc.connected)


class GeometrySharedFixtureTests(unittest.TestCase):
    def test_original_shared_profile_decodes_without_reinterpreting_vertices(self):
        from pathlib import Path
        from manager.spectator_geometry import validate_header, validate_payload
        envelope = (Path(__file__).parent / "fixtures" / "spectator_geometry.jksg").read_bytes()
        value = validate_header(envelope[:64])
        validate_payload(value, envelope[64:])
        self.assertEqual((value["width"], value["height"], value["world_epoch"], value["control_epoch"],
                          value["sequence"], value["vertex_count"], value["index_count"]),
                         (640, 360, 7, 3, 9, 23, 33))
        self.assertEqual(len(envelope), 64 + 23 * 20 + 33 * 4)

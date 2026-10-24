"""Owned synthetic assets, real loopback transports, and a published-JS oracle."""
import asyncio
import base64
import contextlib
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import tempfile
import unittest
from unittest.mock import patch

from aiohttp import ClientSession, WSMsgType, web

from . import assets as a
from .gateway import WebGateway, b64_json
from .test_gateway import descriptor


def gob(files):
    """Independent small fixture writer, not the production mod packer."""
    body = b"".join(data for _, data in files)
    table, at = bytearray(struct.pack("<I", len(files))), 12
    for name, data in files:
        table.extend(struct.pack("<II128s", at, len(data), name.encode("ascii")))
        at += len(data)
    return struct.pack("<4sII", b"GOB ", 20, 12 + len(body)) + body + table


def make_fixture(root, mode=0, large=False):
    ext = "goo" if mode else "gob"
    (root / "episode").mkdir()
    (root / "resource").mkdir()
    (root / "mod" / "mat").mkdir(parents=True)
    stock = b"owned fixture: pretend original material\n" * 200
    retail = gob([("mat/original.mat", stock), ("cog/original.cog", b"owned base cog\n")])
    base = root / "resource" / ("Jkmres.goo" if mode else "Res2.gob")
    base.write_bytes(retail)
    own = bytes(range(256)) * (1700 if large else 25)
    episode = gob([("episode.jk", b'"Owned fixture"\nTYPE 2\n'),
                   ("jkl/test.jkl", b"owned synthetic level"),
                   ("mat/original.mat", stock), ("mat/custom.mat", own)])
    (root / "episode" / ("Custom." + ext)).write_bytes(episode)
    (root / "episode" / ("Unselected." + ext)).write_bytes(gob([("secret.bin", b"not selected")]))
    (root / "mod" / "mat" / "custom.mat").write_bytes(b"custom mod material\n" * 700)
    (root / "mod" / "mat" / "original.mat").write_bytes(stock)
    (root / "mod" / "nested.gob").write_bytes(gob([("mat/original.mat", stock), ("cog/extra.cog", b"custom nested cog")]))
    (root / "mod" / "whole.gob").write_bytes(retail)
    (root / "mod" / "README.txt").write_text("ignored upstream documentation")
    return {"episode": episode, "stock": stock, "retail": retail, "base": base, "ext": ext}


def rebuild_python(info, stream, candidates):
    refs = struct.unpack_from("<I", stream)[0]
    assert 4 + refs * 40 == info["refsBytes"]
    lookup = {(len(x), hashlib.sha256(x).digest()): x for x in candidates}
    out, pos, inline = bytearray(info["size"]), 0, info["refsBytes"]
    for i in range(refs):
        at = 4 + i * 40
        offset, size = struct.unpack_from("<II", stream, at)
        if offset > pos:
            out[pos:offset] = stream[inline:inline + offset - pos]
            inline += offset - pos
        out[offset:offset + size] = lookup[(size, stream[at + 8:at + 40])]
        pos = max(pos, offset + size)
    out[pos:] = stream[inline:]
    assert hashlib.sha256(out).hexdigest() == info["sha256"]
    return bytes(out)


def request(message, kind=0, body=b"", claimed_source=0, destination=1):
    return struct.pack("<II4sBBBB", claimed_source, destination, b"JKMT", message, 1, kind, 0) + body


class PreparedAssets(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.fixture = make_fixture(self.root)

    async def asyncTearDown(self):
        self.tmp.cleanup()

    async def build(self, **kwargs):
        return await a.build_asset_provider(self.root, "Custom", 0, self.root / "mod", "Fixture Mod", **kwargs)

    async def test_reference_reconstruction_and_deterministic_mod_pack(self):
        provider = await self.build()
        map_offer, mod_offer = provider.offers[0], provider.offers[1]
        self.assertEqual(map_offer.retail_references, 1)
        self.assertEqual(mod_offer.retail_references, 3)
        candidates = [self.fixture["stock"], self.fixture["retail"], b"owned base cog\n"]
        self.assertEqual(rebuild_python(map_offer.info, map_offer.stream, candidates), self.fixture["episode"])
        files = [(rel, path.read_bytes()) for rel, path, _ in a.list_mod_files(self.root / "mod")]
        expected = gob(files)
        self.assertEqual(rebuild_python(mod_offer.info, mod_offer.stream, candidates), expected)
        self.assertNotIn(self.fixture["stock"], map_offer.stream)
        self.assertNotIn(self.fixture["stock"], mod_offer.stream)
        self.assertEqual(provider.session_tail[:7], b"JKMD\x02\x01\x0b")
        self.assertEqual(provider.session_tail[7:39], hashlib.sha256(expected).digest())
        self.assertNotIn("Unselected", json.dumps(provider.summary()))
        # A transfer is a snapshot, not a request-triggered filesystem read.
        shutil.rmtree(self.root)
        packets = list(a.chunk_frames(provider, 123, request(3, body=map_offer.identifier + struct.pack("<III", a.CHUNK_RELAY, 0, 128))))
        self.assertEqual(b"".join(p[28:] for p in packets), map_offer.stream)

    async def test_zero_references_and_stock_only_refusal(self):
        custom = gob([("episode.jk", b"entirely authored test episode")])
        path = self.root / "episode" / "Custom.gob"
        path.write_bytes(custom)
        p = await self.build()
        self.assertEqual(p.offers[0].stream, b"\0\0\0\0" + custom)
        path.write_bytes(gob([("mat/original.mat", self.fixture["stock"])]))
        p = await self.build()
        self.assertEqual(p.info(0)["status"], "retail-only")
        p = await a.build_asset_provider(self.root, "JK1MP", 0)
        self.assertEqual(p.info(0)["status"], "retail")

    async def test_disabled_keeps_map_metadata_and_mod_fingerprint(self):
        enabled, disabled = await self.build(), await self.build(download_enabled=False)
        self.assertEqual(enabled.session_tail, disabled.session_tail)
        self.assertEqual(disabled.info(0)["status"], "ok")
        self.assertEqual(disabled.info(1)["status"], "disabled")
        self.assertEqual(enabled.info(0)["sha256"], disabled.info(0)["sha256"])
        self.assertIsNone(disabled.find(enabled.offers[0].identifier))
        self.assertIsNone(disabled.offers[0].stream)
        self.assertFalse(disabled.summary()["download_enabled"])

    async def test_chunk_bounds_and_hash_select_kind(self):
        p = await self.build()
        mod = p.offers[1]
        packet = request(3, 0, mod.identifier + struct.pack("<III", a.CHUNK_DIRECT, 0, 0xffffffff))
        frames = list(a.chunk_frames(p, 0xf0001234, packet))
        self.assertTrue(frames)
        self.assertLessEqual(len(frames), 128)
        self.assertTrue(all(f[14] == 1 and len(f) <= 28 + a.CHUNK_DIRECT for f in frames))
        self.assertEqual(struct.unpack_from("<II", frames[0]), (1, 0xf0001234))
        self.assertEqual(b"".join(f[28:] for f in frames), mod.stream)
        for bad in (b"unknown!" + struct.pack("<III", a.CHUNK_DIRECT, 0, 1),
                    mod.identifier + struct.pack("<III", 42, 0, 1),
                    mod.identifier + struct.pack("<III", a.CHUNK_DIRECT, 0xffffffff, 1)):
            self.assertEqual(list(a.chunk_frames(p, 2, request(3, 1, bad))), [])

    async def test_preflight_rejects_unadvertised_overrides_and_unsafe_mod_names(self):
        extra = self.root / "resource" / "extra.gob"
        extra.write_bytes(gob([("x.bin", b"custom")]))
        with self.assertRaisesRegex(a.AssetPreparationError, "Unadvertised resource"):
            await self.build()
        extra.unlink()
        loose = self.root / "episode" / "Custom"
        loose.mkdir();(loose / "test.jkl").write_text("override")
        with self.assertRaisesRegex(a.AssetPreparationError, "Loose selected"):
            await self.build()
        shutil.rmtree(loose)
        root_mods = self.root / "mods"
        root_mods.mkdir();(root_mods / "extra.gob").write_bytes(b"outside selected mod")
        with self.assertRaisesRegex(a.AssetPreparationError, "Unadvertised mods/"):
            await self.build()
        shutil.rmtree(root_mods)
        docs = self.root / "resource" / ".notes"
        docs.mkdir();(docs / "example.dat").write_bytes(b"ignored documentation")
        (self.root / "resource" / "README").write_text("documentation")
        await self.build()
        bad = self.root / "mod" / "bad:filename.mat"
        bad.write_bytes(b"bad")
        with self.assertRaisesRegex(a.AssetPreparationError, "filename"):
            await self.build()
        bad.unlink()
        (self.root / "mod" / "alias.mat").symlink_to(self.fixture["base"])
        with self.assertRaisesRegex(a.AssetPreparationError, "symbolic link"):
            await self.build()

    async def test_mots_remaster_tail_and_unsupported_placement(self):
        tmp = self.root / "mots"
        tmp.mkdir();make_fixture(tmp, 1)
        pack = tmp / "resource" / "JKMRemasteredAssets.goo"
        pack.write_bytes(b"owned synthetic remaster fixture")
        p = await a.build_asset_provider(tmp, "Custom", 1, tmp / "mod", "MotS Mod")
        self.assertEqual(p.session_tail[:7], b"JKMD\x02\x03\x08")
        self.assertEqual(p.session_tail[39:55], hashlib.sha256(pack.read_bytes()).digest()[:16])
        self.assertEqual(p.info(0)["ext"], "goo")
        self.assertEqual(p.summary()["remastered"]["status"], "local-required")
        (tmp / "mod" / pack.name).write_bytes(pack.read_bytes())
        with self.assertRaisesRegex(a.AssetPreparationError, "Keep JKMRemasteredAssets"):
            await a.build_asset_provider(tmp, "Custom", 1, tmp / "mod")


class AssetEngine:
    connected = True
    def __init__(self, mode=0):
        entry = bytearray(descriptor(mode));entry[88:120] = b"Custom".ljust(32, b"\0")
        self.session = mode, bytes(entry)
        self.next_id = 65536
        self.sent, self.removed = [], []
    def subscribe_data(self, cb):
        self.data = cb;return lambda: None
    def subscribe_state(self, cb):
        return lambda: None
    def subscribe_info(self, cb):
        return lambda: None
    async def add_peer(self):
        self.next_id += 1;return self.next_id
    async def remove_peer(self, peer):
        self.removed.append(peer)
    async def send(self, source, destination, payload):
        self.sent.append((source, destination, payload))
        await self.data(1, source, payload)


class AssetTransport(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.root = Path(self.tmp.name)
        self.fixture = make_fixture(self.root, large=True)
        self.provider = await a.build_asset_provider(self.root, "Custom", 0, self.root / "mod", "Fixture Mod")
        self.engine = AssetEngine()
        self.gateway = WebGateway(self.engine, enable_webrtc=True, assets=self.provider, hold_seconds=.1)
        self.runner = web.AppRunner(self.gateway.create_app());await self.runner.setup()
        self.site = web.TCPSite(self.runner, "127.0.0.1", 0);await self.site.start()
        self.url = "http://127.0.0.1:" + str(self.site._server.sockets[0].getsockname()[1])
        self.client = ClientSession()
        self.sockets = []
    async def asyncTearDown(self):
        for socket in self.sockets:
            await socket.close()
        await self.gateway.close();await self.client.close();await self.runner.cleanup();self.tmp.cleanup()
    async def text(self, ws, prefix):
        async def read():
            while True:
                msg = await ws.receive()
                if msg.type == WSMsgType.TEXT and msg.data.startswith(prefix):return msg.data
                if msg.type in (WSMsgType.CLOSED, WSMsgType.ERROR):raise AssertionError("Socket closed")
        return await asyncio.wait_for(read(), 5)
    async def binary(self, ws):
        async def read():
            while True:
                msg = await ws.receive()
                if msg.type == WSMsgType.BINARY:return msg.data
                if msg.type in (WSMsgType.CLOSED, WSMsgType.ERROR):raise AssertionError("Socket closed")
        return await asyncio.wait_for(read(), 5)
    async def join(self):
        ws = await self.client.ws_connect(self.url + "/relay")
        self.sockets.append(ws)
        await ws.send_str("hello jk1 " + base64.b64encode(b"AssetPilot").decode())
        await ws.send_str("list jk1")
        listing = (await self.text(ws, "list ")).split()[3]
        self.assertEqual(bytes.fromhex(listing), self.engine.session[1] + self.provider.session_tail)
        await ws.send_str("join 1")
        await self.text(ws, "seat ")
        welcome = (await self.text(ws, "welcome ")).split()
        self.assertEqual(welcome[2], listing)
        return ws, int(welcome[1])

    async def test_websocket_download_retry_sender_and_game_separation(self):
        ws, player = await self.join()
        await ws.send_bytes(request(1, claimed_source=0xffffffff))
        info = await self.binary(ws)
        self.assertEqual(struct.unpack_from("<II", info), (1, player))
        meta = json.loads(info[16:]);offer = self.provider.offers[0]
        self.assertEqual(meta, dict(offer.info))
        req = request(3, body=offer.identifier + struct.pack("<III", a.CHUNK_RELAY, 0, 128))
        await ws.send_bytes(req)
        chunks = [await self.binary(ws) for _ in range((len(offer.stream) + a.CHUNK_RELAY - 1) // a.CHUNK_RELAY)]
        self.assertEqual(b"".join(p[28:] for p in chunks), offer.stream)
        await ws.send_bytes(request(3, body=offer.identifier + struct.pack("<III", a.CHUNK_RELAY, 1, 1)))
        self.assertEqual(await self.binary(ws), chunks[1])
        self.assertEqual(self.engine.sent, [])
        game = struct.pack("<IIHH", 999, 1, 1, 0) + b"game stays separate"
        await ws.send_bytes(game)
        reply = await self.binary(ws)
        self.assertEqual(reply[8:], game[8:])
        self.assertEqual(self.engine.sent[0][0], player)
        self.assertEqual(self.gateway.metrics["asset_bytes"], len(offer.stream) + len(chunks[1]) - 28)
        health = await (await self.client.get(self.url + "/health")).json()
        self.assertEqual(health["assets"]["map"]["sha256"], meta["sha256"])

    async def test_rtc_map_channel_and_relay_after_channel_closes(self):
        from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
        ws, player = await self.join()
        pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        game = pc.createDataChannel("jk", negotiated=True, id=0, ordered=True)
        channel = pc.createDataChannel("jk-map", negotiated=True, id=1, ordered=True)
        opened, incoming, games = asyncio.Event(), asyncio.Queue(), asyncio.Queue()
        channel.on("open", opened.set)
        channel.on("message", incoming.put_nowait)
        game.on("message", games.put_nowait)
        try:
            await pc.setLocalDescription(await pc.createOffer())
            await ws.send_str("signal 1 " + b64_json({"d": {"type": "offer", "sdp": pc.localDescription.sdp}}))
            answer = json.loads(base64.b64decode((await self.text(ws, "signal 1 ")).split()[2]))["d"]
            await pc.setRemoteDescription(RTCSessionDescription(sdp=answer["sdp"], type="answer"))
            await asyncio.wait_for(opened.wait(), 5)
            channel.send(request(1))
            info = await asyncio.wait_for(incoming.get(), 5)
            self.assertEqual(info[12], 2)
            offer = self.provider.offers[0]
            channel.send(request(3, body=offer.identifier + struct.pack("<III", a.CHUNK_DIRECT, 0, 128)))
            count = (len(offer.stream) + a.CHUNK_DIRECT - 1) // a.CHUNK_DIRECT
            chunks = [await asyncio.wait_for(incoming.get(), 5) for _ in range(count)]
            self.assertEqual(b"".join(p[28:] for p in chunks), offer.stream)
            self.assertTrue(games.empty())
            channel.close();await asyncio.sleep(.05)
            # Same fixed job chunk size on fallback; no implicit resizing.
            await ws.send_bytes(request(3, body=offer.identifier + struct.pack("<III", a.CHUNK_DIRECT, 0, 1)))
            self.assertEqual(await self.binary(ws), chunks[0])
        finally:
            await pc.close()

    async def test_leave_cancels_backpressure_and_discards_pending_requests(self):
        ws, player = await self.join()
        peer = self.gateway.peers[player]
        entered = asyncio.Event()
        original = self.gateway._send_asset_packet
        async def slow(*args):
            entered.set();await asyncio.Event().wait()
        self.gateway._send_asset_packet = slow
        offer = self.provider.offers[0]
        await ws.send_bytes(request(3, body=offer.identifier + struct.pack("<III", a.CHUNK_RELAY, 0, 128)))
        await asyncio.wait_for(entered.wait(), 2)
        self.assertEqual(self.gateway.metrics["active_asset_transfers"], 1)
        await ws.send_str("leave")
        for _ in range(50):
            if peer.asset_task.done():break
            await asyncio.sleep(.01)
        self.assertTrue(peer.asset_task.cancelled())
        self.assertEqual(self.gateway.metrics["active_asset_transfers"], 0)
        self.assertIn(player, self.engine.removed)
        self.gateway._send_asset_packet = original

    async def test_disabled_chunks_do_not_block_game_and_invalid_requests_are_ignored(self):
        self.provider.download_enabled = False
        ws, player = await self.join()
        await ws.send_bytes(request(1))
        self.assertEqual(json.loads((await self.binary(ws))[16:])["status"], "ok")
        offer = self.provider.offers[0]
        await ws.send_bytes(request(3, body=offer.identifier + struct.pack("<III", a.CHUNK_RELAY, 0, 1)))
        await ws.send_bytes(request(1, destination=1234))
        game = struct.pack("<IIHH", 0, 1, 1, 0) + b"alive"
        await ws.send_bytes(game)
        self.assertEqual((await self.binary(ws))[8:], game[8:])
        self.assertEqual(self.gateway.metrics["asset_denied"], 1)
        self.assertEqual(self.gateway.metrics["asset_chunks"], 0)

    @unittest.skipUnless(os.environ.get("JKDF2WEB_CLIENT_DIR") and shutil.which("node"),
                         "Set JKDF2WEB_CLIENT_DIR for the exact published-JS oracle")
    async def test_published_javascript_download_and_rebuild(self):
        oracle = self.root / "oracle.json"
        files = [{"rel": rel, "data": base64.b64encode(path.read_bytes()).decode()} for rel, path, _ in a.list_mod_files(self.root / "mod")]
        oracle.write_text(json.dumps({"retail": base64.b64encode(self.fixture["retail"]).decode(),
                                     "mod_files": files, "episode_sha256": self.provider.info(0)["sha256"],
                                     "mod_sha256": self.provider.info(1)["sha256"]}))
        script = Path(__file__).with_name("check_published_assets.mjs")
        process = await asyncio.create_subprocess_exec("node", str(script),
                    str(Path(os.environ["JKDF2WEB_CLIENT_DIR"]) / "openjkdf2.js"),
                    self.url.replace("http:", "ws:") + "/relay", str(oracle),
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(process.communicate(), 25)
        self.assertEqual(process.returncode, 0, stderr.decode() + stdout.decode())
        result = json.loads(stdout.decode().strip().splitlines()[-1])
        self.assertTrue(result["passed"])
        self.assertFalse(result["published_code_modified"])
        print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    unittest.main()

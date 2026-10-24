"""Real loopback transport tests; no retail gameplay claim is implied."""
import asyncio
import base64
import contextlib
import json
import struct
import unittest

from aiohttp import ClientSession, WSMsgType, web
from .gateway import WebGateway, b64_json, browser_transport_payload
from .ipc import NativeIPC, encode_frame, read_frame


def descriptor(mode=0):
    value = bytearray(240)
    struct.pack_into("<ii", value, 16, 8, 0)
    name = "Transport fixture".encode("utf-16-le")
    value[24:24 + len(name)] = name
    episode = b"jkm_mp" if mode else b"jk1mp"
    value[88:88 + len(episode)] = episode
    value[120:126] = b"m2.jkl"
    struct.pack_into("<iii", value, 228, 0x1000, 50, 4)
    return bytes(value)


class EngineFixture:
    """IPC fixture echoes bytes; it does not simulate gameplay."""
    def __init__(self, mode=0):
        self.mode, self.next_id = mode, 65536
        self.connections, self.peers = set(), set()
        self.received = asyncio.Queue()
        self.pool = []

    async def handle(self, reader, writer):
        self.connections.add(writer)
        try:
            kind, source, destination, payload = await read_frame(reader)
            if kind != 1 or payload != b"fixture-token-1234567890":
                writer.write(encode_frame(199, 1, 1, b"authentication"))
                await writer.drain()
                return
            writer.write(encode_frame(101, payload=struct.pack("<I", 1)))
            await writer.drain()
            while True:
                kind, source, destination, payload = await read_frame(reader)
                if kind == 2:
                    writer.write(encode_frame(102, payload=struct.pack("<I", self.mode) + descriptor(self.mode)))
                elif kind == 3:
                    player = source or (self.pool.pop(0) if self.pool else self.next_id)
                    self.next_id += 1
                    self.peers.add(player)
                    writer.write(encode_frame(103, player, destination, struct.pack("<I", 0)))
                elif kind == 4:
                    self.peers.discard(source)
                    writer.write(encode_frame(104, source))
                elif kind == 5:
                    await self.received.put((source, destination, payload))
                    writer.write(encode_frame(105, 1, source, payload))
                elif kind == 7:
                    writer.write(encode_frame(107))
                elif kind == 8:
                    self.pool = list(struct.unpack("<" + "I" * (len(payload) // 4), payload))
                    writer.write(encode_frame(108, payload=struct.pack("<I", len(self.pool))))
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            self.connections.discard(writer)
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    async def close(self):
        for writer in tuple(self.connections):
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()


class GatewayIntegration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fixture = EngineFixture()
        self.server = await asyncio.start_server(self.fixture.handle, "127.0.0.1", 0)
        port = self.server.sockets[0].getsockname()[1]
        self.ipc = NativeIPC(port, "fixture-token-1234567890", reconnect_delay=0.02)
        self.gateway = WebGateway(self.ipc, enable_webrtc=True, hold_seconds=0.25)
        self.runner = web.AppRunner(self.gateway.create_app())
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await self.site.start()
        port = self.site._server.sockets[0].getsockname()[1]
        self.url = f"http://127.0.0.1:{port}"
        await self.ipc.connect()
        self.client = ClientSession()

    async def asyncTearDown(self):
        await self.gateway.close()
        await self.client.close()
        await self.runner.cleanup()
        await self.ipc.close()
        await self.fixture.close()
        self.server.close()
        await self.server.wait_closed()

    async def text(self, ws, prefix):
        async def get():
            while True:
                message = await ws.receive()
                if message.type == WSMsgType.TEXT and message.data.startswith(prefix):
                    return message.data
                if message.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                    self.fail("WebSocket closed waiting for " + prefix)
        return await asyncio.wait_for(get(), 5)

    async def join(self, game="jk1"):
        ws = await self.client.ws_connect(self.url + "/relay")
        await ws.send_str("hello " + game + " " + base64.b64encode(b"TestPilot").decode())
        await ws.send_str("join 1")
        seat = (await self.text(ws, "seat ")).split()
        welcome = (await self.text(ws, "welcome ")).split()
        self.assertEqual(len(bytes.fromhex(welcome[2])), 240)
        self.assertEqual(int(welcome[1]), int(seat[2]))
        return ws, int(seat[2]), seat[3]

    async def test_native_ipc_session_and_parallel_allocations(self):
        self.assertEqual(await self.ipc.info(), (0, descriptor()))
        ids = await asyncio.gather(self.ipc.add_peer(), self.ipc.add_peer())
        self.assertEqual(ids, [65536, 65537])
        for player in ids:
            await self.ipc.remove_peer(player)

    async def test_directplay_id_pool(self):
        self.assertEqual(await self.ipc.set_id_pool([1001, 1002]), 2)
        self.assertEqual(await self.ipc.add_peer(), 1001)

    async def test_browser_join_gate_transport_roster(self):
        header = struct.pack("<HH", 41, 123)
        payload = header + b"\x03" + struct.pack("<III", 1, 1001, 65536)
        self.assertEqual(browser_transport_payload(payload), header + b"\x01" + struct.pack("<I", 1))
        other = struct.pack("<HH", 42, 123) + payload[4:]
        self.assertEqual(browser_transport_payload(other), other)

    async def test_game_filter_and_wrong_game_join(self):
        async with self.client.ws_connect(self.url + "/relay") as ws:
            await ws.send_str("list mots")
            self.assertEqual(await self.text(ws, "list"), "list")
            await ws.send_str("list jk1")
            value = await self.text(ws, "list")
            self.assertEqual(bytes.fromhex(value.split()[3]), descriptor())
            await ws.send_str("hello mots " + base64.b64encode(b"Mara").decode())
            await ws.send_str("join 1")
            self.assertEqual(await self.text(ws, "error"), "error wrong-game")

    async def test_mots_session_descriptor_and_join(self):
        self.fixture.mode = 1
        self.assertEqual(await self.ipc.info(refresh=True), (1, descriptor(1)))
        ws, player, key = await self.join("mots")
        self.assertEqual(self.gateway.game, "mots")
        self.assertEqual(self.gateway.entry[88:94], b"jkm_mp")
        await ws.close()

    async def test_websocket_preserves_payload_and_stamps_source(self):
        ws, player, key = await self.join()
        payload = struct.pack("<HH", 1, 0) + b"fixture-sith-bytes"
        await ws.send_bytes(struct.pack("<II", 123456789, 1) + payload)
        self.assertEqual(await asyncio.wait_for(self.fixture.received.get(), 3), (player, 1, payload))
        response = await ws.receive(timeout=3)
        self.assertEqual(response.data, struct.pack("<II", 1, player) + payload)
        await ws.close()

    async def test_map_transfer_never_enters_game_engine(self):
        ws, player, key = await self.join()
        await ws.send_bytes(struct.pack("<II", player, 1) + b"JKMT\x01\x01\x00\x00")
        with self.assertRaises(TimeoutError):
            await asyncio.wait_for(self.fixture.received.get(), 0.05)
        self.assertEqual(self.gateway.metrics["map_requests"], 1)
        await ws.close()

    async def test_rejoin_key_preserves_player_and_wrong_key_rejected(self):
        ws, player, key = await self.join()
        await ws.close()
        again = await self.client.ws_connect(self.url + "/relay")
        await again.send_str(f"rejoin 1 {player} wrong")
        self.assertEqual(await self.text(again, "error"), "error no-seat")
        await again.send_str(f"rejoin 1 {player} {key}")
        self.assertEqual(await self.text(again, "rejoined"), f"rejoined 1 {player}")
        self.assertEqual(len(self.gateway.peers), 1)
        await again.send_str("leave")
        for _ in range(20):
            if player not in self.fixture.peers:
                break
            await asyncio.sleep(0.01)
        self.assertNotIn(player, self.fixture.peers)
        await again.close()

    async def test_origin_control(self):
        response = await self.client.get(self.url + "/relay", headers={"Origin": "https://unrelated.invalid"})
        self.assertEqual(response.status, 403)

    async def test_webrtc_negotiated_browser_channels(self):
        from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
        ws, player, key = await self.join()
        pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        channel = pc.createDataChannel("jk", negotiated=True, id=0, ordered=True)
        pc.createDataChannel("jk-map", negotiated=True, id=1, ordered=True)
        opened, received = asyncio.Event(), asyncio.Queue()
        @channel.on("open")
        def on_open():
            opened.set()
        @channel.on("message")
        def on_message(data):
            received.put_nowait(data)
        try:
            await pc.setLocalDescription(await pc.createOffer())
            await ws.send_str("signal 1 " + b64_json({"d": {"type": "offer", "sdp": pc.localDescription.sdp}}))
            signal = await self.text(ws, "signal 1 ")
            answer = json.loads(base64.b64decode(signal.split()[2]))["d"]
            await pc.setRemoteDescription(RTCSessionDescription(sdp=answer["sdp"], type="answer"))
            await asyncio.wait_for(opened.wait(), 5)
            payload = struct.pack("<HH", 1, 0) + b"rtc-fixture"
            channel.send(struct.pack("<II", 0, 1) + payload)
            self.assertEqual(await asyncio.wait_for(self.fixture.received.get(), 5), (player, 1, payload))
            self.assertEqual(await asyncio.wait_for(received.get(), 5), struct.pack("<II", 1, player) + payload)
            self.assertEqual(self.gateway.metrics["webrtc_in"], 1)
            self.assertEqual(self.gateway.metrics["webrtc_out"], 1)
        finally:
            await pc.close()
            await ws.close()


if __name__ == "__main__":
    unittest.main()

"""JKDF2Web lobby, WebSocket fallback, and WebRTC host-side transport.

Implements Tristamus' existing browser wire protocol. The game simulation
stays in the dedicated native engine. No browser or retail client patch is
applied by this module.
"""
from __future__ import annotations

import asyncio
import base64
import contextlib
from dataclasses import dataclass, field
import hmac
import json
import logging
from pathlib import Path
import secrets
import struct
import time
from urllib.parse import urlsplit

from aiohttp import WSMsgType, web

from .ipc import EngineUnavailable, MAX_SITH_PAYLOAD
from . import assets as asset_protocol

LOG = logging.getLogger(__name__)
MAX_MESSAGE = 65536
MAX_SIGNAL = 16384
GAMES = ("jk1", "mots")
ASSET_SUFFIXES = {".html", ".js", ".wasm", ".css", ".png", ".jpg", ".jpeg", ".svg", ".ico", ".webp", ".woff", ".woff2"}


def b64_json(value) -> str:
    return base64.b64encode(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()).decode()


def session_details(entry: bytes) -> dict:
    if len(entry) != 240:
        raise ValueError("Expected packed jkMultiEntry240")
    def narrow(offset, width=32):
        return entry[offset:offset + width].split(b"\0", 1)[0].decode("latin-1", "replace")
    def wide(offset):
        return entry[offset:offset + 64].decode("utf-16-le", "replace").split("\0", 1)[0]
    return {
        "name": wide(24), "episode": narrow(88), "map": narrow(120),
        "locked": bool(wide(152)), "max": max(0, struct.unpack_from("<i", entry, 16)[0] - 1),
        "transport_slots": struct.unpack_from("<i", entry, 16)[0],
        "players": struct.unpack_from("<i", entry, 20)[0], "mod": "",
        "flags": struct.unpack_from("<I", entry, 228)[0],
        "tick_ms": struct.unpack_from("<i", entry, 232)[0],
    }


def browser_transport_payload(payload: bytes) -> bytes:
    """DSS41 enumerates host1, matching the unchanged browser's transport.

    Hack_ResetClients has a synthetic 1..32 roster. Actual canonical retail
    DPIDs remain unchanged in gameplay; this adapts only the join gate.
    """
    if len(payload) >= 5 and struct.unpack_from("<H", payload)[0] == 41:
        if len(payload) == 5 + 4 * payload[4]:
            return payload[:4] + b"\x01" + struct.pack("<I", 1)
    return payload


@dataclass(eq=False)
class Connection:
    ws: web.WebSocketResponse
    game: str = ""
    name: str | None = None
    watch: bool = False
    peer: "Peer | None" = None


@dataclass(eq=False)
class Peer:
    id: int
    conn: Connection | None
    room: int
    name: str
    game: str
    key: str = field(default_factory=lambda: secrets.token_hex(16))
    pc: object | None = None
    channel: object | None = None
    map_channel: object | None = None
    hold_task: asyncio.Task | None = None
    incoming_task: asyncio.Task | None = None
    outgoing_task: asyncio.Task | None = None
    signal_task: asyncio.Task | None = None
    asset_task: asyncio.Task | None = None
    incoming: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=256))
    outgoing: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=256))
    signals: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=64))
    asset_requests: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=16))
    asset_pending: set = field(default_factory=set)
    asset_writable: asyncio.Event = field(default_factory=asyncio.Event)
    last_seen: float = field(default_factory=time.monotonic)
    closed: bool = False

    @property
    def rtc_open(self) -> bool:
        return bool(self.channel and self.channel.readyState == "open" and
                    self.pc and self.pc.connectionState == "connected")

    @property
    def map_rtc_open(self) -> bool:
        return bool(self.map_channel and self.map_channel.readyState == "open" and
                    self.pc and self.pc.connectionState == "connected")


class WebGateway:
    def __init__(self, engine, client_dir: Path | str | None = None, *,
                 enable_webrtc: bool = True, ice_servers: list | None = None,
                 hold_seconds: float = 60.0, allowed_origins: list[str] | None = None,
                 max_connections: int = 128, assets: asset_protocol.AssetProvider | None = None):
        self.engine = engine
        self.client_dir = Path(client_dir).resolve() if client_dir else None
        self.enable_webrtc = enable_webrtc
        self.ice_servers = ice_servers or []
        self.hold_seconds = hold_seconds
        self.allowed_origins = set(allowed_origins or [])
        self.max_connections = max_connections
        self.assets = assets
        self.connections: set[Connection] = set()
        self.peers: dict[int, Peer] = {}
        self.room_id = 1
        self.mode: int | None = None
        self.entry: bytes | None = None
        self._closed = False
        self._join_lock = asyncio.Lock()
        self._tasks: set[asyncio.Task] = set()
        self.metrics = {"websocket_in": 0, "websocket_out": 0, "webrtc_in": 0,
                        "webrtc_out": 0, "map_requests": 0, "queue_overflows": 0,
                        "asset_requests": 0, "asset_chunks": 0, "asset_bytes": 0,
                        "asset_wire_bytes": 0, "asset_denied": 0, "asset_request_drops": 0,
                        "active_asset_transfers": 0}
        self._unsubscribe = [engine.subscribe_data(self.on_engine_data),
                             engine.subscribe_state(self.on_engine_state),
                             engine.subscribe_info(self.on_engine_info)]
        if getattr(engine, "session", None):
            self.mode, self.entry = engine.session
        if enable_webrtc:
            try:
                import aiortc  # noqa: F401
            except ImportError as exc:
                raise RuntimeError("WebRTC requested; install web_gateway/requirements.txt or disable it") from exc

    @property
    def ready(self) -> bool:
        return bool(self.engine.connected and self.entry is not None and not self._closed)

    @property
    def game(self) -> str:
        return "mots" if self.mode == 1 else "jk1"

    @property
    def current_assets(self):
        if (self.assets and self.entry and self.mode == self.assets.mode and
                session_details(self.entry)["episode"].casefold() == self.assets.episode_name.casefold()):
            return self.assets
        return None

    def _entry_hex(self):
        provider = self.current_assets
        return self.entry.hex() + (provider.session_tail.hex() if provider else "")

    def _spawn(self, coro, name: str = "web-gateway") -> asyncio.Task:
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def on_engine_info(self, mode: int, entry: bytes) -> None:
        self.mode, self.entry = mode, entry
        await self._publish_status()

    async def on_engine_state(self, connected: bool) -> None:
        if not connected:
            for peer in tuple(self.peers.values()):
                if peer.conn:
                    await self._text(peer.conn, "host-left")
                await self._remove_peer(peer, notify_engine=False)
            self.entry = None
            self.mode = None
            self.room_id += 1
        elif getattr(self.engine, "session", None):
            self.mode, self.entry = self.engine.session
        await self._publish_status()

    async def on_engine_data(self, source: int, destination: int, payload: bytes) -> None:
        peer = self.peers.get(destination)
        if peer and not peer.closed:
            payload = browser_transport_payload(payload)
            packet = struct.pack("<II", source, destination) + payload
            try:
                peer.outgoing.put_nowait(packet)
            except asyncio.QueueFull:
                self.metrics["queue_overflows"] += 1
                self._spawn(self._remove_peer(peer), "web-peer-overflow")

    async def _text(self, conn: Connection, text: str) -> None:
        if not conn.ws.closed:
            with contextlib.suppress(ConnectionError, RuntimeError, TimeoutError):
                await asyncio.wait_for(conn.ws.send_str(text), timeout=2.0)

    def status(self) -> dict:
        lobby = sorted(c.name for c in self.connections if c.name is not None and c.peer is None)
        by_game = {g: {"online": 0, "lobby": sorted(c.name for c in self.connections
                     if c.game == g and c.name is not None and c.peer is None)} for g in GAMES}
        games = []
        if self.ready:
            info = session_details(self.entry)
            if self.current_assets:
                info["mod"] = self.current_assets.mod_name
            count = max(info["players"], len(self.peers))
            names = [p.name for p in sorted(self.peers.values(), key=lambda p: p.id)]
            games.append({k: info[k] for k in ("name", "episode", "map", "locked", "max", "mod")}
                         | {"id": self.room_id, "game": self.game, "players": count, "names": names})
            by_game[self.game]["online"] += count
        for value in by_game.values():
            value["online"] += len(value["lobby"])
        return {"online": sum(g["online"] for g in by_game.values()), "lobby": lobby,
                "byGame": by_game, "games": games}

    async def _publish_status(self) -> None:
        text = "status " + b64_json(self.status())
        watchers = [conn for conn in self.connections if conn.watch]
        if watchers:
            await asyncio.gather(*(self._text(conn, text) for conn in watchers))

    async def _join(self, conn: Connection, room: int) -> None:
        async with self._join_lock:
            if conn.peer:
                await self._remove_peer(conn.peer)
            if not self.ready or room != self.room_id:
                await self._text(conn, "error no-room")
                return
            if conn.game and conn.game != self.game:
                await self._text(conn, "error wrong-game")
                return
            info = session_details(self.entry)
            if info["max"] > 0 and max(info["players"], len(self.peers)) >= info["max"]:
                await self._text(conn, "error full")
                return
            try:
                peer_id = await self.engine.add_peer()
            except (EngineUnavailable, ConnectionError, TimeoutError):
                await self._text(conn, "error no-room")
                return
            # A state callback could run during allocation. Do not attach a
            # completed old request to a restarted native session.
            if not self.ready or room != self.room_id:
                await self.engine.remove_peer(peer_id)
                await self._text(conn, "error no-room")
                return
            peer = Peer(peer_id, conn, room, conn.name or "", conn.game or self.game)
            conn.peer = peer
            self.peers[peer_id] = peer
            peer.incoming_task = self._spawn(self._incoming_loop(peer), "web-peer-in")
            peer.outgoing_task = self._spawn(self._outgoing_loop(peer), "web-peer-out")
            peer.signal_task = self._spawn(self._signal_loop(peer), "web-peer-signals")
            await self._text(conn, f"seat {room} {peer_id} {peer.key}")
            await self._text(conn, f"welcome {peer_id} {self._entry_hex()}")
            await self._publish_status()

    async def _remove_peer(self, peer: Peer, *, notify_engine: bool = True) -> None:
        if peer.closed:
            return
        peer.closed = True
        self.peers.pop(peer.id, None)
        if peer.conn and peer.conn.peer is peer:
            peer.conn.peer = None
        peer.conn = None
        current = asyncio.current_task()
        for task in (peer.hold_task, peer.incoming_task, peer.outgoing_task, peer.signal_task, peer.asset_task):
            if task and task is not current:
                task.cancel()
        if peer.pc:
            with contextlib.suppress(Exception):
                await peer.pc.close()
        if notify_engine:
            with contextlib.suppress(ConnectionError, TimeoutError):
                await self.engine.remove_peer(peer.id)
        await self._publish_status()

    async def _hold_expiry(self, peer: Peer) -> None:
        while not peer.closed and peer.conn is None:
            await asyncio.sleep(self.hold_seconds)
            if peer.conn is not None:
                return
            # A live RTC player keeps playing if only its lobby socket drops.
            if peer.rtc_open and time.monotonic() - peer.last_seen < self.hold_seconds:
                continue
            await self._remove_peer(peer)
            return

    async def _disconnect(self, conn: Connection) -> None:
        self.connections.discard(conn)
        peer = conn.peer
        if peer and peer.conn is conn:
            peer.conn = None
            if not peer.map_rtc_open:
                self._cancel_asset_work(peer)
            if peer.hold_task:
                peer.hold_task.cancel()
            peer.hold_task = self._spawn(self._hold_expiry(peer), "web-peer-hold")
        conn.peer = None
        await self._publish_status()

    async def _rejoin(self, conn: Connection, args: list[str]) -> None:
        if len(args) != 3:
            await self._text(conn, "error bad-request")
            return
        try:
            room, peer_id = int(args[0]), int(args[1])
        except ValueError:
            await self._text(conn, "error no-seat")
            return
        peer = self.peers.get(peer_id)
        if (not self.ready or not peer or room != peer.room or room != self.room_id or
                not hmac.compare_digest(peer.key, args[2])):
            await self._text(conn, "error no-seat")
            return
        if conn.peer and conn.peer is not peer:
            await self._remove_peer(conn.peer)
        old = peer.conn
        if old and old is not conn:
            old.peer = None
            await old.ws.close(code=4001, message=b"replaced")
        conn.peer, peer.conn = peer, conn
        peer.last_seen = time.monotonic()
        if peer.hold_task:
            peer.hold_task.cancel()
            peer.hold_task = None
        await self._text(conn, f"rejoined {room} {peer.id}")
        await self._publish_status()

    async def handle_text(self, conn: Connection, line: str) -> None:
        parts = line.split()
        if not parts:
            return
        op, args = parts[0], parts[1:]
        if op == "ping" and not args:
            if conn.peer:
                conn.peer.last_seen = time.monotonic()
        elif op == "hello" and len(args) == 2 and args[0] in GAMES:
            try:
                raw = base64.b64decode(args[1], validate=True)
                if len(raw) > 128:
                    raise ValueError("name too long")
                name = raw.decode("utf-8")
                name = "".join(c for c in name if c.isprintable())[:31]
            except (ValueError, UnicodeError):
                await self._text(conn, "error bad-request")
                return
            conn.game, conn.name = args[0], name
            if conn.peer:
                conn.peer.name, conn.peer.game = name, args[0]
            await self._publish_status()
        elif op == "watch" and not args:
            conn.watch = True
            await self._text(conn, "status " + b64_json(self.status()))
        elif op == "list" and len(args) <= 1:
            if self.ready and (not args or args[0] == self.game):
                count = max(session_details(self.entry)["players"], len(self.peers))
                await self._text(conn, f"list {self.room_id} {count} {self._entry_hex()}")
            else:
                await self._text(conn, "list")
        elif op == "join" and len(args) == 1 and args[0].isdigit():
            await self._join(conn, int(args[0]))
        elif op == "leave" and not args:
            if conn.peer:
                await self._remove_peer(conn.peer)
        elif op == "rejoin":
            await self._rejoin(conn, args)
        elif op == "signal" and len(args) == 2 and args[0] == "1" and conn.peer:
            if self.enable_webrtc:
                try:
                    if len(args[1]) > MAX_SIGNAL:
                        raise ValueError("signal too long")
                    obj = json.loads(base64.b64decode(args[1], validate=True))
                    conn.peer.signals.put_nowait(obj)
                except (ValueError, TypeError, asyncio.QueueFull):
                    await self._text(conn, "error bad-signal")
        elif op in ("host", "update", "welcome", "rehost"):
            await self._text(conn, "error dedicated-only")
        else:
            await self._text(conn, "error bad-request")

    def receive_packet(self, peer: Peer, packet: bytes, transport: str) -> None:
        if peer.closed or not isinstance(packet, bytes) or not 12 <= len(packet) <= MAX_MESSAGE:
            return
        peer.last_seen = time.monotonic()
        if packet[8:12] == b"JKMT":
            # Transfer control is separate from the Sith VM and may be much
            # larger than a game packet. Its authenticated source is peer.id.
            self.metrics["map_requests"] += 1
            self._receive_asset(peer, packet, transport)
            return
        if len(packet) > MAX_SITH_PAYLOAD + 8:
            return
        destination = struct.unpack_from("<I", packet, 4)[0]
        try:
            # Source comes from the authenticated seat, never from the frame.
            peer.incoming.put_nowait((destination, packet[8:]))
            self.metrics[transport + "_in"] += 1
        except asyncio.QueueFull:
            self.metrics["queue_overflows"] += 1
            self._spawn(self._remove_peer(peer), "web-peer-overflow")

    def _cancel_asset_work(self, peer):
        if peer.asset_task:
            peer.asset_task.cancel()
            peer.asset_task = None
        peer.asset_pending.clear()
        while not peer.asset_requests.empty():
            with contextlib.suppress(asyncio.QueueEmpty):
                peer.asset_requests.get_nowait()

    def _receive_asset(self, peer, packet, transport):
        provider = self.current_assets
        if (provider is None or len(packet) < asset_protocol.HEADER or
                struct.unpack_from("<I", packet, 4)[0] != 1 or packet[13] != 1 or
                packet[14] not in (asset_protocol.MAP, asset_protocol.MOD) or packet[15] != 0):
            return
        kind = packet[12]
        if ((kind == asset_protocol.INFO_REQUEST and len(packet) != 16) or
                (kind == asset_protocol.CHUNK_REQUEST and len(packet) != 36) or
                kind not in (asset_protocol.INFO_REQUEST, asset_protocol.CHUNK_REQUEST)):
            return
        self.metrics["asset_requests"] += 1
        if not provider.download_enabled and kind == asset_protocol.CHUNK_REQUEST:
            self.metrics["asset_denied"] += 1
            return
        key = (transport, packet[12:])
        if key in peer.asset_pending:
            return
        try:
            peer.asset_requests.put_nowait((key, packet, transport))
            peer.asset_pending.add(key)
        except asyncio.QueueFull:
            # The existing client retries missing chunks. Do not evict a
            # game player because its finite asset-request queue is full.
            self.metrics["asset_request_drops"] += 1
            return
        if peer.asset_task is None or peer.asset_task.done():
            peer.asset_task = self._spawn(self._asset_loop(peer), "web-peer-assets")

    async def _asset_loop(self, peer):
        while not peer.closed:
            key, request, transport = await peer.asset_requests.get()
            active = False
            try:
                provider = self.current_assets
                if provider is None:
                    continue
                if request[12] == asset_protocol.INFO_REQUEST:
                    if request[14] == asset_protocol.MOD and not provider.download_enabled:
                        self.metrics["asset_denied"] += 1
                    await self._send_asset_packet(peer, asset_protocol.info_frame(provider, peer.id, request[14]), transport)
                    continue
                self.metrics["active_asset_transfers"] += 1
                active = True
                for packet in asset_protocol.chunk_frames(provider, peer.id, request):
                    if peer.closed or not await self._send_asset_packet(peer, packet, transport):
                        break
                    await asyncio.sleep(0)
            finally:
                if active:
                    self.metrics["active_asset_transfers"] -= 1
                peer.asset_pending.discard(key)

    async def _send_asset_packet(self, peer, packet, transport):
        if peer.closed:
            return False
        sent = False
        if transport == "webrtc":
            # Keep bulk transfer off the game channel and bound SCTP output.
            # A stuck RTC queue falls back to the same frame on WebSocket;
            # the unchanged client deduplicates chunks by hash/index.
            deadline = time.monotonic() + 8.0
            while peer.map_rtc_open and peer.map_channel.bufferedAmount > 256 * 1024 and not peer.closed:
                peer.asset_writable.clear()
                if peer.map_channel.bufferedAmount <= 256 * 1024:
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(peer.asset_writable.wait(), min(1.0, remaining))
            if peer.closed:
                return False
            if peer.map_rtc_open and peer.map_channel.bufferedAmount <= 256 * 1024:
                try:
                    peer.map_channel.send(packet)
                    self.metrics["webrtc_out"] += 1
                    sent = True
                except Exception:
                    pass
        if not sent:
            conn = peer.conn
            if not conn or conn.ws.closed or peer.closed:
                return False
            try:
                await asyncio.wait_for(conn.ws.send_bytes(packet), timeout=5.0)
                self.metrics["websocket_out"] += 1
                sent = True
            except (ConnectionError, RuntimeError, TimeoutError):
                return False
        self.metrics["asset_wire_bytes"] += len(packet)
        if packet[12] == asset_protocol.CHUNK:
            self.metrics["asset_chunks"] += 1
            self.metrics["asset_bytes"] += len(packet) - 28
        return sent

    async def _incoming_loop(self, peer: Peer) -> None:
        try:
            while not peer.closed:
                destination, payload = await peer.incoming.get()
                await self.engine.send(peer.id, destination, payload)
        except (EngineUnavailable, ConnectionError):
            await self._remove_peer(peer)

    async def _outgoing_loop(self, peer: Peer) -> None:
        try:
            while not peer.closed:
                packet = await peer.outgoing.get()
                if peer.rtc_open:
                    if peer.channel.bufferedAmount > 1024 * 1024:
                        raise ConnectionError("Slow WebRTC recipient")
                    try:
                        peer.channel.send(packet)
                        self.metrics["webrtc_out"] += 1
                        continue
                    except (ConnectionError, RuntimeError):
                        pass
                conn = peer.conn
                if conn and not conn.ws.closed:
                    await asyncio.wait_for(conn.ws.send_bytes(packet), timeout=2.0)
                    self.metrics["websocket_out"] += 1
        except (ConnectionError, TimeoutError):
            await self._remove_peer(peer)

    async def _signal_loop(self, peer: Peer) -> None:
        while not peer.closed:
            obj = await peer.signals.get()
            try:
                await self._signal(peer, obj)
            except Exception:
                LOG.info("WebRTC negotiation failed for player %s; WebSocket remains available", peer.id)
                if peer.pc:
                    with contextlib.suppress(Exception):
                        await peer.pc.close()
                    peer.pc = peer.channel = peer.map_channel = None

    async def _signal(self, peer: Peer, obj: dict) -> None:
        if not isinstance(obj, dict):
            return
        from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription
        from aiortc.sdp import candidate_from_sdp
        description = obj.get("d")
        if isinstance(description, dict) and description.get("type") == "offer":
            if peer.pc:
                await peer.pc.close()
            servers = [RTCIceServer(**config) for config in self.ice_servers]
            pc = peer.pc = RTCPeerConnection(RTCConfiguration(iceServers=servers))
            channel = peer.channel = pc.createDataChannel("jk", negotiated=True, id=0, ordered=True)
            map_channel = peer.map_channel = pc.createDataChannel("jk-map", negotiated=True, id=1, ordered=True)
            map_channel.bufferedAmountLowThreshold = 128 * 1024

            @map_channel.on("bufferedamountlow")
            @map_channel.on("open")
            @map_channel.on("close")
            def on_map_writable():
                peer.asset_writable.set()

            @channel.on("message")
            def on_message(data):
                if peer.pc is pc:
                    self.receive_packet(peer, data, "webrtc")

            @map_channel.on("message")
            def on_map(data):
                if peer.pc is pc:
                    self.receive_packet(peer, data, "webrtc")

            await pc.setRemoteDescription(RTCSessionDescription(sdp=description["sdp"], type="offer"))
            await pc.setLocalDescription(await pc.createAnswer())
            if peer.closed or peer.pc is not pc:
                await pc.close()
                return
            if peer.conn:
                await self._text(peer.conn, "signal 1 " + b64_json({"d": {
                    "type": pc.localDescription.type, "sdp": pc.localDescription.sdp}}))
        elif isinstance(obj.get("c"), dict) and peer.pc:
            data = obj["c"]
            raw = data.get("candidate", "")
            if raw.startswith("candidate:"):
                candidate = candidate_from_sdp(raw[len("candidate:"):])
                candidate.sdpMid = data.get("sdpMid")
                candidate.sdpMLineIndex = data.get("sdpMLineIndex")
                await peer.pc.addIceCandidate(candidate)

    async def websocket(self, request: web.Request) -> web.StreamResponse:
        origin = request.headers.get("Origin")
        if origin:
            parsed = urlsplit(origin)
            same_host = parsed.scheme in ("http", "https") and parsed.netloc == request.host
            if not same_host and origin not in self.allowed_origins:
                raise web.HTTPForbidden(text="Origin is not allowed")
        if len(self.connections) >= self.max_connections:
            raise web.HTTPServiceUnavailable(text="Connection limit reached")
        ws = web.WebSocketResponse(max_msg_size=MAX_MESSAGE, heartbeat=30, receive_timeout=120)
        await ws.prepare(request)
        conn = Connection(ws)
        self.connections.add(conn)
        if self.ice_servers:
            await self._text(conn, "ice " + b64_json(self.ice_servers))
        try:
            async for message in ws:
                if message.type == WSMsgType.TEXT:
                    if len(message.data) > 32768:
                        await ws.close(code=1009, message=b"Control message too long")
                        break
                    await self.handle_text(conn, message.data)
                elif message.type == WSMsgType.BINARY and conn.peer:
                    self.receive_packet(conn.peer, message.data, "websocket")
                elif message.type == WSMsgType.ERROR:
                    break
        except (ConnectionError, TimeoutError):
            pass
        finally:
            await self._disconnect(conn)
        return ws

    async def health(self, request: web.Request) -> web.Response:
        return web.json_response({"ready": self.ready, "game": self.game if self.ready else None,
                                  "web_peers": len(self.peers), "webrtc": self.enable_webrtc,
                                  "metrics": self.metrics,
                                  "assets": self.current_assets.summary() if self.current_assets else None})

    async def asset(self, request: web.Request) -> web.StreamResponse:
        if not self.client_dir:
            raise web.HTTPNotFound(text="Install the unchanged browser build and configure client_dir")
        name = request.match_info.get("asset", "") or "index.html"
        path = (self.client_dir / name).resolve()
        if not path.is_relative_to(self.client_dir) or path.suffix.lower() not in ASSET_SUFFIXES or not path.is_file():
            raise web.HTTPNotFound()
        return web.FileResponse(path, headers={"Cross-Origin-Opener-Policy": "same-origin",
                                               "Cross-Origin-Embedder-Policy": "require-corp",
                                               "X-Content-Type-Options": "nosniff"})

    def create_app(self) -> web.Application:
        app = web.Application(client_max_size=MAX_MESSAGE)
        app.router.add_get("/relay", self.websocket)
        app.router.add_get("/health", self.health)
        app.router.add_get("/", self.asset)
        app.router.add_get("/{asset:.*}", self.asset)
        return app

    async def close(self) -> None:
        self._closed = True
        for unsubscribe in self._unsubscribe:
            unsubscribe()
        for peer in tuple(self.peers.values()):
            await self._remove_peer(peer)
        for conn in tuple(self.connections):
            await conn.ws.close(code=1001, message=b"Gateway stopped")
        for task in tuple(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*tuple(self._tasks), return_exceptions=True)


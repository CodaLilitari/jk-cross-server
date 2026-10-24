"""Authenticated loopback adapter endpoint sharing the single native IPC connection."""
from __future__ import annotations
import asyncio
import hmac
import struct

U32 = struct.Struct("<I")
FIELDS = struct.Struct("<III")
MAX_FRAME = 65536

async def receive(reader):
    length = U32.unpack(await reader.readexactly(4))[0]
    if not 12 <= length <= MAX_FRAME:
        raise ValueError("Invalid frame length")
    raw = await reader.readexactly(length)
    return (*FIELDS.unpack_from(raw), raw[12:])

def encode(kind, src=0, dst=0, payload=b""):
    body = FIELDS.pack(kind, src, dst) + payload
    if len(body) > MAX_FRAME:
        raise ValueError("Frame too large")
    return U32.pack(len(body)) + body

class AdapterBroker:
    def __init__(self, engine, token: str, port=46001, log=lambda s: None):
        self.engine, self.token, self.port, self.log = engine, token, port, log
        self.server = None
        self.clients = set()
        self.owners = {}
        self.tasks = set()
        self.pool_owner = None
        self.pool_ready = asyncio.Event()
        engine.subscribe_data(self.on_data)
        engine.subscribe_state(self.on_state)
        engine.subscribe_info(self.on_info)

    async def start(self):
        self.server = await asyncio.start_server(self.accept, "127.0.0.1", self.port, limit=MAX_FRAME + 4)

    async def on_data(self, src, dst, payload):
        client = self.owners.get(dst)
        # Pool-backed native/browser peers are local DirectPlay surrogates. Their
        # incoming retail packets are handled by the adapter, while native sends
        # only data whose destination is an actual registered retail peer here.
        if client:
            await client.send(105, src, dst, payload)

    async def on_state(self, connected):
        if not connected:
            self.pool_ready.clear()
            for client in list(self.clients):
                client.writer.close()

    async def on_info(self, mode, entry):
        for client in list(self.clients):
            if client.authenticated:
                await client.send(102, payload=U32.pack(mode) + entry)

    async def accept(self, reader, writer):
        task = asyncio.current_task()
        self.tasks.add(task)
        client = AdapterClient(self, reader, writer)
        self.clients.add(client)
        try:
            if len(self.clients) > 4:
                return
            kind, src, dst, payload = await asyncio.wait_for(receive(reader), 5)
            if kind != 1 or not hmac.compare_digest(payload, self.token.encode()):
                await client.send(199, kind, 1, b"Authentication failed")
                return
            client.authenticated = True
            await client.send(101, payload=U32.pack(1))
            while True:
                kind, src, dst, payload = await receive(reader)
                try:
                    if kind == 2:
                        mode, entry = await self.engine.info()
                        await client.send(102, payload=U32.pack(mode) + entry)
                    elif kind == 3:
                        peer = await self.engine.add_peer(src)
                        self.owners[peer] = client
                        client.peers.add(peer)
                        await client.send(103, peer, dst, U32.pack(0))
                        self.log(f"Retail transport peer {peer} registered")
                    elif kind == 4:
                        if src not in client.peers:
                            raise ValueError("Peer not owned by this adapter")
                        await self.engine.remove_peer(src)
                        client.peers.discard(src)
                        self.owners.pop(src, None)
                        await client.send(104, src, dst)
                    elif kind == 5:
                        if src not in client.peers or not 4 <= len(payload) <= 2052:
                            raise ValueError("Unknown sender or invalid Sith payload")
                        await self.engine.send(src, dst, payload)
                    elif kind == 7:
                        await client.send(107, src, dst, payload)
                    elif kind == 8:
                        if self.pool_owner not in (None, client):
                            raise ValueError("Another adapter owns the DirectPlay pool")
                        if len(payload) % 4 or not 1 <= len(payload) // 4 <= 15:
                            raise ValueError("Expected 1–15 DirectPlay player IDs")
                        ids = list(struct.unpack(f"<{len(payload)//4}I", payload))
                        if len(set(ids)) != len(ids) or any(n < 65 for n in ids):
                            raise ValueError("Invalid DirectPlay pool IDs")
                        await self.engine.set_id_pool(ids)
                        self.pool_owner = client
                        self.pool_ready.set()
                        await client.send(108, 0, dst, U32.pack(len(ids)))
                        self.log(f"DirectPlay pool ready ({len(ids)} surrogate identities)")
                    else:
                        raise ValueError("Unknown command")
                except (ValueError, RuntimeError, asyncio.TimeoutError) as exc:
                    await client.send(199, kind, 2, str(exc).encode()[:2048])
        except (asyncio.IncompleteReadError, ConnectionError, ValueError, asyncio.TimeoutError):
            pass
        finally:
            self.clients.discard(client)
            for peer in list(client.peers):
                self.owners.pop(peer, None)
                try:
                    await self.engine.remove_peer(peer)
                except (RuntimeError, ConnectionError, asyncio.TimeoutError):
                    pass
            if self.pool_owner is client:
                self.pool_owner = None
                self.pool_ready.clear()
                self.log("DirectPlay adapter disconnected; mixed session must restart")
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass
            self.tasks.discard(task)

    async def close(self):
        if self.server:
            self.server.close()
        for client in list(self.clients):
            client.writer.close()
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if self.server:
            await self.server.wait_closed()

class AdapterClient:
    def __init__(self, broker, reader, writer):
        self.broker, self.reader, self.writer = broker, reader, writer
        self.authenticated = False
        self.peers = set()
        self.lock = asyncio.Lock()

    async def send(self, kind, src=0, dst=0, payload=b""):
        async with self.lock:
            if self.writer.is_closing():
                return
            self.writer.write(encode(kind, src, dst, payload))
            await asyncio.wait_for(self.writer.drain(), 5)

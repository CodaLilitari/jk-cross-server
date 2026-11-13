"""Authenticated loopback adapter endpoint sharing the single native IPC connection."""
from __future__ import annotations
import asyncio
import contextlib
import hmac
import struct
from web_gateway.ipc import REPLACE_POOL_ID, POOL_REPLACED, POOL_RETIRED

U32 = struct.Struct("<I")
FIELDS = struct.Struct("<III")
MAX_FRAME = 65536
MAX_ISSUED_IDENTITIES = 65536
MAX_POOL_REPLACEMENTS = 15

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
        self.pool_ids = set()
        self.pool_history = set()
        self.issued_ids = {1}
        self.pool_retired = set()
        self.pool_notified = set()
        self.pool_replacements = {}
        self.pool_pending = {}
        self._pool_notifications = asyncio.Lock()
        self._identity_lock = asyncio.Lock()
        engine.subscribe_data(self.on_data)
        engine.subscribe_state(self.on_state)
        engine.subscribe_info(self.on_info)
        if hasattr(engine, "subscribe_removed"):
            engine.subscribe_removed(self.on_removed)
        if hasattr(engine, "subscribe_pool_retired"):
            engine.subscribe_pool_retired(self.on_pool_retired)

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

    async def on_removed(self, peer_id):
        client = self.owners.pop(peer_id, None)
        if client:
            client.peers.discard(peer_id)
            client.retired_peers.add(peer_id)
            await client.send(104, peer_id)

    async def on_pool_retired(self, peer_id):
        if peer_id in self.pool_replacements:
            return
        if peer_id not in self.pool_ids and peer_id not in self.pool_pending:
            self.log("Unexpected surrogate retirement; mixed session must restart")
            if self.pool_owner:
                self.pool_owner.writer.close()
            return
        self.pool_retired.add(peer_id)
        await self._flush_pool_retirements()

    async def _flush_pool_retirements(self):
        # Reader callbacks never await an engine request. Retain events until
        # the preceding registration ACK has been sent to the adapter.
        async with self._pool_notifications:
            client = self.pool_owner
            if not client or not client.pool_registered or client.pool_replacing:
                return
            for peer_id in sorted(self.pool_retired - self.pool_notified):
                if client.pool_replacing or self.pool_owner is not client:
                    break
                if peer_id not in self.pool_ids:
                    continue
                await client.send(POOL_RETIRED, peer_id)
                self.pool_notified.add(peer_id)

    async def _add_retail(self, client, peer_id, request_id):
        async with self._identity_lock:
            if not 65 <= peer_id < 0xFFFFFFFE or peer_id in self.issued_ids:
                raise ValueError("A retail connection requires a fresh DirectPlay identity")
            if len(self.issued_ids) >= MAX_ISSUED_IDENTITIES:
                raise ValueError("Identity lifetime limit reached; restart the session")
            peer = await self.engine.add_peer(peer_id)
            if peer != peer_id:
                raise ValueError("Engine returned a different retail identity")
            self.issued_ids.add(peer)
            self.owners[peer] = client
            client.peers.add(peer)
        await client.send(103, peer, request_id, U32.pack(0))
        self.log(f"Retail transport peer {peer} registered")

    async def _install_pool(self, client, request_id, payload):
        async with self._identity_lock:
            if self.pool_owner is not None or self.pool_history:
                raise ValueError("A DirectPlay pool is already registered for this session")
            if len(payload) % 4 or not 1 <= len(payload) // 4 <= 15:
                raise ValueError("Expected 1–15 DirectPlay player IDs")
            ids = list(struct.unpack(f"<{len(payload)//4}I", payload))
            if (len(set(ids)) != len(ids) or any(not 65 <= n < 0xFFFFFFFE for n in ids)
                    or any(n in self.issued_ids for n in ids)):
                raise ValueError("Invalid or previously issued DirectPlay pool IDs")
            if len(self.issued_ids) + len(ids) > MAX_ISSUED_IDENTITIES:
                raise ValueError("Identity lifetime limit reached; restart the session")
            # Ownership precedes the await: native retirement can arrive in
            # the same IPC read batch as the initial registration ACK.
            self.pool_owner = client
            self.pool_ids = set(ids)
            self.pool_history = set(ids)
            self.issued_ids.update(ids)
            await self.engine.set_id_pool(ids)
            await client.send(108, 0, request_id, U32.pack(len(ids)))
            client.pool_registered = True
            self.pool_ready.set()
        await self._flush_pool_retirements()
        self.log(f"DirectPlay pool ready ({len(ids)} surrogate identities)")

    async def _replace_pool(self, client, old_id, request_id, payload):
        async with self._identity_lock:
            if client is not self.pool_owner or not client.pool_registered:
                raise ValueError("Only the registered pool owner may replace identities")
            if not request_id or len(payload) != 4:
                raise ValueError("Invalid surrogate replacement request")
            new_id = U32.unpack(payload)[0]
            previous = self.pool_replacements.get(old_id)
            if previous is not None:
                if previous != new_id:
                    raise ValueError("Retired identity already has a different replacement")
                await client.send(POOL_REPLACED, old_id, request_id, payload)
                return
            if (old_id not in self.pool_ids or old_id not in self.pool_retired
                    or not 65 <= new_id < 0xFFFFFFFE or new_id in self.issued_ids):
                raise ValueError("Replacement requires a retired slot and a fresh identity")
            if len(self.issued_ids) >= MAX_ISSUED_IDENTITIES:
                raise ValueError("Identity lifetime limit reached; restart the session")
            client.pool_replacing = True
            self.pool_pending[new_id] = old_id
            try:
                accepted = await self.engine.replace_pool_id(old_id, new_id)
                if accepted != new_id:
                    raise ValueError("Engine returned a different surrogate identity")
                self.pool_ids.remove(old_id)
                self.pool_ids.add(new_id)
                self.pool_history.add(new_id)
                self.issued_ids.add(new_id)
                self.pool_replacements[old_id] = new_id
                self.pool_retired.discard(old_id)
                await client.send(POOL_REPLACED, old_id, request_id, payload)
                self.log(f"Retired surrogate {old_id} replaced with fresh DirectPlay identity {new_id}")
            finally:
                self.pool_pending.pop(new_id, None)
                client.pool_replacing = False
        await self._flush_pool_retirements()

    def _queue_pool_replacement(self, client, old_id, request_id, payload):
        if client is not self.pool_owner or not client.pool_registered:
            raise ValueError("Only the registered pool owner may replace identities")
        if not request_id or len(payload) != 4:
            raise ValueError("Invalid surrogate replacement request")
        if client.pool_request_count >= MAX_POOL_REPLACEMENTS:
            raise ValueError("Surrogate replacement queue is full")
        client.pool_requests.put_nowait((old_id, request_id, payload))
        client.pool_request_count += 1
        if client.pool_worker is None:
            client.pool_worker = asyncio.create_task(self._replace_pool_worker(client))

    async def _replace_pool_worker(self, client):
        # One bounded serial worker keeps this same adapter's DATA/REMOVE/INFO
        # receive path responsive while the native replacement ACK is pending.
        while True:
            old_id, request_id, payload = await client.pool_requests.get()
            try:
                await self._replace_pool(client, old_id, request_id, payload)
            except (ValueError, RuntimeError, ConnectionError, asyncio.TimeoutError) as exc:
                try:
                    await client.send(199, REPLACE_POOL_ID, 2, str(exc).encode()[:2048])
                finally:
                    # The old physical player may already have been destroyed.
                    # An uncertain replacement requires restarting this adapter.
                    client.writer.close()
                return
            finally:
                client.pool_request_count -= 1

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
                        await self._add_retail(client, src, dst)
                    elif kind == 4:
                        if src in client.retired_peers:
                            # Keep this marker through duplicate departure and
                            # already-buffered packets. A new incarnation must
                            # have a fresh ordinary DirectPlay identity.
                            await client.send(104, src, dst)
                            continue
                        if src not in client.peers:
                            raise ValueError("Peer not owned by this adapter")
                        client.peers.discard(src)
                        client.retired_peers.add(src)
                        self.owners.pop(src, None)
                        await self.engine.remove_peer(src)
                        await client.send(104, src, dst)
                    elif kind == 5:
                        if src in client.retired_peers:
                            # Ordinary DSS_QUIT and DirectPlay's destruction
                            # notice race with packets already in flight.
                            # Retire only that seat, not the shared adapter.
                            continue
                        if src not in client.peers or not 4 <= len(payload) <= 2052:
                            raise ValueError("Unknown sender or invalid Sith payload")
                        await self.engine.send(src, dst, payload)
                    elif kind == 7:
                        await client.send(107, src, dst, payload)
                    elif kind == 8:
                        await self._install_pool(client, dst, payload)
                    elif kind == REPLACE_POOL_ID:
                        self._queue_pool_replacement(client, src, dst, payload)
                    else:
                        raise ValueError("Unknown command")
                except (ValueError, RuntimeError, asyncio.TimeoutError) as exc:
                    await client.send(199, kind, 2, str(exc).encode()[:2048])
                    if kind in (8, REPLACE_POOL_ID) and self.pool_owner is client:
                        break
        except (asyncio.IncompleteReadError, ConnectionError, ValueError, asyncio.TimeoutError):
            pass
        finally:
            self.clients.discard(client)
            if client.pool_worker is not None:
                client.pool_worker.cancel()
                with contextlib.suppress(asyncio.CancelledError, ConnectionError):
                    await client.pool_worker
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
        self.retired_peers = set()
        self.pool_registered = False
        self.pool_replacing = False
        self.pool_requests = asyncio.Queue(maxsize=MAX_POOL_REPLACEMENTS)
        self.pool_request_count = 0
        self.pool_worker = None
        self.lock = asyncio.Lock()

    async def send(self, kind, src=0, dst=0, payload=b""):
        async with self.lock:
            if self.writer.is_closing():
                return
            self.writer.write(encode(kind, src, dst, payload))
            await asyncio.wait_for(self.writer.drain(), 5)

"""Real loopback IPC/broker checks; fixtures do not claim DirectPlay gameplay."""
import asyncio
import contextlib
import struct
import unittest
from unittest import mock

from manager.broker import AdapterBroker, encode, receive
from web_gateway.ipc import (NativeIPC, ProtocolError, encode_frame, read_frame,
                             POOL_REPLACED, POOL_RETIRED, REPLACE_POOL_ID)


class PoolWireFixture:
    def __init__(self):
        self.writers, self.tasks = set(), set()
        self.pool, self.retired, self.peers = [], set(), set()
        self.replacements, self.received = [], asyncio.Queue()
        self.requested = asyncio.Queue()
        self.release = asyncio.Event()
        self.release.set()
        self.retire_at_registration = False
        self.retire_at_replacement = False

    async def emit(self, data):
        for writer in tuple(self.writers):
            writer.write(data)
            await writer.drain()

    async def retire(self, peer):
        self.peers.discard(peer)
        self.retired.add(peer)
        await self.emit(encode_frame(104, peer) + encode_frame(POOL_RETIRED, peer))

    async def replace(self, writer, old, request, new):
        await self.release.wait()
        self.pool[self.pool.index(old)] = new
        self.retired.discard(old)
        data = encode_frame(POOL_REPLACED, old, request, struct.pack("<I", new))
        if self.retire_at_replacement:
            self.retired.add(new)
            data += encode_frame(POOL_RETIRED, new)
        writer.write(data)
        await writer.drain()

    async def handle(self, reader, writer):
        self.writers.add(writer)
        try:
            kind, _, _, token = await read_frame(reader)
            if kind != 1 or token != b"fixture-engine-token":
                return
            writer.write(encode_frame(101, payload=struct.pack("<I", 1)))
            await writer.drain()
            while True:
                kind, source, destination, payload = await read_frame(reader)
                if kind == 2:
                    writer.write(encode_frame(102, payload=bytes(244)))
                elif kind == 8:
                    self.pool = list(struct.unpack("<" + "I" * (len(payload) // 4), payload))
                    writer.write(encode_frame(108, payload=struct.pack("<I", len(self.pool))))
                    if self.retire_at_registration:
                        self.retired.add(self.pool[0])
                        writer.write(encode_frame(POOL_RETIRED, self.pool[0]))
                elif kind == 3:
                    self.peers.add(source)
                    writer.write(encode_frame(103, source, destination, bytes(4)))
                elif kind == 4:
                    self.peers.discard(source)
                    writer.write(encode_frame(104, source))
                elif kind == 5:
                    await self.received.put((source, destination, payload))
                    writer.write(encode_frame(105, 1, source, payload))
                elif kind == REPLACE_POOL_ID:
                    new = struct.unpack("<I", payload)[0]
                    self.replacements.append((source, new))
                    await self.requested.put((source, new))
                    task = asyncio.create_task(self.replace(writer, source, destination, new))
                    self.tasks.add(task)
                    task.add_done_callback(self.tasks.discard)
                elif kind == 7:
                    writer.write(encode_frame(107))
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            self.writers.discard(writer)
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    async def close(self):
        for task in tuple(self.tasks):
            task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        for writer in tuple(self.writers):
            writer.close()


class SurrogatePoolIntegration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = PoolWireFixture()
        self.server = await asyncio.start_server(self.engine.handle, "127.0.0.1", 0)
        self.ipc = NativeIPC(self.server.sockets[0].getsockname()[1], "fixture-engine-token",
                             reconnect_delay=100)
        await self.ipc.connect()
        self.broker = AdapterBroker(self.ipc, "fixture-adapter-token", port=0)
        await self.broker.start()
        self.connections = []
        self.reader, self.writer = await self.connect_adapter()

    async def asyncTearDown(self):
        for _, writer in self.connections:
            writer.close()
        await self.broker.close()
        await self.ipc.close()
        await self.engine.close()
        self.server.close()
        await self.server.wait_closed()

    async def connect_adapter(self):
        reader, writer = await asyncio.open_connection("127.0.0.1", self.broker.server.sockets[0].getsockname()[1])
        self.connections.append((reader, writer))
        writer.write(encode(1, payload=b"fixture-adapter-token"))
        await writer.drain()
        self.assertEqual((await asyncio.wait_for(receive(reader), 2))[0], 101)
        return reader, writer

    async def next(self):
        return await asyncio.wait_for(receive(self.reader), 2)

    async def send(self, kind, source=0, destination=0, payload=b""):
        self.writer.write(encode(kind, source, destination, payload))
        await self.writer.drain()

    async def register(self, ids=(1001, 1002, 1003)):
        await self.send(8, payload=struct.pack("<" + "I" * len(ids), *ids))
        self.assertEqual(await self.next(), (108, 0, 0, struct.pack("<I", len(ids))))

    async def test_fresh_replacement_and_duplicate_requests_preserve_other_slots(self):
        await self.register()
        await self.engine.retire(1001)
        self.assertEqual(await self.next(), (POOL_RETIRED, 1001, 0, b""))
        await self.send(REPLACE_POOL_ID, 1001, 7, struct.pack("<I", 2001))
        self.assertEqual(await self.next(), (POOL_REPLACED, 1001, 7, struct.pack("<I", 2001)))
        await self.send(REPLACE_POOL_ID, 1001, 8, struct.pack("<I", 2001))
        self.assertEqual(await self.next(), (POOL_REPLACED, 1001, 8, struct.pack("<I", 2001)))
        await self.broker.on_pool_retired(1001)
        await self.send(7)
        self.assertEqual((await self.next())[0], 107)
        self.assertEqual(self.engine.replacements, [(1001, 2001)])
        self.assertEqual(self.engine.pool, [2001, 1002, 1003])
        self.assertEqual(self.broker.pool_ids, {2001, 1002, 1003})
        self.assertTrue({1, 1001, 1002, 1003, 2001} <= self.broker.issued_ids)

    async def test_retirement_in_initial_ack_batch_is_not_lost(self):
        self.engine.retire_at_registration = True
        await self.register()
        self.assertEqual(await self.next(), (POOL_RETIRED, 1001, 0, b""))
        self.assertTrue(self.broker.pool_ready.is_set())

    async def test_replacement_wait_does_not_block_data_info_or_other_retirements(self):
        await self.register()
        await self.send(3, 5001, 5001)
        self.assertEqual((await self.next())[:3], (103, 5001, 5001))
        await self.engine.retire(1001)
        self.assertEqual((await self.next())[:2], (POOL_RETIRED, 1001))
        self.engine.release.clear()
        self.engine.retire_at_replacement = True
        await self.send(REPLACE_POOL_ID, 1001, 7, struct.pack("<I", 2001))
        self.assertEqual(await asyncio.wait_for(self.engine.requested.get(), 2), (1001, 2001))
        await self.send(2)
        self.assertEqual((await self.next())[0], 102)
        await self.send(5, 5001, 1, b"test")
        self.assertEqual(await asyncio.wait_for(self.engine.received.get(), 2), (5001, 1, b"test"))
        self.assertEqual(await self.next(), (105, 1, 5001, b"test"))
        await self.send(4, 5001)
        self.assertEqual((await self.next())[:2], (104, 5001))
        await self.send(7)
        self.assertEqual((await self.next())[0], 107)
        await self.engine.retire(1002)
        await self.engine.retire(1003)
        self.engine.release.set()
        self.assertEqual(await self.next(), (POOL_REPLACED, 1001, 7, struct.pack("<I", 2001)))
        notices = [await self.next() for _ in range(3)]
        self.assertEqual({frame[1] for frame in notices}, {1002, 1003, 2001})
        self.assertTrue(all(frame[0] == POOL_RETIRED for frame in notices))
        self.assertEqual(self.broker.pool_retired, {1002, 1003, 2001})

    async def test_adapter_replacement_queue_is_serial_and_bounded(self):
        await self.register()
        await self.engine.retire(1001)
        await self.engine.retire(1002)
        await self.next()
        await self.next()
        self.engine.release.clear()
        await self.send(REPLACE_POOL_ID, 1001, 7, struct.pack("<I", 2001))
        self.assertEqual(await asyncio.wait_for(self.engine.requested.get(), 2), (1001, 2001))
        await self.send(REPLACE_POOL_ID, 1002, 8, struct.pack("<I", 2002))
        await self.send(7)
        self.assertEqual((await self.next())[0], 107)
        self.assertEqual(self.engine.replacements, [(1001, 2001)])
        self.assertEqual(self.broker.pool_owner.pool_request_count, 2)
        self.engine.release.set()
        self.assertEqual(await self.next(), (POOL_REPLACED, 1001, 7, struct.pack("<I", 2001)))
        self.assertEqual(await self.next(), (POOL_REPLACED, 1002, 8, struct.pack("<I", 2002)))
        self.assertEqual(self.engine.replacements, [(1001, 2001), (1002, 2002)])

        # Force the actual bounded admission branch without queuing thousands
        # of requests or touching the unrelated pool entry.
        client = self.broker.pool_owner
        with mock.patch("manager.broker.MAX_POOL_REPLACEMENTS", 0):
            with self.assertRaisesRegex(ValueError, "queue is full"):
                self.broker._queue_pool_replacement(client, 1003, 9, struct.pack("<I", 2003))
        self.assertEqual(self.engine.pool, [2001, 2002, 1003])

    async def test_only_pool_owner_can_replace(self):
        await self.register()
        await self.engine.retire(1001)
        await self.next()
        reader, writer = await self.connect_adapter()
        writer.write(encode(REPLACE_POOL_ID, 1001, 7, struct.pack("<I", 2001)))
        await writer.drain()
        self.assertEqual((await asyncio.wait_for(receive(reader), 2))[0], 199)
        self.assertFalse(self.engine.replacements)
        self.assertEqual(self.engine.pool, [1001, 1002, 1003])
        await self.send(7)
        self.assertEqual((await self.next())[0], 107)

    async def test_departed_retail_identity_cannot_become_a_surrogate(self):
        await self.register()
        await self.send(3, 5001, 5001)
        self.assertEqual((await self.next())[:3], (103, 5001, 5001))
        await self.send(4, 5001)
        self.assertEqual((await self.next())[:2], (104, 5001))
        await self.engine.retire(1001)
        await self.next()
        await self.send(REPLACE_POOL_ID, 1001, 7, struct.pack("<I", 5001))
        self.assertEqual((await self.next())[0], 199)
        self.assertFalse(self.engine.replacements)
        self.assertEqual(self.engine.pool, [1001, 1002, 1003])

    async def test_history_limit_rejects_replacement_without_reusing_old_id(self):
        await self.register()
        await self.engine.retire(1001)
        await self.next()
        with mock.patch("manager.broker.MAX_ISSUED_IDENTITIES", len(self.broker.issued_ids)):
            await self.send(REPLACE_POOL_ID, 1001, 7, struct.pack("<I", 2001))
            self.assertEqual((await self.next())[0], 199)
        self.assertFalse(self.engine.replacements)
        self.assertIn(1001, self.broker.pool_retired)
        self.assertEqual(self.engine.pool, [1001, 1002, 1003])

    async def test_native_ipc_checks_exact_ack_and_serializes_replacements(self):
        future = asyncio.get_running_loop().create_future()
        self.ipc._pool_replacements[77] = (future, 1001, 2001)
        for old, new, payload in ((1002, 2001, struct.pack("<I", 2001)),
                                  (1001, 2002, struct.pack("<I", 2002)),
                                  (1001, 2001, b"x")):
            with self.subTest(old=old, new=new), self.assertRaises(ProtocolError):
                await self.ipc._dispatch(POOL_REPLACED, old, 77, payload)
        self.assertFalse(future.done())
        await self.ipc._dispatch(POOL_REPLACED, 1001, 77, struct.pack("<I", 2001))
        await self.ipc._dispatch(POOL_REPLACED, 1001, 77, struct.pack("<I", 2001))
        self.assertEqual(future.result(), 2001)
        self.ipc._pool_replacements.pop(77)
        await self.register()
        self.engine.release.clear()
        first = asyncio.create_task(self.ipc.replace_pool_id(1001, 2001))
        second = asyncio.create_task(self.ipc.replace_pool_id(1002, 2002))
        self.assertEqual(await asyncio.wait_for(self.engine.requested.get(), 2), (1001, 2001))
        self.assertEqual(self.engine.replacements, [(1001, 2001)])
        self.engine.release.set()
        self.assertEqual(await asyncio.wait_for(first, 2), 2001)
        self.assertEqual(await asyncio.wait_for(second, 2), 2002)
        self.assertEqual(self.engine.replacements, [(1001, 2001), (1002, 2002)])

    async def test_adapter_close_cancels_pending_replacement_worker(self):
        await self.register()
        await self.engine.retire(1001)
        await self.next()
        self.engine.release.clear()
        await self.send(REPLACE_POOL_ID, 1001, 7, struct.pack("<I", 2001))
        await asyncio.wait_for(self.engine.requested.get(), 2)
        client = self.broker.pool_owner
        self.writer.close()
        await self.writer.wait_closed()
        await asyncio.wait_for(asyncio.gather(client.pool_worker, return_exceptions=True), 2)
        self.assertTrue(client.pool_worker.done())
        self.assertEqual(client.pool_request_count, 0)
        self.assertFalse(self.ipc._pool_replacements)
        self.assertEqual(self.engine.pool, [1001, 1002, 1003])
        self.assertTrue(self.ipc.connected)

    async def test_engine_disconnect_fails_pending_replacement_promptly(self):
        await self.register()
        await self.engine.retire(1001)
        await self.next()
        self.engine.release.clear()
        await self.send(REPLACE_POOL_ID, 1001, 7, struct.pack("<I", 2001))
        await asyncio.wait_for(self.engine.requested.get(), 2)
        client = self.broker.pool_owner
        for writer in tuple(self.engine.writers):
            writer.close()
        await asyncio.wait_for(asyncio.gather(client.pool_worker, return_exceptions=True), 2)
        self.assertFalse(self.ipc.connected)
        self.assertFalse(self.ipc._pool_replacements)
        self.assertEqual(client.pool_request_count, 0)
        self.assertEqual(self.engine.pool, [1001, 1002, 1003])

    async def test_native_error_completes_request_without_stalling_reader(self):
        await self.register()
        self.engine.release.clear()
        pending = asyncio.create_task(self.ipc.replace_pool_id(1001, 2001))
        await asyncio.wait_for(self.engine.requested.get(), 2)
        await self.engine.emit(encode_frame(199, REPLACE_POOL_ID, 11, b"fixture rejection"))
        with self.assertRaises(ProtocolError):
            await asyncio.wait_for(pending, 2)
        self.assertFalse(self.ipc._pool_replacements)
        self.assertEqual(await self.ipc.info(refresh=True), (0, bytes(240)))
        self.assertEqual(self.engine.pool, [1001, 1002, 1003])


if __name__ == "__main__":
    unittest.main()

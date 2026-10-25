"""Private admin IPC and routing checks using controlled local fixtures."""
import asyncio
import contextlib
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from manager.chat_admin import ChatAdminController, redact_admin_proof
from manager.authority import AuthorityStore, GameAuthority
from tools.admin_key import parse_credential, proof_for
from manager.broker import AdapterBroker, encode, receive
from manager.runtime import ServerManager, stage_tree
from web_gateway.ipc import (NativeIPC, encode_frame, read_frame, ProtocolError,
    ADMIN_REQUEST, ADMIN_CHAT, ADMIN_REPLY, ADMIN_RESET,
    ADMIN_MESSAGE, ADMIN_PLAYERS, ADMIN_KICK, ADMIN_NEXT_LEVEL)


class PolicyFixture:
    """Crypto has independent tests; this fixture checks action routing."""
    def __init__(self, store):
        self.grants, self.challenges = {}, []
    def reset(self):
        self.grants.clear()
    def begin(self, peer, generation):
        self.challenges.append((peer, generation))
        return "Controlled challenge fixture"
    def prove(self, peer, generation, key, proof):
        return "Controlled proof fixture"
    def authorized(self, peer, generation, capability=None):
        caps = self.grants.get((peer, generation), set())
        return bool(caps) and (capability is None or capability in caps)
    def logout(self, peer, generation):
        self.grants.pop((peer, generation), None)
    def status(self):
        return {"authenticated_connections": len(self.grants)}


class AdminEngineFixture:
    """Typed IPC replies, with no game process or player effects."""
    def __init__(self):
        self.writers, self.requests = set(), []
    async def handle(self, reader, writer):
        self.writers.add(writer)
        try:
            kind, source, destination, payload = await read_frame(reader)
            if kind != 1 or payload != b"controlled-admin-ipc-token":
                return
            writer.write(encode_frame(101, payload=struct.pack("<I", 1)))
            await writer.drain()
            while True:
                kind, source, destination, payload = await read_frame(reader)
                if kind == 2:
                    writer.write(encode_frame(102, payload=bytes(244)))
                elif kind == ADMIN_REQUEST:
                    generation, operation = struct.unpack_from("<II", payload)
                    self.requests.append((source, generation, operation, payload[8:].decode("ascii")))
                    writer.write(encode_frame(ADMIN_REPLY, source, destination, struct.pack("<II", generation, 0)))
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
    async def emit(self, kind, source=0, destination=0, payload=b""):
        for writer in tuple(self.writers):
            writer.write(encode_frame(kind, source, destination, payload))
            await writer.drain()
    async def close(self):
        for writer in tuple(self.writers):
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()


class AdminRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = AdminEngineFixture()
        self.server = await asyncio.start_server(self.engine.handle, "127.0.0.1", 0)
        self.ipc = NativeIPC(self.server.sockets[0].getsockname()[1], "controlled-admin-ipc-token",
                             reconnect_delay=.03, request_timeout=.5)
        self.logs = []
        with patch("manager.chat_admin.GameAuthority", PolicyFixture):
            self.controller = ChatAdminController(None, self.ipc, self.logs.append)
        await self.controller.start()
        await self.ipc.connect()
    async def asyncTearDown(self):
        await self.controller.close()
        await self.ipc.close()
        await self.engine.close()
        self.server.close()
        await self.server.wait_closed()
    async def chat(self, text, peer=501, generation=9):
        before = len(self.engine.requests)
        await self.engine.emit(ADMIN_CHAT, peer, generation, text.encode("ascii"))
        async def received():
            while len(self.engine.requests) == before:
                await asyncio.sleep(.005)
        await asyncio.wait_for(received(), 1)
        await asyncio.wait_for(self.controller._queue.join(), 1)
        return self.engine.requests[before:]

    async def test_unverified_command_denied_and_actor_bound_to_engine_event(self):
        rows = await self.chat("admin kick #2")
        self.assertEqual([row[2] for row in rows], [ADMIN_MESSAGE])
        self.assertIn("permission required", rows[0][3])
        rows = await self.chat("admin login", peer=782, generation=81)
        self.assertEqual(self.controller.authority.challenges, [(782, 81)])
        self.assertEqual(rows[0][:3], (782, 81, ADMIN_MESSAGE))

    async def test_capabilities_rechecked_without_arbitrary_console_forwarding(self):
        self.controller.authority.grants[(501, 9)] = {"player.kick"}
        self.assertEqual((await self.chat("admin next level"))[0][2], ADMIN_MESSAGE)
        rows = await self.chat("admin kick Exact Player Name")
        self.assertEqual(rows[0], (501, 9, ADMIN_KICK, "Exact Player Name"))
        self.assertEqual((await self.chat("admin players"))[0][2], ADMIN_PLAYERS)
        rows = await self.chat("admin arbitrary console text")
        self.assertEqual(rows[0][2], ADMIN_MESSAGE)
        self.assertIn("Unknown", rows[0][3])
        self.controller.authority.grants.clear()
        self.assertEqual((await self.chat("admin kick #2"))[0][2], ADMIN_MESSAGE)

    async def test_reset_discards_grants_and_queued_operations(self):
        self.controller.authority.grants[(501, 9)] = {"match.next"}
        self.controller.on_chat(501, 9, "admin next level")
        self.controller.reset()
        await asyncio.wait_for(self.controller._queue.join(), 1)
        self.assertFalse(self.engine.requests)
        self.controller.authority.grants[(501, 9)] = {"match.next"}
        await self.engine.emit(ADMIN_RESET)
        self.assertEqual((await self.chat("admin next level", generation=10))[0][2], ADMIN_MESSAGE)
        self.assertFalse(self.controller.authority.grants)

    async def test_reader_can_receive_action_replies_without_deadlock(self):
        self.assertEqual((await self.chat("admin login"))[0][2], ADMIN_MESSAGE)
        self.assertEqual(await self.ipc.info(refresh=True), (0, bytes(240)))
        self.controller.authority.grants[(501, 9)] = {"match.next"}
        self.assertEqual((await self.chat("admin next level"))[0][2], ADMIN_NEXT_LEVEL)
        self.assertEqual(self.logs, ["Verified player 501 requested next level: accepted"])

    async def test_input_is_bounded_and_proof_not_logged(self):
        for peer, gen, text in ((501, 9, "ordinary chat"), (501, 9, "admin login\nadmin kick #2"),
                                (1, 9, "admin login"), (501, 0, "admin login")):
            self.controller.on_chat(peer, gen, text)
        self.assertTrue(self.controller._queue.empty())
        for _ in range(1000):
            self.controller.on_chat(501, 9, "admin status")
        self.assertEqual(self.controller._queue.qsize(), 8)
        self.controller.reset()
        self.assertEqual((await self.chat("admin prove example example"))[0][2], ADMIN_MESSAGE)
        self.assertEqual(self.logs, [])

    async def test_ipc_rejects_bad_operation_and_mismatched_reply(self):
        for args in ((501, 0, ADMIN_KICK, "#2"), (1, 9, ADMIN_KICK, "#2"),
                     (501, 9, 88, "text"), (501, 9, ADMIN_NEXT_LEVEL, "extra"),
                     (501, 9, ADMIN_MESSAGE, "line\nbreak")):
            with self.subTest(args=args), self.assertRaises(ValueError):
                await self.ipc.admin_command(*args)
        future = asyncio.get_running_loop().create_future()
        self.ipc._admin_pending[19] = (future, 501, 9)
        with self.assertRaises(ProtocolError):
            await self.ipc._dispatch(ADMIN_REPLY, 502, 19, struct.pack("<II", 9, 0))
        self.ipc._admin_pending.pop(19)
        future.cancel()

    async def test_adapter_cannot_forward_private_admin_operations(self):
        broker = AdapterBroker(self.ipc, "fixture-broker-token", port=0)
        await broker.start()
        reader, writer = await asyncio.open_connection("127.0.0.1", broker.server.sockets[0].getsockname()[1])
        try:
            writer.write(encode(1, payload=b"fixture-broker-token"))
            await writer.drain()
            self.assertEqual((await receive(reader))[0], 101)
            writer.write(encode(ADMIN_REQUEST, 501, 1, struct.pack("<II", 9, ADMIN_NEXT_LEVEL)))
            await writer.drain()
            self.assertEqual((await asyncio.wait_for(receive(reader), 1))[0], 199)
            self.assertFalse(self.engine.requests)
        finally:
            writer.close()
            await writer.wait_closed()
            await broker.close()

    async def test_real_persistent_credential_proof_revocation_and_actor_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AuthorityStore(Path(directory) / "authority")
            issued = store.issue("Controlled integration fixture", ["player.kick"])
            credential = parse_credential(issued["credential"])
            self.controller.authority = GameAuthority(store)
            challenge = (await self.chat("admin login"))[0][3]
            proof = proof_for(credential, challenge)
            self.assertIn("authenticated", (await self.chat(proof))[0][3])
            # A copied chat proof cannot grant a different live connection.
            self.assertIn("failed", (await self.chat(proof, peer=502))[0][3])
            self.assertEqual((await self.chat("admin kick #3"))[0][2], ADMIN_KICK)
            reopened = AuthorityStore(Path(directory) / "authority")
            reopened.revoke(issued["metadata"]["id"])
            self.assertEqual((await self.chat("admin kick #3"))[0][2], ADMIN_MESSAGE)
            self.assertNotIn(credential["secret"], repr(self.logs))
            self.assertNotIn(proof, repr(self.logs))


class AdminIsolationTests(unittest.TestCase):
    def test_log_redaction_and_game_staging(self):
        self.assertEqual(redact_admin_proof("Peer: ADMIN prove example proof"), "Peer: admin prove [redacted]")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "jk-admin-key-fixture.cog").write_text("private fixture")
            (source / "authority").mkdir()
            (source / "authority/keys.sqlite3").write_text("private fixture")
            (source / "public.txt").write_text("game fixture")
            stage_tree(source, root / "staged")
            self.assertEqual([p.name for p in (root / "staged").iterdir()], ["public.txt"])

    def test_startup_does_not_create_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manager = ServerManager(root / "config.json", root / "runtime")
            self.assertFalse((root / "runtime/authority").exists())
            self.assertEqual(manager.authority_store.metadata()["credentials"], [])
            manager.status()
            manager.log("Player: admin prove example-key short-lived-proof")
            self.assertEqual(manager.logs[-1]["text"], "Player: admin prove [redacted]")
            self.assertFalse((root / "runtime/authority").exists())


if __name__ == "__main__":
    unittest.main()

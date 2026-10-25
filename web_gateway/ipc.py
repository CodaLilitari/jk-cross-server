"""Authenticated loopback IPC to the server-only OpenJKDF2 gateway patch.

Wire: u32le body length, then u32le type/source/destination and payload.
This module never opens a public listener and never changes game packets.
"""
from __future__ import annotations

import asyncio
import contextlib
import inspect
import ipaddress
import logging
import struct
from collections.abc import Callable

LOG = logging.getLogger(__name__)
MAX_FRAME = 65536
MAX_SITH_PAYLOAD = 2052
HELLO, INFO, ADD_PEER, REMOVE_PEER, DATA, PING, SET_ID_POOL = 1, 2, 3, 4, 5, 7, 8
HELLO_REPLY, INFO_REPLY, ADDED, REMOVED, DATA_REPLY, PONG, ID_POOL_REPLY, ERROR = 101, 102, 103, 104, 105, 107, 108, 199
ADMIN_REQUEST, ADMIN_CHAT, ADMIN_REPLY, ADMIN_RESET = 9, 109, 110, 111
ADMIN_MESSAGE, ADMIN_PLAYERS, ADMIN_KICK, ADMIN_NEXT_LEVEL = 1, 2, 3, 4
MAX_ADMIN_TEXT = 127


class EngineUnavailable(ConnectionError):
    """The dedicated engine is not connected and authenticated."""


class ProtocolError(ConnectionError):
    """The loopback peer rejected a request or violated the IPC contract."""


def encode_frame(kind: int, source: int = 0, destination: int = 0, payload: bytes = b"") -> bytes:
    body = struct.pack("<III", kind, source, destination) + payload
    if not 12 <= len(body) <= MAX_FRAME:
        raise ValueError("IPC frame length outside 12..65536")
    return struct.pack("<I", len(body)) + body


async def read_frame(reader: asyncio.StreamReader) -> tuple[int, int, int, bytes]:
    length = struct.unpack("<I", await reader.readexactly(4))[0]
    if not 12 <= length <= MAX_FRAME:
        raise ProtocolError("IPC frame length outside 12..65536")
    body = await reader.readexactly(length)
    kind, source, destination = struct.unpack_from("<III", body)
    return kind, source, destination, body[12:]


class NativeIPC:
    """One engine connection shared by all server-side transport adapters.

    Call start(), then wait_ready(). The reconnect loop clears obsolete peers
    when an engine connection is lost; adapters must close their own sessions
    on a False state callback. Subscribers may be sync or async functions and
    must not await another IPC request inside a reader callback. Admin chat
    callbacks receive engine-verified transport identity and incarnation, not
    a player name or the sender claimed inside a game chat packet.
    """

    def __init__(self, port: int, token: str, host: str = "127.0.0.1", *,
                 request_timeout: float = 5.0, reconnect_delay: float = 1.0):
        if host == "localhost":
            host = "127.0.0.1"
        if not ipaddress.ip_address(host).is_loopback:
            raise ValueError("The native IPC endpoint must be loopback")
        if not 1 <= port <= 65535:
            raise ValueError("Invalid native IPC port")
        if len(token.encode("utf-8")) < 16:
            raise ValueError("Native IPC token must contain at least 16 UTF-8 bytes")
        self.host, self.port, self._token = host, port, token
        self.request_timeout = request_timeout
        self.reconnect_delay = reconnect_delay
        self._writer: asyncio.StreamWriter | None = None
        self._task: asyncio.Task | None = None
        self._closed = False
        self._ready = asyncio.Event()
        self._write_lock = asyncio.Lock()
        self._session: tuple[int, bytes] | None = None
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._admin_pending: dict[int, tuple[asyncio.Future, int, int]] = {}
        self._info_waiters: list[asyncio.Future] = []
        self._pool_future: asyncio.Future | None = None
        self._pool_lock = asyncio.Lock()
        self._data_callbacks: list[Callable] = []
        self._state_callbacks: list[Callable] = []
        self._info_callbacks: list[Callable] = []
        self._admin_callbacks: list[Callable] = []
        self._admin_reset_callbacks: list[Callable] = []
        self._removed_callbacks: list[Callable] = []
        self.last_error: str | None = None

    @property
    def connected(self) -> bool:
        return self._ready.is_set()

    @property
    def session(self) -> tuple[int, bytes] | None:
        return self._session

    def subscribe_data(self, callback: Callable) -> Callable:
        self._data_callbacks.append(callback)
        return lambda: self._data_callbacks.remove(callback) if callback in self._data_callbacks else None

    def subscribe_state(self, callback: Callable) -> Callable:
        self._state_callbacks.append(callback)
        return lambda: self._state_callbacks.remove(callback) if callback in self._state_callbacks else None

    def subscribe_info(self, callback: Callable) -> Callable:
        self._info_callbacks.append(callback)
        return lambda: self._info_callbacks.remove(callback) if callback in self._info_callbacks else None

    def subscribe_admin(self, callback: Callable) -> Callable:
        self._admin_callbacks.append(callback)
        return lambda: self._admin_callbacks.remove(callback) if callback in self._admin_callbacks else None

    def subscribe_admin_reset(self, callback: Callable) -> Callable:
        self._admin_reset_callbacks.append(callback)
        return lambda: self._admin_reset_callbacks.remove(callback) if callback in self._admin_reset_callbacks else None

    def subscribe_removed(self, callback: Callable) -> Callable:
        self._removed_callbacks.append(callback)
        return lambda: self._removed_callbacks.remove(callback) if callback in self._removed_callbacks else None

    def _next_request(self) -> int:
        self._request_id = (self._request_id % 0xFFFFFFFF) + 1
        while self._request_id in self._pending or self._request_id in self._admin_pending:
            self._request_id = (self._request_id % 0xFFFFFFFF) + 1
        return self._request_id

    async def _notify(self, subscribers: list[Callable], *args) -> None:
        for callback in tuple(subscribers):
            try:
                value = callback(*args)
                if inspect.isawaitable(value):
                    await value
            except asyncio.CancelledError:
                raise
            except Exception:
                LOG.exception("Transport subscriber failed")

    async def start(self) -> None:
        if self._closed:
            raise RuntimeError("Cannot restart a closed NativeIPC object")
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="native-engine-ipc")

    async def connect(self, timeout: float = 10.0) -> None:
        await self.start()
        await self.wait_ready(timeout)

    async def wait_ready(self, timeout: float = 10.0) -> None:
        try:
            await asyncio.wait_for(self._ready.wait(), timeout)
        except TimeoutError as exc:
            raise EngineUnavailable("Dedicated engine IPC did not become ready") from exc

    async def _write(self, kind: int, source: int = 0, destination: int = 0,
                     payload: bytes = b"", *, require_ready: bool = True) -> None:
        async with self._write_lock:
            if not self._writer or (require_ready and not self.connected):
                raise EngineUnavailable("Dedicated engine is disconnected")
            self._writer.write(encode_frame(kind, source, destination, payload))
            await asyncio.wait_for(self._writer.drain(), self.request_timeout)

    async def info(self, *, refresh: bool = False) -> tuple[int, bytes]:
        if not self.connected:
            raise EngineUnavailable("Dedicated engine is disconnected")
        if self._session is not None and not refresh:
            return self._session
        future = asyncio.get_running_loop().create_future()
        self._info_waiters.append(future)
        try:
            await self._write(INFO)
            return await asyncio.wait_for(future, self.request_timeout)
        finally:
            if future in self._info_waiters:
                self._info_waiters.remove(future)

    async def add_peer(self, requested_id: int = 0) -> int:
        if requested_id != 0 and not 2 <= requested_id <= 0xFFFFFFFF:
            raise ValueError("External player IDs must be 2..4294967295, or zero for allocation")
        request_id = self._next_request()
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            await self._write(ADD_PEER, requested_id, request_id)
            return await asyncio.wait_for(future, self.request_timeout)
        finally:
            self._pending.pop(request_id, None)

    async def remove_peer(self, peer_id: int) -> None:
        if self.connected:
            await self._write(REMOVE_PEER, peer_id)

    async def send(self, source: int, destination: int, payload: bytes) -> None:
        if not 2 <= source <= 0xFFFFFFFF or not 0 <= destination <= 0xFFFFFFFF:
            raise ValueError("Invalid external player ID")
        if not 4 <= len(payload) <= MAX_SITH_PAYLOAD:
            raise ValueError("Sith payload length outside 4..2052")
        await self._write(DATA, source, destination, bytes(payload))

    async def ping(self) -> None:
        await self._write(PING)

    async def admin_command(self, peer_id: int, generation: int, operation: int,
                            argument: str = "") -> tuple[int, str]:
        """Send one typed, manager-authorized operation over private IPC.

        This method is deliberately absent from the public transport broker.
        The engine rechecks the actor's current transport incarnation before
        executing it, including private replies. There is no console command.
        """
        if (type(peer_id) is not int or not 2 <= peer_id <= 0xFFFFFFFF or
                type(generation) is not int or not 1 <= generation <= 0xFFFFFFFF):
            raise ValueError("Invalid admin actor incarnation")
        if type(operation) is not int or operation not in (ADMIN_MESSAGE, ADMIN_PLAYERS, ADMIN_KICK, ADMIN_NEXT_LEVEL):
            raise ValueError("Unknown admin operation")
        if (not isinstance(argument, str) or len(argument) > MAX_ADMIN_TEXT or
                any(not 32 <= ord(ch) <= 126 for ch in argument)):
            raise ValueError("Admin argument must be at most 127 printable ASCII characters")
        if operation in (ADMIN_PLAYERS, ADMIN_NEXT_LEVEL) and argument:
            raise ValueError("This admin operation does not accept an argument")
        if operation in (ADMIN_MESSAGE, ADMIN_KICK) and not argument:
            raise ValueError("This admin operation requires an argument")
        if len(self._admin_pending) >= 64:
            raise EngineUnavailable("Admin request queue is full")
        request_id = self._next_request()
        future = asyncio.get_running_loop().create_future()
        self._admin_pending[request_id] = (future, peer_id, generation)
        try:
            await self._write(ADMIN_REQUEST, peer_id, request_id,
                              struct.pack("<II", generation, operation) + argument.encode("ascii"))
            return await asyncio.wait_for(future, self.request_timeout)
        finally:
            self._admin_pending.pop(request_id, None)

    async def set_id_pool(self, ids: list[int]) -> int:
        """Install real DirectPlay surrogate IDs before allocating clients."""
        if not ids or len(ids) > 64 or len(set(ids)) != len(ids) or any(not 2 <= i <= 0xFFFFFFFF for i in ids):
            raise ValueError("Expected 1..64 unique unsigned player IDs greater than one")
        async with self._pool_lock:
            self._pool_future = asyncio.get_running_loop().create_future()
            try:
                await self._write(SET_ID_POOL, payload=struct.pack("<" + "I" * len(ids), *ids))
                return await asyncio.wait_for(self._pool_future, self.request_timeout)
            finally:
                self._pool_future = None

    async def _dispatch(self, kind: int, source: int, destination: int, payload: bytes) -> None:
        if kind == INFO_REPLY:
            if len(payload) != 244:
                raise ProtocolError("Engine descriptor is not mode32 + jkMultiEntry240")
            mode = struct.unpack_from("<I", payload)[0]
            if mode not in (0, 1):
                raise ProtocolError("Unknown engine game mode")
            self._session = (mode, payload[4:])
            for future in tuple(self._info_waiters):
                if not future.done():
                    future.set_result(self._session)
            await self._notify(self._info_callbacks, *self._session)
        elif kind == ADDED:
            future = self._pending.get(destination)
            if future and not future.done():
                if len(payload) != 4 or struct.unpack("<I", payload)[0] != 0 or source < 2:
                    future.set_exception(ProtocolError("Native peer allocation failed"))
                else:
                    future.set_result(source)
            elif source > 1 and len(payload) == 4 and struct.unpack("<I", payload)[0] == 0:
                # A timed-out allocator must not leave an invisible seat.
                await self._write(REMOVE_PEER, source)
        elif kind == ID_POOL_REPLY:
            if self._pool_future and not self._pool_future.done():
                if len(payload) == 4:
                    self._pool_future.set_result(struct.unpack("<I", payload)[0])
                else:
                    self._pool_future.set_exception(ProtocolError("Invalid ID pool reply"))
        elif kind == DATA_REPLY:
            if not 4 <= len(payload) <= MAX_SITH_PAYLOAD:
                raise ProtocolError("Engine emitted an invalid Sith payload length")
            await self._notify(self._data_callbacks, source, destination, payload)
        elif kind == ADMIN_CHAT:
            if (source < 2 or destination == 0 or not 1 <= len(payload) <= MAX_ADMIN_TEXT or
                    any(not 32 <= byte <= 126 for byte in payload)):
                raise ProtocolError("Invalid verified admin chat event")
            await self._notify(self._admin_callbacks, source, destination, payload.decode("ascii"))
        elif kind == ADMIN_RESET:
            if source or destination or payload:
                raise ProtocolError("Invalid admin reset event")
            await self._notify(self._admin_reset_callbacks)
            for future, _, _ in tuple(self._admin_pending.values()):
                if not future.done():
                    future.set_exception(EngineUnavailable("Admin connection context changed"))
        elif kind == ADMIN_REPLY:
            if (not 8 <= len(payload) <= MAX_ADMIN_TEXT + 8 or
                    any(not 32 <= byte <= 126 for byte in payload[8:])):
                raise ProtocolError("Invalid admin command reply")
            generation, status = struct.unpack_from("<II", payload)
            pending = self._admin_pending.get(destination)
            if pending:
                future, expected_peer, expected_generation = pending
                if source != expected_peer or generation != expected_generation:
                    raise ProtocolError("Admin reply actor incarnation does not match its request")
                if not future.done():
                    future.set_result((status, payload[8:].decode("ascii")))
        elif kind == ERROR:
            reason = payload.decode("utf-8", "replace")[:256]
            error = ProtocolError(f"Engine request {source} rejected ({destination}): {reason}")
            if source == ADD_PEER:
                for future in self._pending.values():
                    if not future.done():
                        future.set_exception(error)
            elif source == SET_ID_POOL and self._pool_future and not self._pool_future.done():
                self._pool_future.set_exception(error)
            elif source == ADMIN_REQUEST:
                # Protocol-level errors contain no command/proof text. Normal
                # actor/action denials use a correlated ADMIN_REPLY instead.
                for future, _, _ in self._admin_pending.values():
                    if not future.done():
                        future.set_exception(ProtocolError("Engine rejected an admin request"))
            else:
                LOG.warning("%s", error)
        elif kind == REMOVED:
            if source < 2 or destination or payload:
                raise ProtocolError("Invalid engine peer removal")
            await self._notify(self._removed_callbacks, source)
        elif kind not in (HELLO_REPLY, PONG):
            raise ProtocolError(f"Unknown engine IPC response {kind}")

    async def _run(self) -> None:
        while not self._closed:
            try:
                reader, writer = await asyncio.open_connection(self.host, self.port, limit=MAX_FRAME + 4)
                self._writer = writer
                await self._write(HELLO, payload=self._token.encode("utf-8"), require_ready=False)
                reply = await asyncio.wait_for(read_frame(reader), self.request_timeout)
                if reply[0] != HELLO_REPLY or reply[3] != struct.pack("<I", 1):
                    raise ProtocolError("Engine IPC authentication/version negotiation failed")
                await self._write(INFO, require_ready=False)
                while self._session is None:
                    reply = await asyncio.wait_for(read_frame(reader), self.request_timeout)
                    await self._dispatch(*reply)
                self._ready.set()
                self.last_error = None
                await self._notify(self._state_callbacks, True)
                while not self._closed:
                    await self._dispatch(*await read_frame(reader))
            except asyncio.CancelledError:
                break
            except Exception as exc:
                # Authentication secrets are never included in errors or logs.
                self.last_error = f"{type(exc).__name__}: {exc}"
                LOG.info("Engine IPC unavailable: %s", type(exc).__name__)
            finally:
                was_ready = self._ready.is_set()
                self._ready.clear()
                self._session = None
                for future in tuple(self._pending.values()) + tuple(self._info_waiters):
                    if not future.done():
                        future.set_exception(EngineUnavailable("Engine IPC connection ended"))
                for future, _, _ in tuple(self._admin_pending.values()):
                    if not future.done():
                        future.set_exception(EngineUnavailable("Engine IPC connection ended"))
                if self._pool_future and not self._pool_future.done():
                    self._pool_future.set_exception(EngineUnavailable("Engine IPC connection ended"))
                writer, self._writer = self._writer, None
                if writer:
                    writer.close()
                    with contextlib.suppress(Exception):
                        await writer.wait_closed()
                if was_ready:
                    await self._notify(self._state_callbacks, False)
            if not self._closed:
                await asyncio.sleep(self.reconnect_delay)

    async def close(self) -> None:
        self._closed = True
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

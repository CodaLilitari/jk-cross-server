"""Connection-bound administration through verified engine chat events."""
from __future__ import annotations

import asyncio
from collections import deque
import contextlib
import re
import time

from .authority import GameAuthority
from web_gateway.ipc import (
    ADMIN_MESSAGE, ADMIN_PLAYERS, ADMIN_KICK, ADMIN_NEXT_LEVEL,
    EngineUnavailable, MAX_ADMIN_TEXT,
)

_PROOF_LOG = re.compile(r"\badmin\s+prove\b[^\r\n]*", re.IGNORECASE)


def redact_admin_proof(value: object) -> str:
    """Do not retain even short-lived proof values in general session logs."""
    return _PROOF_LOG.sub("admin prove [redacted]", str(value))


class ChatAdminController:
    def __init__(self, store, ipc, log=lambda message: None):
        self.ipc = ipc
        self.authority = GameAuthority(store)
        self.log = log
        self._queue = asyncio.Queue(maxsize=64)
        self._worker = None
        self._epoch = 0
        self._closed = False
        self._recent = {}
        self._subscriptions = [ipc.subscribe_admin(self.on_chat),
                               ipc.subscribe_admin_reset(self.reset),
                               ipc.subscribe_state(self.on_state)]

    async def start(self):
        if self._closed:
            raise RuntimeError("Cannot restart a closed chat administrator")
        if self._worker is None:
            self._worker = asyncio.create_task(self._run(), name="game-chat-admin")

    def reset(self):
        self._epoch += 1
        self.authority.reset()
        self._recent.clear()
        while not self._queue.empty():
            with contextlib.suppress(asyncio.QueueEmpty):
                self._queue.get_nowait()
                self._queue.task_done()

    def on_state(self, connected):
        # A reconnect never resurrects a previous connection's grant.
        self.reset()

    def on_chat(self, peer_id, generation, text):
        """Reader callback: queue work without awaiting another IPC request."""
        if self._closed or not self.ipc.connected:
            return
        if (type(peer_id) is not int or not 2 <= peer_id <= 0xFFFFFFFF or
                type(generation) is not int or not 1 <= generation <= 0xFFFFFFFF or
                not isinstance(text, str) or not 1 <= len(text) <= MAX_ADMIN_TEXT or
                any(not 32 <= ord(character) <= 126 for character in text)):
            return
        words = text.split()
        if not words or words[0].casefold() != "admin":
            return
        identity, now = (peer_id, generation), time.monotonic()
        for key, recent in tuple(self._recent.items()):
            if not recent or now - recent[-1] > 10:
                self._recent.pop(key, None)
        if identity not in self._recent and len(self._recent) >= 64:
            return
        recent = self._recent.setdefault(identity, deque())
        while recent and now - recent[0] >= 2:
            recent.popleft()
        if len(recent) >= 8:
            return
        recent.append(now)
        with contextlib.suppress(asyncio.QueueFull):
            self._queue.put_nowait((self._epoch, peer_id, generation, text))

    def status(self):
        return {"connected": bool(self.ipc.connected and not self._closed),
                "queued_commands": self._queue.qsize(), "authority": self.authority.status()}

    async def _reply(self, epoch, peer_id, generation, message):
        if epoch != self._epoch or self._closed or not self.ipc.connected:
            return
        safe = str(message)
        if not safe or len(safe) > MAX_ADMIN_TEXT or any(not 32 <= ord(ch) <= 126 for ch in safe):
            safe = "Admin request failed. Ask the server operator to check the control panel."
        await self.ipc.admin_command(peer_id, generation, ADMIN_MESSAGE, safe)

    async def _handle(self, epoch, peer_id, generation, text):
        if epoch != self._epoch or not self.ipc.connected:
            return
        words = text.split()
        lower = [word.casefold() for word in words]
        reply = lambda message: self._reply(epoch, peer_id, generation, message)
        if lower in (["admin"], ["admin", "help"]):
            await reply("Admin: login, prove, status, players, next level, kick #slot (or exact name), logout.")
            return
        if lower == ["admin", "login"]:
            await reply(self.authority.begin(peer_id, generation))
            return
        if len(words) >= 2 and lower[1] == "prove":
            if len(words) != 4:
                await reply("Admin verification failed. Type admin login for a new challenge.")
            else:
                await reply(self.authority.prove(peer_id, generation, words[2], words[3]))
            return
        if lower == ["admin", "logout"]:
            self.authority.logout(peer_id, generation)
            await reply("Admin authority cleared for this connection.")
            return
        if lower == ["admin", "status"]:
            active = self.authority.authorized(peer_id, generation)
            await reply("Admin verified for this connection." if active else
                        "Admin permission required. Type admin login.")
            return
        operation, capability, argument = None, None, ""
        if lower == ["admin", "players"]:
            operation = ADMIN_PLAYERS
        elif lower == ["admin", "next", "level"]:
            operation, capability = ADMIN_NEXT_LEVEL, "match.next"
        elif len(words) >= 3 and lower[1] == "kick":
            operation, capability = ADMIN_KICK, "player.kick"
            argument = text.strip().split(None, 2)[2].strip()
        if operation is None:
            await reply("Unknown admin command. Type admin help.")
            return
        if not self.authority.authorized(peer_id, generation, capability):
            await reply("Admin permission required for this command. Type admin login.")
            return
        status, message = await self.ipc.admin_command(peer_id, generation, operation, argument)
        if operation in (ADMIN_KICK, ADMIN_NEXT_LEVEL):
            name = "kick" if operation == ADMIN_KICK else "next level"
            self.log(f"Verified player {peer_id} requested {name}: " + ("accepted" if status == 0 else "denied"))
        if message:
            await reply(message)

    async def _run(self):
        while True:
            item = await self._queue.get()
            try:
                await self._handle(*item)
            except asyncio.CancelledError:
                raise
            except (EngineUnavailable, ConnectionError, TimeoutError):
                pass
            except Exception:
                self.authority.reset()
                self.log("Game administrator request failed; authority was cleared. Check the credential store.")
                with contextlib.suppress(ConnectionError, RuntimeError, TimeoutError):
                    await self._reply(*item[:3], "Admin verification is unavailable. Ask the server operator to check the control panel.")
            finally:
                self._queue.task_done()

    async def close(self):
        self._closed = True
        self.reset()
        for unsubscribe in self._subscriptions:
            unsubscribe()
        self._subscriptions.clear()
        if self._worker is not None:
            self._worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker
            self._worker = None

"""Scoped local companion service. Only pump() exchanges native datagrams."""
from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
import hmac
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import secrets
import socket
import struct
import subprocess
from socketserver import ThreadingMixIn
import threading
import time
from urllib.parse import urlsplit

from . import tactics

HEADER = struct.Struct("<4sBBHIII")
STATE, ACK, CHAT, SOUND = 1, 2, 3, 4
STRATEGY, SAY, RELEASE = 16, 17, 18
TACTICS = 21  # 19 and 20 belong to the adaptive-player branch
STRATEGY_PAYLOAD = struct.Struct("<dBBHffII")
KINDS = {"strategy": STRATEGY, "say": SAY, "release": RELEASE, "tactics": TACTICS}
MODES = ("autonomous", "pressure", "resource", "recover")
RESOURCES = (0, 11, 12, 14, 15, 40, 60, 62, 63, 64, 65, 66)
ACK_STATUS = ("applied", "rejected", "expired", "stale", "rate_limited")
MAX_PENDING, EVENT_HISTORY, COMMAND_HISTORY, TACTIC_HISTORY = 16, 128, 256, 32
UINT_MAX = 0xffffffff
IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
FENCE = {"run_id", "world_epoch", "life_epoch"}


def create_private_directory(directory, *, parents=False):
    """Create a fresh directory whose credential and lease files inherit privacy."""
    directory.mkdir(mode=0o700, parents=parents, exist_ok=False)
    if os.name != "nt":
        return
    # Windows mkdir(0700) can install explicit administrator and system ACEs.
    # Replace the DACL on this newly created, empty directory before any secret
    # is written. Use the token's user SID even when the owner is a group.
    script = (
        "$ErrorActionPreference='Stop'; "
        "$path=$env:JK_COMPANION_PRIVATE_DIR; "
        "$user=[System.Security.Principal.WindowsIdentity]::GetCurrent().User; "
        "$acl=[System.Security.AccessControl.DirectorySecurity]::new(); "
        "$acl.SetSecurityDescriptorSddlForm(('D:P(A;OICI;FA;;;'+$user.Value+')'), "
        "[System.Security.AccessControl.AccessControlSections]::Access); "
        "[System.IO.Directory]::SetAccessControl($path,$acl); "
        "$actual=Get-Acl -LiteralPath $path; "
        "$rules=@($actual.GetAccessRules($true,$true,[System.Security.Principal.SecurityIdentifier])); "
        "if (!$actual.AreAccessRulesProtected -or $rules.Count -ne 1 -or "
        "$rules[0].IdentityReference.Value -ne $user.Value -or "
        "$rules[0].AccessControlType -ne 'Allow' -or $rules[0].FileSystemRights -ne 'FullControl' -or "
        "[int]$rules[0].InheritanceFlags -ne 3 -or [int]$rules[0].PropagationFlags -ne 0) "
        "{ throw 'Could not establish private directory permissions.' }"
    )
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                   env={**os.environ, "JK_COMPANION_PRIVATE_DIR": str(directory.resolve())},
                   check=True, capture_output=True)


def frame(kind, world, life, seq, payload):
    return HEADER.pack(b"JKCP", 1, kind, len(payload), world, life, seq) + payload


def plain_text(text):
    return (type(text) is str and 1 <= len(text) <= 110 and text.isascii()
            and all(32 <= ord(c) <= 126 for c in text) and bool(text.strip())
            and text.lstrip().lower().split(" ", 1)[0] != "admin")


class Problem(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def need(condition, message, status=400):
    if not condition:
        raise Problem(status, message)


def fields(body, required, optional=()):
    need(type(body) is dict and required <= body.keys() <= required | set(optional),
         "Missing or unknown request fields.")


def integer(value, low, high):
    need(type(value) is int and low <= value <= high, "Integer out of range.")
    return value


def number(value, low, high):
    need(type(value) in (int, float) and low <= value <= high, "Number out of range.")
    return float(value)


def decode_state(data):
    if len(data) != 144:
        return None
    slot, net, guid, signature = struct.unpack_from("<4I", data)
    game_time, x, y, z, health, shields, mana = struct.unpack_from("<7f", data, 16)
    weapon, kills, deaths, mode, goal, flags = struct.unpack_from("<4IiI", data, 44)
    target_slot, target_net, target_guid, target_sig = struct.unpack_from("<4I", data, 68)
    tx, ty, tz, target_age = struct.unpack_from("<4f", data, 84)
    category = struct.unpack_from("<I", data, 100)[0]
    hx, hy, hz, age, strength, *ammo = struct.unpack_from("<9f", data, 104)
    mask = struct.unpack_from("<I", data, 140)[0]
    if (slot >= 32 or not net or mode >= len(MODES) or flags & ~63 or not flags & 4 or
            not all(math.isfinite(v) for v in (game_time, x, y, z, health, shields, mana, tx,
                                                ty, tz, target_age, hx, hy, hz, age, strength, *ammo))):
        return None
    target = hearing = None
    if flags & 8:
        if flags & (1 | 2) or target_slot >= 32 or target_net == 0 or target_age < 0:
            return None
        target = {"slot": target_slot, "net_id": target_net, "guid": target_guid,
                  "signature": target_sig, "position": [tx, ty, tz], "age": target_age}
    elif (target_slot, target_net, target_guid, target_sig, tx, ty, tz, target_age) != (UINT_MAX, 0, 0, 0, 0, 0, 0, 0):
        return None
    if flags & 16:
        if not 1 <= category <= 4 or age < 0 or not 0 <= strength <= 1:
            return None
        hearing = {"category": category, "position": [hx, hy, hz], "age": age, "strength": strength}
    elif any((category, hx, hy, hz, age, strength)):
        return None
    return {"slot": slot, "net_id": net, "guid": guid, "signature": signature,
            "game_time": game_time, "position": [x, y, z], "health": health, "shields": shields,
            "mana": mana, "weapon": weapon, "kills": kills, "deaths": deaths, "mode": MODES[mode],
            "goal": goal, "flags": flags, "target": target, "hearing": hearing,
            "ammo": dict(zip(("energy", "power", "explosives", "rail"), ammo)), "force_mask": mask}


@dataclass
class Command:
    name: str
    fingerprint: str
    lease: str
    seq: int
    world: int
    life: int
    packet: bytes
    deadline: float
    status: str = "pending"
    reason: int | None = None
    sent: bool = False
    detail: dict | None = None

    def result(self, key):
        return {"request_id": key, "kind": self.name, "status": self.status, "reason": self.reason,
                "world_epoch": self.world, "life_epoch": self.life}


@dataclass
class Bot:
    ident: str
    sock: socket.socket
    child: socket.socket | None
    token: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    world: int = 0
    life: int = 0
    state: dict | None = None
    observed: float = 0.
    sequence: int = 0
    event_seq: int = 0
    wire_dropped: int = 0
    cursor: int = 0
    events: deque = field(default_factory=lambda: deque(maxlen=EVENT_HISTORY))
    commands: OrderedDict = field(default_factory=OrderedDict)
    pending: dict = field(default_factory=dict)
    lease: str | None = None
    lease_until: float = 0.
    last_chat: float = -math.inf
    release: tuple | None = None
    # Tactic adjustments the engine acknowledged as applied, oldest first.
    # The engine's table also depends on its baseline file, so this is the
    # hub's record of what it sent, not a readback of the engine.
    tactic_log: deque = field(default_factory=lambda: deque(maxlen=TACTIC_HISTORY))

    def next_seq(self):
        self.sequence = self.sequence % UINT_MAX + 1
        return self.sequence

    def cancel(self):
        for command in self.pending.values():
            command.status = "unconfirmed" if command.sent else "cancelled"
        self.pending.clear()

    def expire_lease(self, now):
        self.cancel()
        self.lease = None
        if self.world:
            self.release = (now + 2, frame(RELEASE, self.world, self.life, self.next_seq(), struct.pack("<d", now + 2)))

    def accept(self, raw, now):
        if not HEADER.size <= len(raw) <= 512:
            return
        magic, version, kind, length, world, life, seq = HEADER.unpack_from(raw)
        if magic != b"JKCP" or version != 1 or not seq or length != len(raw) - HEADER.size:
            return
        data = raw[HEADER.size:]
        if kind == ACK and len(data) == 4:
            status, original, reason = struct.unpack("<BBH", data)
            cmd = self.pending.get(seq)
            if (cmd and cmd.sent and (cmd.world, cmd.life, KINDS[cmd.name]) == (world, life, original)
                    and status < len(ACK_STATUS) and (status == 0) == (reason == 0)):
                cmd.status, cmd.reason = ACK_STATUS[status], reason
                del self.pending[seq]
                if cmd.name == "tactics" and status == 0:
                    self.tactic_log.append(dict(cmd.detail, world_epoch=world, life_epoch=life, at=now))
            return
        if not world or not life:
            return
        if self.event_seq:
            delta = (seq - self.event_seq) & UINT_MAX
            if delta == 0 or delta > UINT_MAX // 2:
                return
        event = None
        if kind == STATE:
            state = decode_state(data)
            if state is None:
                return
            if (world, life) != (self.world, self.life):
                self.cancel()
                self.lease = self.release = None
                self.world, self.life = world, life
            self.state, self.observed = state, now
        elif (world, life) != (self.world, self.life):
            return
        elif kind == CHAT and 9 <= length <= 118:
            slot, net = struct.unpack_from("<iI", data)
            text = data[8:].decode("ascii", "replace")
            if not 0 <= slot < 32 or not net or not plain_text(text):
                return
            event = {"kind": "chat", "slot": slot, "net_id": net, "text": text}
        elif kind == SOUND and length == 24:
            category, x, y, z, strength, uncertainty = struct.unpack("<I5f", data)
            if (not 1 <= category <= 4 or not all(map(math.isfinite, (x,y,z,strength,uncertainty)))
                    or not 0 <= strength <= 1 or uncertainty < 0):
                return
            event = {"kind": "sound", "category": category, "position": [x,y,z],
                     "strength": strength, "uncertainty": uncertainty}
        else:
            return
        if self.event_seq:
            self.wire_dropped += ((seq - self.event_seq) & UINT_MAX) - 1 - (seq < self.event_seq)
        self.event_seq = seq
        if event:
            self.cursor += 1
            self.events.append(dict(event, cursor=self.cursor, world_epoch=world, life_epoch=life))

    def pump(self, now):
        for _ in range(32):
            try:
                self.accept(self.sock.recv(513), now)
            except OSError:
                break
        if self.lease and now >= self.lease_until:
            self.expire_lease(now)
        if self.release:
            deadline, packet = self.release
            if deadline > now:
                try:
                    self.sock.send(packet)
                except OSError:
                    return
            self.release = None
        for seq, cmd in list(self.pending.items()):
            if now >= cmd.deadline:
                cmd.status = "unconfirmed" if cmd.sent else "expired"
                del self.pending[seq]
            elif not cmd.sent:
                try:
                    self.sock.send(cmd.packet)
                except OSError:
                    break
                cmd.sent = True


class LocalServer(ThreadingMixIn, HTTPServer):
    """Cap simultaneous readers and interrupt every outstanding read on stop."""
    def __init__(self, address, handler):
        self.slots = threading.BoundedSemaphore(8)
        self.active_lock = threading.Lock()
        self.active = set()
        super().__init__(address, handler)

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        with self.active_lock:
            self.active.add(request)
        try:
            super().process_request(request, address)
        except BaseException:
            self.forget(request)
            raise

    def forget(self, request):
        with self.active_lock:
            self.active.discard(request)
        self.slots.release()

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.forget(request)

    def interrupt_readers(self):
        with self.active_lock:
            for request in self.active:
                try:
                    request.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass


class BrowserChannel:
    """Trusted browser-host adapter endpoint. No listening socket or web credential."""
    def __init__(self, endpoint):
        self.endpoint = endpoint

    def enqueue_native_frame(self, data):
        """Return False on oversize/backpressure; never hold up a game frame."""
        if not isinstance(data, bytes) or not HEADER.size <= len(data) <= 512:
            return False
        try:
            return self.endpoint.send(data) == len(data)
        except OSError:
            return False

    def outgoing_frames(self):
        records = []
        for _ in range(MAX_PENDING + 1):
            try:
                records.append(self.endpoint.recv(513))
            except OSError:
                break
        return records

    def close(self):
        self.endpoint.close()


class Hub:
    def __init__(self, run_directory, ids, port, *, allow_chat=False, clock=time.monotonic, channel_factory=None):
        self.clock, self.allow_chat = clock, allow_chat
        self.run_id = secrets.token_hex(16)
        self.directory = Path(run_directory) / "companion"
        create_private_directory(self.directory)
        self.lock = threading.RLock()
        self.bots = {}
        self.server = self.thread = None
        try:
            if type(port) is not int or not 0 <= port <= 65535:
                raise ValueError("Companion port must be in 0..65535.")
            self.server = LocalServer(("127.0.0.1", port), Handler)
            self.server.hub = self
            self.port = self.server.server_port
            self.url = f"http://127.0.0.1:{self.port}"
            for ident in ids:
                if not re.fullmatch(r"[a-z0-9_-]{1,32}", ident) or ident in self.bots:
                    raise ValueError("Invalid companion bot identity.")
                parent, child = channel_factory() if channel_factory else socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
                bot = self.bots[ident] = Bot(ident, parent, child)
                parent.setblocking(False)
                child.setblocking(False)
                credential = {"version": 1, "bot_id": ident, "run_id": self.run_id,
                              "url": self.url, "token": bot.token}
                with os.fdopen(os.open(self.directory / (ident+".json"), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as f:
                    json.dump(credential, f)
            self.thread = threading.Thread(target=self.server.serve_forever, args=(0.05,), name="jk-companion")
            self.thread.start()
        except BaseException:
            self.close()
            raise

    def take_socket(self, ident):
        bot = self.bots[ident]
        if bot.child is None:
            raise RuntimeError("Native descriptor already handed off.")
        child, bot.child = bot.child, None
        return child

    def open_browser_channel(self, ident):
        """Take exclusive ownership in place of handing the same endpoint to a subprocess."""
        return BrowserChannel(self.take_socket(ident))

    def close(self):
        if self.thread and self.thread.is_alive():
            self.server.shutdown()
            self.thread.join()
        if self.server:
            self.server.interrupt_readers()
            self.server.server_close()
        for bot in self.bots.values():
            bot.sock.close()
            if bot.child:
                bot.child.close()
            (self.directory / (bot.ident + ".json")).unlink(missing_ok=True)

    def pump(self):
        with self.lock:
            now = self.clock()
            for bot in self.bots.values():
                bot.pump(now)

    def request(self, method, ident, route, query, token, body):
        with self.lock:
            bot = self.bots.get(ident)
            need(bot is not None and token.isascii() and hmac.compare_digest(bot.token, token),
                 "Bot credential required.", 401)
            now = self.clock()
            if bot.lease and now >= bot.lease_until:
                bot.expire_lease(now)
            fence = {"run_id": self.run_id, "world_epoch": bot.world, "life_epoch": bot.life}
            fresh = bot.state is not None and now - bot.observed <= 3
            if method == "GET":
                need(not query or route == "events", "Unexpected query.")
                if route == "capabilities":
                    return 200, dict(fence, protocol=1, native_active=fresh, chat_enabled=self.allow_chat,
                                     modes=MODES, resource_bins=RESOURCES, lease_seconds=30)
                if route == "observation":
                    return 200, dict(fence, state=bot.state, native_active=fresh,
                                     age_seconds=(now-bot.observed if bot.state else None))
                if route == "tactics":
                    return 200, dict(fence, **tactics.describe(), now=now, applied=list(bot.tactic_log))
                if route == "events":
                    need(not query or re.fullmatch(r"after=[0-9]{1,18}", query), "Invalid event cursor.")
                    after = int(query[6:]) if query else 0
                    need(after <= bot.cursor, "Cursor exceeds current history.", 409)
                    oldest = bot.events[0]["cursor"] if bot.events else 1
                    return 200, dict(fence, cursor=bot.cursor, gap=after < oldest-1,
                                     wire_dropped=bot.wire_dropped,
                                     events=[ev for ev in bot.events if ev["cursor"] > after])
                if route.startswith("commands/"):
                    cmd = bot.commands.get(route[9:])
                    need(cmd is not None, "Unknown request.", 404)
                    return 200, dict(run_id=self.run_id, **cmd.result(route[9:]))
                raise Problem(404, "Unknown companion operation.")
            need(not query, "Unexpected query.")
            need(route in {"attach", "renew", *KINDS}, "Unknown companion operation.", 404)
            need(type(body) is dict and FENCE <= body.keys(), "Missing observation fence.")
            need(type(body["run_id"]) is str and type(body["world_epoch"]) is int and
                 type(body["life_epoch"]) is int, "Invalid observation fence.")
            need(all(body[k] == v for k, v in fence.items()), "Stale run, world or life.", 409)
            if route == "attach":
                fields(body, FENCE | {"controller"})
                need(type(body["controller"]) is str and IDENTIFIER.fullmatch(body["controller"]), "Invalid controller.")
                need(fresh, "Waiting for native state.", 409)
                need(not bot.lease, "A controller holds this bot.", 409)
                bot.lease = secrets.token_urlsafe(24)
                bot.lease_until = now + 30
                return 200, dict(fence, lease_id=bot.lease, expires_in=30)
            if route in KINDS:
                return self.command(bot, route, body, now, fresh)
            fields(body, FENCE | {"lease_id"})
            self.check_lease(bot, body)
            need(fresh, "Waiting for native state.", 409)
            bot.lease_until = now + 30
            return 200, dict(fence, lease_id=bot.lease, expires_in=30)

    @staticmethod
    def check_lease(bot, body):
        supplied = body.get("lease_id")
        need(type(supplied) is str and supplied.isascii() and bot.lease and
             hmac.compare_digest(supplied, bot.lease), "Controller lease expired or invalid.", 409)

    def command(self, bot, route, body, now, fresh):
        base = FENCE | {"lease_id", "request_id"}
        strategy_options = {"ttl_seconds","weapon","resource","range","risk","focus_net_id","focus_guid"}
        fields(body, base | ({"mode"} if route == "strategy" else {"text"} if route == "say" else set()),
               strategy_options if route == "strategy" else
               {"preset", "values", "reset"} if route == "tactics" else ())
        key = body["request_id"]
        need(type(key) is str and IDENTIFIER.fullmatch(key), "Invalid request identifier.")
        fingerprint = json.dumps([route, body], sort_keys=True, separators=(",",":"))
        old = bot.commands.get(key)
        if old:
            need(old.fingerprint == fingerprint, "Request ID was already used with different data.", 409)
            return (202 if old.status == "pending" else 200), dict(run_id=self.run_id, **old.result(key))
        self.check_lease(bot, body)
        need(fresh, "Waiting for native state.", 409)
        deadline = min(now + 2, bot.lease_until)
        detail = None
        if route == "tactics":
            # The engine refuses a second adjustment within its commitment
            # window and reports it as rate_limited; its game clock decides.
            try:
                reset, values = tactics.resolve(body.get("preset"), body.get("values"), body.get("reset", False))
                payload = struct.pack("<d", deadline) + tactics.encode(reset, values)
            except ValueError as error:
                raise Problem(400, str(error)) from None
            detail = {"preset": body.get("preset"), "reset": reset, "values": values}
        elif route == "say":
            need(self.allow_chat, "This bot run has outbound companion chat disabled.", 403)
            need(plain_text(body["text"]), "Invalid or reserved game chat.")
            need(now - bot.last_chat >= 5, "Chat cooldown.", 429)
            payload = struct.pack("<d", deadline) + body["text"].encode("ascii")
        elif route == "strategy":
            mode = body["mode"]
            need(type(mode) is str and mode in MODES, "Unknown strategy mode.")
            weapon = integer(body.get("weapon", 0), 0, 10)
            resource = integer(body.get("resource", 0), 0, 65535)
            need(resource in RESOURCES, "Unknown stock resource bin.")
            distance = number(body.get("range", 0), 0, 12)
            need(distance == 0 or distance >= .2, "Preferred range is 0 or 0.2..12.")
            risk = number(body.get("risk", .5), 0, 1)
            net = integer(body.get("focus_net_id", 0), 0, UINT_MAX)
            guid = integer(body.get("focus_guid", 0), 0, UINT_MAX)
            target = bot.state["target"]
            need((net == guid == 0) or (net and guid and target and (net,guid) == (target["net_id"],target["guid"])),
                 "Focus must match a currently observed target.", 409)
            ttl = number(body.get("ttl_seconds", 10), .1, 30)
            deadline = min(now + ttl, bot.lease_until)
            payload = STRATEGY_PAYLOAD.pack(deadline, MODES.index(mode), weapon, resource, distance, risk, net, guid)
        else:
            payload = struct.pack("<d", deadline)
        if route != "release":
            need(len(bot.pending) < MAX_PENDING, "Native command queue is full.", 429)
        # Preserve all request IDs in a live lease. Past-lease history may be
        # evicted because the secret that authorized it cannot become live again.
        limit = COMMAND_HISTORY + (route == "release")
        while len(bot.commands) >= limit:
            victim = next((k for k,v in bot.commands.items() if v.lease != bot.lease and v.status != "pending"), None)
            need(victim is not None, "Command history full for this lease.", 429)
            del bot.commands[victim]
        if route == "release":
            bot.cancel()
            bot.lease = None
        elif route == "say":
            bot.last_chat = now
        seq = bot.next_seq()
        cmd = Command(route, fingerprint, body["lease_id"], seq, bot.world, bot.life,
                      frame(KINDS[route], bot.world, bot.life, seq, payload), deadline, detail=detail)
        bot.commands[key] = bot.pending[seq] = cmd
        return 202, dict(run_id=self.run_id, **cmd.result(key))


class Handler(BaseHTTPRequestHandler):
    server_version = "JKCompanion/1"
    # One bounded request per connection. No authorization headers, chat,
    # controller leases or request bodies should be copied into access logs.
    def log_message(self, *args):
        pass

    def handle(self):
        try:
            super().handle()
        except (ConnectionError, TimeoutError):
            # A client may disconnect midway through headers, including at shutdown.
            pass

    def setup(self):
        super().setup()
        self.connection.settimeout(1.5)

    def do_GET(self):
        self.dispatch("GET")

    def do_POST(self):
        self.dispatch("POST")

    def dispatch(self, method):
        try:
            hub = self.server.hub
            authority = f"127.0.0.1:{hub.port}"
            need(ipaddress.ip_address(self.client_address[0]).is_loopback and
                 self.headers.get_all("Host") == [authority] and
                 self.headers.get_all("Origin", []) in ([], [hub.url]) and
                 "cross-site" not in self.headers.get_all("Sec-Fetch-Site", []),
                 "Loopback and same origin required.", 403)
            auth = self.headers.get_all("Authorization", [])
            need(len(auth) == 1 and auth[0].startswith("Bearer "), "Bot credential required.", 401)
            parsed = urlsplit(self.path)
            match = re.fullmatch(r"/v1/bots/([a-z0-9_-]{1,32})/([a-z]+(?:/[A-Za-z0-9_-]{1,64})?)", parsed.path)
            need(match and not parsed.netloc and not parsed.fragment, "Unknown companion route.", 404)
            bot_id, route = match.groups()
            token = auth[0][7:]
            bot = hub.bots.get(bot_id)
            need(bot and token.isascii() and hmac.compare_digest(bot.token, token), "Bot credential required.", 401)
            length = self.headers.get_all("Content-Length", [])
            need("Transfer-Encoding" not in self.headers and len(length) <= 1, "Invalid request framing.")
            body = None
            if method == "POST":
                need(self.headers.get_content_type() == "application/json", "Expected application/json.", 415)
                need(len(length) == 1 and re.fullmatch(r"[0-9]{1,5}", length[0]), "Expected bounded body.")
                size = int(length[0])
                need(0 < size <= 4096, "Request body exceeds limit.", 413)
                def unique(pairs):
                    result = dict(pairs)
                    need(len(result) == len(pairs), "Duplicate JSON field.")
                    return result
                def reject_constant(value):
                    raise ValueError(value)
                payload = self.rfile.read(size)
                need(len(payload) == size, "Incomplete JSON body.")
                body = json.loads(payload.decode("utf-8"), object_pairs_hook=unique, parse_constant=reject_constant)
            else:
                need(not length or length == ["0"], "GET has no request body.")
            status, result = hub.request(method, bot_id, route, parsed.query, token, body)
        except Problem as error:
            status, result = error.status, {"error": str(error)}
        except (TimeoutError, UnicodeError, ValueError, RecursionError):
            status, result = 400, {"error": "Malformed request."}
        data = json.dumps(result, allow_nan=False, separators=(",", ":")).encode()
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass

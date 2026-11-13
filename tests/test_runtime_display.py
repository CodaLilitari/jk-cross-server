"""Manager display and readiness behavior using authored subprocess/IPC fixtures.

These fixtures exercise supervision and authenticated IPC, not game compatibility.
"""
import asyncio
import json
import os
from pathlib import Path
import socket
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

from manager import config
from manager.runtime import ServerManager
from web_gateway.ipc import NativeIPC


DISPLAY_KEYS = ("DISPLAY", "WAYLAND_DISPLAY", "SDL_VIDEO_DRIVER", "SDL_VIDEODRIVER", "EGL_PLATFORM", "XDG_RUNTIME_DIR")

# The helper deliberately uses the real loopback framing/authentication and runs
# as an owned child. Its descriptor contains only authored synthetic metadata.
ENGINE = r'''
import asyncio, contextlib, json, os, socket, struct, sys
from pathlib import Path

keys = ("DISPLAY", "WAYLAND_DISPLAY", "SDL_VIDEO_DRIVER", "SDL_VIDEODRIVER", "EGL_PLATFORM", "XDG_RUNTIME_DIR", "OPENJKDF2_SPECTATOR_FD", "OPENJKDF2_SPECTATOR_GEOMETRY_FD")
Path("engine-environment.json").write_text(json.dumps({k: os.environ.get(k) for k in keys}))
mode = 1 if "-motsCompat" in sys.argv else 0
flavor = os.environ.get("JK_FIXTURE_DESCRIPTOR", "valid")
writers = set()
observer_mode, world_epoch, control_epoch, frame_sequence = 0, 1, 1, 0
observer_target, observer_generation = 0, 0
observer_behavior = os.environ.get("JK_FIXTURE_SPECTATOR", "normal")
frame_socket = socket.socket(fileno=int(os.environ["OPENJKDF2_SPECTATOR_FD"])) if os.environ.get("OPENJKDF2_SPECTATOR_FD") else None
geometry_socket = socket.socket(fileno=int(os.environ["OPENJKDF2_SPECTATOR_GEOMETRY_FD"])) if os.environ.get("OPENJKDF2_SPECTATOR_GEOMETRY_FD") else None
geometry_enabled = False
if geometry_socket:
    geometry_socket.setblocking(False)
if frame_socket:
    frame_socket.setblocking(False)

def observer_reply(operation, result=0):
    flags = 1 | (32 if observer_mode else 0) | (2 if frame_sequence else 0)
    if observer_behavior == "render-error":
        flags |= 64
    rows = [struct.pack("<III64s", 101, 17, 1, "Fixture player".encode("utf-16-le"))] if operation == 0 and observer_behavior != "empty-roster" else []
    return struct.pack("<16I6fi", 1, result, operation, (15 if frame_socket else 0) | (16 if geometry_socket and observer_behavior != "old-image-engine" else 0), observer_mode,
                       flags, world_epoch, control_epoch, observer_target, observer_generation,
                       4, 2, 5000 if observer_behavior == "stale-frame" else (0 if frame_sequence else 0xffffffff),
                       6 if observer_behavior == "render-error" else (0 if observer_mode else 7),
                       len(rows), frame_sequence, 1., 2., 3., 0., 0., 0., 1) + b"".join(rows)

async def observer_request(writer, source, destination, payload):
    global observer_mode, control_epoch, observer_target, observer_generation, frame_sequence, geometry_enabled
    global observer_behavior
    if observer_behavior == "silent":
        return
    if observer_behavior == "unsupported":
        writer.write(frame(199, source=11, destination=6, payload=b"unknown request"))
        return
    if observer_behavior == "malformed":
        writer.write(frame(114, destination=destination, payload=b"bad"))
        return
    version, operation = struct.unpack_from("<II", payload)
    result = 0
    if source or version != 1 or len(payload) != {0: 8, 1: 28, 2: 40, 3: 20}.get(operation):
        result = 1
    elif operation:
        expected_world, expected_control = struct.unpack_from("<II", payload, 8)
        if operation == 3 and observer_behavior == "geometry-epoch-transition":
            # A follow target leaves after the manager's epoch check.
            control_epoch += 1
            observer_mode, observer_target, observer_generation = 1, 0, 0
            frame_sequence, geometry_enabled = 0, False
            observer_behavior = "normal"
        if (expected_world, expected_control) != (world_epoch, control_epoch):
            result = 2
        elif operation == 1:
            selected_mode, peer, generation = struct.unpack_from("<III", payload, 16)
            if selected_mode == 2 and (peer, generation) != (101, 17):
                result = 3
            else:
                observer_mode, observer_target, observer_generation = selected_mode, peer, generation
                control_epoch += 1
                frame_sequence = 0
        elif operation == 3:
            if observer_behavior == "geometry-deny":
                result = 4
            if observer_behavior == "geometry-reject":
                writer.write(frame(199, source=11, destination=6, payload=b"unsupported geometry"))
                return
            geometry_enabled = bool(struct.unpack_from("<I", payload, 16)[0])
            if not observer_mode:
                result = 4
        elif observer_mode != 1:
            result = 5
    with Path("observer-requests.jsonl").open("a") as output:
        output.write(json.dumps({"source": source, "operation": operation, "bytes": len(payload)}) + "\n")
    if observer_behavior == "drop-enable-reply" and operation == 1 and not result and observer_mode:
        return
    writer.write(frame(114, destination=destination, payload=observer_reply(operation, result)))

async def publish_observer_frame(oversized=False):
    global frame_sequence
    if not frame_socket:
        return
    frame_sequence += 1
    pixels = bytes([frame_sequence, 20, 30, 255]) * 8
    header = struct.pack("<4s8I", b"JKSV", 1, 4, 2, world_epoch, control_epoch,
                         frame_sequence, 640 * 360 * 4 + 4 if oversized else len(pixels), 0)
    parts = (header[:7], header[7:]) if oversized else (header[:7], header[7:], pixels[:9], pixels[9:])
    for part in parts:
        await asyncio.get_running_loop().sock_sendall(frame_socket, part)

async def publish_geometry(kind):
    global frame_sequence
    if not geometry_socket or not geometry_enabled:
        return
    frame_sequence += 1
    vertices = b"".join(struct.pack("<4f4B", x, y, 0., 1., 255, 40, 20, 255) for x, y in ((-1., -1.), (1., -1.), (0., 1.)))
    indices = struct.pack("<3I", 0, 1, 2)
    fields = [b"JKSG", 1, 4, 2, world_epoch, control_epoch, frame_sequence, 72, 0, 0, 3, 3, 0, 0, 0, 0]
    if kind == "oversize": fields[7] = 2097153
    if kind == "stale": fields[9] = 2001
    if kind == "epoch": fields[4] += 1
    if kind == "reserved": fields[12] = 1
    if kind == "count": fields[10] = 65537
    if kind == "nonfinite": vertices = struct.pack("<f", float("nan")) + vertices[4:]
    if kind == "alpha": vertices = vertices[:19] + b"\x00" + vertices[20:]
    if kind == "index": indices = struct.pack("<3I", 0, 1, 3)
    if kind == "empty": fields[7], fields[10], fields[11], vertices, indices = 0, 0, 0, b"", b""
    envelope = struct.pack("<4s15I", *fields) + vertices + indices
    try:
        for part in (envelope[:7], envelope[7:64], envelope[64:]):
            await asyncio.get_running_loop().sock_sendall(geometry_socket, part)
            if kind == "delayed" and len(part) == 57:
                await asyncio.sleep(2.1)
    except (BrokenPipeError, ConnectionResetError):
        pass

def frame(kind, source=0, destination=0, payload=b""):
    body = struct.pack("<III", kind, source, destination) + payload
    return struct.pack("<I", len(body)) + body

def descriptor(flavor):
    data = bytearray(240)
    if flavor != "blank":
        struct.pack_into("<ii", data, 16, 8, 2)
        name = "Manager fixture".encode("utf-16-le")
        data[24:24+len(name)] = name
        data[88:93] = b"JK1MP"
        data[120:126] = b"m3.jkl" if flavor == "next-map" else b"m2.jkl"
        struct.pack_into("<ii", data, 228, 0x1000, 100)
    if flavor == "bad-count":
        struct.pack_into("<i", data, 20, -1)
    return bytes(data[:-1] if flavor == "truncated" else data)

def info():
    return frame(102, payload=struct.pack("<I", 1-mode if flavor == "wrong-mode" else mode) + descriptor(flavor))

async def read(reader):
    length = struct.unpack("<I", await reader.readexactly(4))[0]
    body = await reader.readexactly(length)
    return (*struct.unpack_from("<III", body), body[12:])

async def handle(reader, writer):
    writers.add(writer)
    try:
        kind, source, destination, payload = await read(reader)
        if kind != 1 or payload.decode() != os.environ["OPENJKDF2_GATEWAY_TOKEN"]:
            return
        writer.write(frame(101, payload=struct.pack("<I", 1)))
        await writer.drain()
        while True:
            kind, source, destination, payload = await read(reader)
            if kind == 2 and flavor != "missing":
                writer.write(info())
            elif kind == 7:
                writer.write(frame(107, destination=destination))
            elif kind == 8:
                writer.write(frame(108, destination=destination, payload=struct.pack("<I", len(payload)//4)))
            elif kind == 11:
                await observer_request(writer, source, destination, payload)
            await writer.drain()
    except (ConnectionError, asyncio.IncompleteReadError):
        pass
    finally:
        writers.discard(writer)
        writer.close()
        with contextlib.suppress(ConnectionError):
            await writer.wait_closed()

async def main():
    global flavor, observer_behavior, world_epoch, control_epoch, observer_mode, frame_sequence
    server = await asyncio.start_server(handle, "127.0.0.1", int(os.environ["OPENJKDF2_GATEWAY_PORT"]))
    reader = asyncio.StreamReader()
    await asyncio.get_running_loop().connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin)
    while command := await reader.readline():
        command = command.decode().strip()
        if command == "disconnect":
            server.close()
            for writer in tuple(writers):
                writer.close()
            await server.wait_closed()
        elif command.startswith("geometry-"):
            await publish_geometry(command.removeprefix("geometry-"))
        elif command == "observer-frame":
            await publish_observer_frame()
        elif command == "observer-oversize":
            await publish_observer_frame(oversized=True)
        elif command == "observer-map":
            world_epoch += 1
            control_epoch += 1
            observer_mode, frame_sequence = 0, 0
        elif command.startswith("observer-"):
            observer_behavior = command.removeprefix("observer-")
        else:
            flavor = command
            if flavor != "missing":
                for writer in tuple(writers):
                    writer.write(info())
                    await writer.drain()
    await asyncio.Event().wait()

asyncio.run(main())
'''

WINE = r'''
import asyncio, json, os, struct
from pathlib import Path

keys = ("DISPLAY", "WAYLAND_DISPLAY", "SDL_VIDEO_DRIVER", "SDL_VIDEODRIVER", "EGL_PLATFORM")
Path("wine-environment.json").write_text(json.dumps({k: os.environ.get(k) for k in keys}))

def frame(kind, payload):
    body = struct.pack("<III", kind, 0, 0) + payload
    return struct.pack("<I", len(body)) + body

async def read(reader):
    size = struct.unpack("<I", await reader.readexactly(4))[0]
    return await reader.readexactly(size)

async def main():
    reader, writer = await asyncio.open_connection("127.0.0.1", int(os.environ["JK_GATEWAY_PORT"]))
    writer.write(frame(1, os.environ["JK_GATEWAY_TOKEN"].encode()))
    await writer.drain()
    await read(reader)
    writer.write(frame(8, struct.pack("<III", 101, 102, 103)))
    await writer.drain()
    await read(reader)
    await reader.read()
    writer.close()
    await writer.wait_closed()

asyncio.run(main())
'''

XVFB = r'''
import os, sys
env = os.environ.copy()
env["DISPLAY"] = ":77"
os.execvpe(sys.argv[4], sys.argv[4:], env)
'''


def executable(path, source):
    path.write_text("#!" + sys.executable + "\n" + source, encoding="utf-8")
    path.chmod(0o700)
    return str(path)


def game_data(root):
    (root / "resource").mkdir(parents=True)
    (root / "episode").mkdir()
    for name in ("jk_.cd", "res1.gob", "res2.gob"):
        (root / "resource" / name).write_bytes(b"")
    payload, rows = bytearray(), []
    for name, data in (("episode.jk", b'"Manager fixture"\nTYPE 2\n'),
                       ("jkl/m2.jkl", b"# authored catalog fixture\n")):
        rows.append(struct.pack("<II128s", 12 + len(payload), len(data), name.encode()))
        payload.extend(data)
    (root / "episode/jk1mp.gob").write_bytes(
        b"GOB " + struct.pack("<II", 20, 12 + len(payload)) + payload +
        struct.pack("<I", len(rows)) + b"".join(rows))


class DisplayConfigurationTests(unittest.TestCase):
    def test_existing_config_defaults_to_automatic_display_selection(self):
        self.assertEqual(config.validate({}).get("engine_display"), "auto")

    def test_display_mode_roundtrip_and_rejected_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            for mode in ("auto", "offscreen", "xvfb", "display"):
                with self.subTest(mode=mode):
                    config.save(path, {"engine_display": mode})
                    self.assertEqual(config.load(path)["engine_display"], mode)
        for value in (None, [], {}, True, 1, "OFFSCREEN", "dummy", ""):
            with self.subTest(value=value), self.assertRaises(config.ConfigError):
                config.validate({"engine_display": value})


class RuntimeFixture(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        game_data(self.root / "game")
        engine = executable(self.root / "engine", ENGINE)
        self.wine = executable(self.root / "wine", WINE)
        self.xvfb = executable(self.root / "xvfb-run", XVFB)
        self.bridge = self.root / "bridge.exe"
        self.bridge.write_bytes(b"authored placeholder passed to the Wine fixture")
        sockets = [socket.socket() for _ in range(3)]
        for listener in sockets:
            listener.bind(("127.0.0.1", 0))
        ports = [listener.getsockname()[1] for listener in sockets]
        for listener in sockets:
            listener.close()
        self.config_path = self.root / "config.json"
        config.save(self.config_path, {"engine": engine, "game_data": str(self.root / "game"),
                                      "web_enabled": False, "ipc_port": ports[0],
                                      "broker_port": ports[1], "web_port": ports[2]})
        self.manager = ServerManager(self.config_path, self.root / "state")
        self.environment = patch.dict(os.environ, {key: value for key, value in os.environ.items()
                                                   if key not in DISPLAY_KEYS}, clear=True)
        self.environment.start()
        self.lookup = patch("manager.runtime.shutil.which", return_value=None)
        self.lookup_mock = self.lookup.start()

    async def asyncTearDown(self):
        await self.manager.close()
        self.lookup.stop()
        self.environment.stop()
        self.temporary.cleanup()

    def observed(self, component="engine"):
        return json.loads((self.manager.run_dir / f"{component}-environment.json").read_text())

    async def wait_status(self, predicate):
        async def wait():
            while not predicate(self.manager.status()):
                await asyncio.sleep(0.01)
            return self.manager.status()
        return await asyncio.wait_for(wait(), 3)

    async def command(self, command):
        self.manager.processes["engine"].stdin.write((command + "\n").encode())
        await self.manager.processes["engine"].stdin.drain()

    def retail(self):
        self.manager.config.update(retail_enabled=True, directplay_bridge=str(self.bridge), wine=self.wine)


class RuntimeDisplayTests(RuntimeFixture):
    async def test_automatic_start_works_without_x_display_or_xvfb(self):
        status = await self.manager.start()
        self.assertEqual(status["state"], "running")
        self.assertTrue(status.get("session_ready"))
        self.assertEqual(status.get("engine_display_backend"), "offscreen")
        self.assertEqual(self.observed()["SDL_VIDEO_DRIVER"], "offscreen")
        self.assertEqual(self.observed()["EGL_PLATFORM"], "surfaceless")
        self.assertIsNone(self.observed()["DISPLAY"])

    async def test_auto_preserves_explicit_display_and_driver_configuration(self):
        os.environ.update(DISPLAY=":24", SDL_VIDEO_DRIVER="x11", SDL_VIDEODRIVER="x11", EGL_PLATFORM="x11")
        status = await self.manager.start()
        self.assertEqual(status["engine_display_backend"], "display")
        observed = self.observed()
        self.assertEqual(observed["DISPLAY"], ":24")
        self.assertEqual(observed["SDL_VIDEO_DRIVER"], "x11")
        self.assertEqual(observed["EGL_PLATFORM"], "x11")

    async def test_auto_preserves_explicit_wayland_driver(self):
        os.environ.update(WAYLAND_DISPLAY="wayland-7", SDL_VIDEO_DRIVER="wayland", XDG_RUNTIME_DIR="/tmp/intentional-wayland-runtime")
        status = await self.manager.start()
        self.assertEqual(status["engine_display_backend"], "display")
        self.assertEqual(self.observed()["WAYLAND_DISPLAY"], "wayland-7")
        self.assertEqual(self.observed()["SDL_VIDEO_DRIVER"], "wayland")
        self.assertEqual(self.observed()["XDG_RUNTIME_DIR"], "/tmp/intentional-wayland-runtime")

    async def test_explicit_offscreen_overrides_inherited_display_backend(self):
        os.environ.update(DISPLAY=":24", SDL_VIDEO_DRIVER="x11", SDL_VIDEODRIVER="x11", EGL_PLATFORM="x11")
        self.manager.config["engine_display"] = "offscreen"
        status = await self.manager.start()
        self.assertEqual(status["engine_display_backend"], "offscreen")
        for key in ("SDL_VIDEO_DRIVER", "SDL_VIDEODRIVER"):
            self.assertEqual(self.observed()[key], "offscreen")
        self.assertEqual(self.observed()["EGL_PLATFORM"], "surfaceless")

    async def test_explicit_display_without_display_fails_before_launch(self):
        self.manager.config["engine_display"] = "display"
        with self.assertRaisesRegex(config.ConfigError, "DISPLAY|display"):
            await self.manager.start()
        self.assertEqual(self.manager.processes, {})
        self.assertFalse((self.manager.run_dir / "engine-environment.json").exists())

    async def test_explicit_xvfb_missing_has_targeted_error(self):
        self.manager.config["engine_display"] = "xvfb"
        with self.assertRaisesRegex(config.ConfigError, "Xvfb|xvfb"):
            await self.manager.start()
        self.assertEqual(self.manager.processes, {})

    async def test_explicit_xvfb_works_even_when_parent_has_a_display(self):
        self.lookup_mock.return_value = self.xvfb
        self.manager.config["engine_display"] = "xvfb"
        os.environ.update(DISPLAY=":24", SDL_VIDEO_DRIVER="offscreen", SDL_VIDEODRIVER="offscreen", EGL_PLATFORM="surfaceless")
        status = await self.manager.start()
        self.assertEqual(status["engine_display_backend"], "xvfb")
        self.assertEqual(self.observed()["DISPLAY"], ":77")
        self.assertEqual(self.observed()["SDL_VIDEO_DRIVER"], "x11")
        self.assertNotEqual(self.observed()["EGL_PLATFORM"], "surfaceless")

    async def test_retail_display_preflight_happens_before_core_launch(self):
        self.retail()
        with self.assertRaisesRegex(config.ConfigError, "Wine|retail|Retail"):
            await self.manager.start()
        self.assertEqual(self.manager.processes, {})
        self.assertFalse((self.manager.run_dir / "engine-environment.json").exists())

    async def test_retail_gets_its_own_xvfb_and_not_core_offscreen_overrides(self):
        self.retail()
        self.lookup_mock.return_value = self.xvfb
        self.manager.config["engine_display"] = "offscreen"
        status = await self.manager.start()
        self.assertTrue(status["retail_ready"])
        self.assertEqual(self.observed()["SDL_VIDEO_DRIVER"], "offscreen")
        wine = self.observed("wine")
        self.assertEqual(wine["DISPLAY"], ":77")
        self.assertNotEqual(wine["SDL_VIDEO_DRIVER"], "offscreen")
        self.assertNotEqual(wine["SDL_VIDEODRIVER"], "offscreen")
        self.assertNotEqual(wine["EGL_PLATFORM"], "surfaceless")

    async def test_retail_preserves_parent_display_when_core_forces_offscreen(self):
        self.retail()
        self.manager.config["engine_display"] = "offscreen"
        os.environ["DISPLAY"] = ":24"
        status = await self.manager.start()
        self.assertTrue(status["retail_ready"])
        self.assertEqual(self.observed()["SDL_VIDEO_DRIVER"], "offscreen")
        self.assertEqual(self.observed("wine")["DISPLAY"], ":24")
        self.assertNotEqual(self.observed("wine")["SDL_VIDEO_DRIVER"], "offscreen")

    async def test_invalid_initial_descriptors_never_claim_running_or_ready(self):
        for flavor in ("blank", "bad-count", "wrong-mode"):
            with self.subTest(flavor=flavor):
                os.environ["JK_FIXTURE_DESCRIPTOR"] = flavor
                with self.assertRaises(RuntimeError):
                    await self.manager.start()
                status = self.manager.status()
                self.assertEqual(status["state"], "failed")
                self.assertFalse(status["session_ready"])
                self.assertIsNone(status["session"])
                self.assertEqual(status["processes"], {})

    async def test_missing_or_truncated_info_never_claims_running_or_ready(self):
        wait_ready = NativeIPC.wait_ready
        async def short_wait(ipc, timeout=40):
            return await wait_ready(ipc, timeout=.4)
        for flavor in ("missing", "truncated"):
            with self.subTest(flavor=flavor), patch.object(NativeIPC, "wait_ready", short_wait):
                os.environ["JK_FIXTURE_DESCRIPTOR"] = flavor
                with self.assertRaises(ConnectionError):
                    await self.manager.start()
                self.assertFalse(self.manager.status()["session_ready"])
                self.assertIsNone(self.manager.session)
                self.assertEqual(self.manager.processes, {})

    async def test_invalid_refresh_clears_session_and_valid_next_map_restores_it(self):
        await self.manager.start()
        await self.command("blank")
        await self.wait_status(lambda status: not status["session_ready"])
        self.assertIsNone(self.manager.session)
        await self.command("next-map")
        status = await self.wait_status(lambda value: value["session_ready"])
        self.assertEqual(status["session"]["map"], "m3.jkl")
        self.assertEqual(status["session"]["players"], 2)

    async def test_disconnect_clears_session_while_owned_process_is_still_alive(self):
        await self.manager.start()
        engine = self.manager.processes["engine"]
        await self.command("disconnect")
        status = await self.wait_status(lambda value: not value["native_connected"])
        self.assertIsNone(engine.returncode)
        self.assertFalse(status["session_ready"])
        self.assertIsNone(status["session"])

    async def test_stop_clears_live_session_map_and_player_counts(self):
        await self.manager.start()
        self.assertEqual(self.manager.session["players"], 2)
        status = await self.manager.stop()
        self.assertFalse(status["session_ready"])
        self.assertFalse(status["native_connected"])
        self.assertIsNone(status["session"])
        self.assertIsNone(status["engine_display_backend"])

    async def test_failed_refresh_clears_session_until_current_info_arrives(self):
        await self.manager.start()
        self.manager.ipc.request_timeout = .1
        await self.command("missing")
        status = await self.wait_status(lambda value: not value["session_ready"])
        self.assertTrue(status["native_connected"])
        self.assertIsNone(status["session"])
        await self.command("next-map")
        status = await self.wait_status(lambda value: value["session_ready"])
        self.assertEqual(status["session"]["map"], "m3.jkl")

    async def test_late_refresh_failure_cannot_clear_newer_info_callback(self):
        await self.manager.start()
        entered, finish = asyncio.Event(), asyncio.Event()
        async def late_failure(*, refresh=False):
            entered.set()
            await finish.wait()
            raise asyncio.TimeoutError()
        with patch.object(self.manager.ipc, "info", late_failure):
            await asyncio.wait_for(entered.wait(), 3)
            await self.command("next-map")
            await self.wait_status(lambda value: value["session"] and value["session"]["map"] == "m3.jkl")
            finish.set()
            await asyncio.sleep(.05)
            self.assertTrue(self.manager.status()["session_ready"])
            self.assertEqual(self.manager.session["map"], "m3.jkl")

    async def test_old_refresh_failure_cannot_clear_a_restarted_session(self):
        await self.manager.start()
        old_ipc = self.manager.ipc
        entered, finish = asyncio.Event(), asyncio.Event()
        async def late_failure(*, refresh=False):
            entered.set()
            await finish.wait()
            raise asyncio.TimeoutError()
        with patch.object(old_ipc, "info", late_failure):
            await asyncio.wait_for(entered.wait(), 3)
            await self.manager.stop()
            await self.manager.start()
            self.assertIsNot(self.manager.ipc, old_ipc)
            finish.set()
            await asyncio.sleep(.05)
            self.assertTrue(self.manager.status()["session_ready"])
            self.assertEqual(self.manager.session["map"], "m2.jkl")


if __name__ == "__main__":
    unittest.main()

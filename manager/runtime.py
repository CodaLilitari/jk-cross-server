"""Supervise the real game engine and transport adapters as one session."""
from __future__ import annotations
import asyncio
import collections
import contextlib
import datetime
import json
import os
import secrets
import shutil
import signal
import time
from pathlib import Path
from aiohttp import web
from web_gateway.ipc import NativeIPC
from web_gateway.gateway import WebGateway, session_details
from web_gateway.assets import build_asset_provider
from . import config as conf
from .content import child_casefold, preflight
from .broker import AdapterBroker

def stage_file(source, destination):
    # Resolve symlinked test/install inputs; create an independent directory
    # tree. Archives are read-only inputs to the engine.
    try:
        os.link(Path(source).resolve(), destination)
    except OSError:
        shutil.copy2(source, destination)
    return str(destination)

def stage_tree(source: Path, target: Path):
    target.mkdir()
    for child in source.iterdir():
        name = child.name.casefold()
        if name == "video":
            continue
        output = target / name
        if output.exists():
            raise conf.ConfigError(f"Ambiguous filename case in {source}: {child.name}")
        if child.is_dir():
            stage_tree(child, output)
        elif child.is_file():
            stage_file(child, output)

class ServerManager:
    def __init__(self, config_path: Path, state_dir: Path, *, updater=None):
        self.config_path, self.state_dir = config_path, state_dir
        self.updater = updater
        self.panel_closing = False
        self.config = conf.load(config_path)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state = "stopped"
        self.error = None
        self.logs = collections.deque(maxlen=600)
        self.processes = {}
        self.tasks = set()
        self.ipc = self.broker = self.gateway = self.web_runner = None
        self.assets = None
        self.run_dir = None
        self.started = None
        self.session = None
        self.preflight_result = None
        self.lock = asyncio.Lock()
        self.intentional_stop = False
        self.generation = 0
        self.restart_attempts = 0

    def log(self, message, source="manager"):
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        row = {"time": timestamp, "source": source, "text": str(message)[:4000]}
        self.logs.append(row)
        if self.run_dir:
            path = self.run_dir / "session.jsonl"
            if path.exists() and path.stat().st_size > 10 * 1024 * 1024:
                path.replace(path.with_suffix(".previous.jsonl"))
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")

    def track(self, coro, name):
        task = asyncio.create_task(coro, name=name)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    def status(self):
        return {"state": self.state, "error": self.error,
                "uptime_seconds": round(time.monotonic() - self.started) if self.started else 0,
                "processes": {name: {"pid": proc.pid, "returncode": proc.returncode} for name, proc in self.processes.items()},
                "native_connected": bool(self.ipc and self.ipc.connected),
                "retail_ready": bool(self.broker and self.broker.pool_ready.is_set()),
                "browser": self.gateway.status() if self.gateway else None,
                "browser_assets": self.assets.summary() if self.assets else None,
                "browser_transfer": dict(self.gateway.metrics) if self.gateway else None,
                "session": self.session, "preflight": self.preflight_result,
                "run_directory": str(self.run_dir) if self.run_dir else None,
                "logs": list(self.logs)}

    async def update_config(self, value):
        async with self.lock:
            if self.state not in ("stopped", "failed"):
                raise conf.ConfigError("Stop the session before changing its settings.")
            self.config = conf.save(self.config_path, value)
            return self.config

    def prepare(self):
        data = Path(self.config["game_data"])
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.run_dir = self.state_dir / "runs" / (stamp + "-" + secrets.token_hex(3))
        self.run_dir.mkdir(parents=True, mode=0o700)
        for dirname in ("resource", "episode"):
            source = child_casefold(data, dirname)
            target = self.run_dir / dirname
            stage_tree(source, target)
        # These are original empty disc marker files, never a client patch.
        # Preserve existing marker names; the engine needs its data-discovery
        # marker before it initializes the dedicated session.
        (self.run_dir / "player").mkdir()
        if self.config["mod_dir"]:
            stage_tree(Path(self.config["mod_dir"]), self.run_dir / "mod")
        (self.run_dir / "registry.json").write_text(json.dumps(conf.registry(self.config), indent=2), encoding="utf-8")
        (self.run_dir / "config.snapshot.json").write_text(json.dumps(self.config, indent=2), encoding="utf-8")
        (self.run_dir / "preflight.json").write_text(json.dumps(self.preflight_result, indent=2), encoding="utf-8")

    async def spawn(self, name, argv, env):
        kwargs = {"cwd": str(self.run_dir), "env": env, "stdin": asyncio.subprocess.PIPE,
                  "stdout": asyncio.subprocess.PIPE, "stderr": asyncio.subprocess.STDOUT}
        if os.name != "nt":
            kwargs["start_new_session"] = True
        proc = await asyncio.create_subprocess_exec(*argv, **kwargs)
        self.processes[name] = proc
        self.log(f"Started {name} (PID {proc.pid})")
        self.track(self.read_log(name, proc), name + "-logs")
        self.track(self.watch(name, proc, self.generation), name + "-watch")
        return proc

    async def read_log(self, name, proc):
        pending = b""
        while chunk := await proc.stdout.read(4096):
            pending += chunk.replace(b"\r", b"\n")
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                text = line.decode("utf-8", errors="replace").strip()
                if text and text != ">":
                    self.log(text, name)
            if len(pending) > 8192:
                self.log(pending[:4000].decode("utf-8", errors="replace"), name)
                pending = b""
        if pending.strip():
            self.log(pending.decode("utf-8", errors="replace"), name)

    async def watch(self, name, proc, generation):
        code = await proc.wait()
        self.log(f"{name} exited with code {code}")
        # Startup checks its own failures. Only the active generation may
        # react to an exit; an old watcher cannot stop a newer session.
        if generation != self.generation or self.intentional_stop or self.state != "running":
            return
        reason = f"{name} exited with code {code}"
        await self.stop(failure=reason)
        if self.config["auto_restart"] and self.restart_attempts < 3:
            self.restart_attempts += 1
            await asyncio.sleep(min(2 ** self.restart_attempts, 8))
            if self.state == "failed" and self.generation == generation + 1:
                try:
                    await self.start(restarting=True)
                except Exception as exc:
                    self.log(f"Automatic restart failed: {exc}")

    async def on_info(self, mode, entry):
        try:
            self.session = session_details(entry)
            self.session["game"] = "mots" if mode else "jk"
        except (ValueError, TypeError):
            self.session = {"game": "mots" if mode else "jk", "descriptor_bytes": len(entry)}

    async def start(self, restarting=False):
        async with self.lock:
            if self.panel_closing:
                raise conf.ConfigError("The control panel is restarting or closing.")
            if self.state not in ("stopped", "failed"):
                raise conf.ConfigError("The session is already active.")
            if self.updater and self.updater.status()["restart_required"]:
                raise conf.ConfigError("Restart this control panel before starting a session with the updated files.")
            self.config = conf.validate(self.config, require_paths=True)
            if self.updater:
                self.updater.acquire_session_lease()
            self.state, self.error = "starting", None
            self.intentional_stop = False
            self.generation += 1
            if not restarting:
                self.restart_attempts = 0
            try:
                self.assets = None
                self.preflight_result = await asyncio.to_thread(preflight, self.config)
                await asyncio.to_thread(self.prepare)
                if self.config["web_enabled"]:
                    self.log("Preparing selected browser map and mod downloads…")
                    self.assets = await build_asset_provider(
                        game_root=self.run_dir, episode_name=self.config["episode"],
                        mode=1 if self.config["game"] == "mots" else 0,
                        mod_root=self.run_dir / "mod" if self.config["mod_dir"] else None,
                        mod_name=Path(self.config["mod_dir"]).name if self.config["mod_dir"] else "",
                        download_enabled=self.config["web_asset_downloads"],
                    )
                    self.preflight_result["browser_assets"] = self.assets.summary()
                    await asyncio.to_thread(
                        (self.run_dir / "preflight.json").write_text,
                        json.dumps(self.preflight_result, indent=2), encoding="utf-8",
                    )
                    self.log("Browser content prepared; transfer policy and hashes are available in session status.")
                token = secrets.token_urlsafe(32)
                env = os.environ.copy()
                runtime_dir = self.run_dir / "xdg"
                runtime_dir.mkdir(mode=0o700)
                env["XDG_RUNTIME_DIR"] = str(runtime_dir)
                env.update(OPENJKDF2_GATEWAY_TOKEN=token, OPENJKDF2_GATEWAY_PORT=str(self.config["ipc_port"]),
                           OPENJKDF2_REQUIRE_DP_POOL="1" if self.config["retail_enabled"] else "0",
                           ALSOFT_DRIVERS="null", SDL_AUDIODRIVER="dummy", LIBGL_ALWAYS_SOFTWARE="1")
                library_path = str(Path(self.config["engine"]).parent)
                env["LD_LIBRARY_PATH"] = library_path + os.pathsep + env.get("LD_LIBRARY_PATH", "")
                argv = [self.config["engine"], "-headless", "-dedicatedServer", "-episode", self.config["episode"], "-map", self.config["map"]]
                if self.config["game"] == "mots":
                    argv.append("-motsCompat")
                if self.config["mod_dir"]:
                    argv += ["-path", "mod"]
                if os.name != "nt" and not env.get("DISPLAY"):
                    xvfb = shutil.which("xvfb-run")
                    if not xvfb:
                        raise conf.ConfigError("The engine needs an X display at bootstrap. Install Xvfb or set DISPLAY.")
                    argv = [xvfb, "-a", "-s", "-screen 0 640x480x24", *argv]
                self.ipc = NativeIPC(port=self.config["ipc_port"], token=token)
                self.ipc.subscribe_info(self.on_info)
                await self.spawn("engine", argv, env)
                await self.ipc.start()
                await self.ipc.wait_ready(timeout=40)
                mode, entry = await self.ipc.info()
                if mode != (1 if self.config["game"] == "mots" else 0):
                    raise RuntimeError("Engine started in the wrong game mode.")
                await self.on_info(mode, entry)
                self.broker = AdapterBroker(self.ipc, token, self.config["broker_port"], self.log)
                await self.broker.start()
                if self.config["retail_enabled"]:
                    bridge_env = env.copy()
                    bridge_env.update(JK_GATEWAY_TOKEN=token, JK_GATEWAY_PORT=str(self.config["broker_port"]))
                    if self.config["wine_prefix"]:
                        bridge_env["WINEPREFIX"] = self.config["wine_prefix"]
                    bridge = [self.config["directplay_bridge"], "--pool", str(min(self.config["max_players"], 15))]
                    if os.name != "nt":
                        bridge.insert(0, self.config["wine"])
                        if not env.get("DISPLAY"):
                            bridge = [xvfb, "-a", "-s", "-screen 0 640x480x24", *bridge]
                    await self.spawn("directplay", bridge, bridge_env)
                    await asyncio.wait_for(self.broker.pool_ready.wait(), 35)
                if self.config["web_enabled"]:
                    self.gateway = WebGateway(self.ipc, client_dir=Path(self.config["web_client"]) if self.config["web_client"] else None,
                                              enable_webrtc=True, allowed_origins=self.config["web_origins"],
                                              ice_servers=self.config["web_ice_servers"], assets=self.assets)
                    self.web_runner = web.AppRunner(self.gateway.create_app(), access_log=None)
                    await self.web_runner.setup()
                    await web.TCPSite(self.web_runner, self.config["web_bind"], self.config["web_port"]).start()
                if any(p.returncode is not None for p in self.processes.values()):
                    raise RuntimeError("A server component exited during startup.")
                self.state, self.started = "running", time.monotonic()
                self.track(self.refresh_status(self.generation), "session-status")
                self.log("Session running; compatibility qualification is recorded separately in qa/.")
            except BaseException as exc:
                self.error = str(exc) or type(exc).__name__
                self.log("Startup failed: " + self.error)
                await self._cleanup()
                self.state = "failed"
                raise
        return self.status()

    async def refresh_status(self, generation):
        while self.generation == generation and self.state == "running":
            await asyncio.sleep(2)
            try:
                if self.ipc:
                    await self.ipc.info(refresh=True)
            except (ConnectionError, RuntimeError, asyncio.TimeoutError):
                pass

    async def _cleanup(self):
        self.intentional_stop = True
        if self.gateway:
            await self.gateway.close()
            self.gateway = None
        self.assets = None
        if self.web_runner:
            await self.web_runner.cleanup()
            self.web_runner = None
        if self.broker:
            await self.broker.close()
            self.broker = None
        if self.ipc:
            await self.ipc.close()
            self.ipc = None
        for name, proc in reversed(list(self.processes.items())):
            if proc.returncode is not None:
                continue
            if name == "directplay":
                # Broker EOF lets the adapter close its session, then its Wine
                # launcher can ask the original helper to exit normally.
                try:
                    await asyncio.wait_for(proc.wait(), 8)
                    continue
                except asyncio.TimeoutError:
                    pass
            with contextlib.suppress(ProcessLookupError):
                if os.name == "nt":
                    proc.terminate()
                else:
                    os.killpg(proc.pid, signal.SIGTERM)
            try:
                await asyncio.wait_for(proc.wait(), 5)
            except asyncio.TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    if os.name == "nt":
                        proc.kill()
                    else:
                        os.killpg(proc.pid, signal.SIGKILL)
                await proc.wait()
        self.processes.clear()
        self.started = None
        if self.updater:
            self.updater.release_session_lease()

    async def stop(self, failure=None):
        async with self.lock:
            self.generation += 1
            self.state = "stopping"
            await self._cleanup()
            self.state = "failed" if failure else "stopped"
            self.error = failure
            self.log(failure or "Session stopped")
        return self.status()

    async def close(self):
        self.panel_closing = True
        await self.stop()
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

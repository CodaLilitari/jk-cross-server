"""Schedule release checks and apply updates only between game sessions."""
from __future__ import annotations

import asyncio
import datetime
import json
import os
from pathlib import Path
import time
from .updater import InstallationBusy


CHECK_INTERVAL = 6 * 60 * 60
DEFAULT_SETTINGS = {"enabled": True, "auto_install": False}


class UpdateController:
    """Keep release management independent of saved game configuration.

    The session manager's lock is held throughout installation. Its installation
    lease also protects sessions belonging to other control-panel processes.
    """

    def __init__(self, manager, updater, *, request_restart=None,
                 check_interval=CHECK_INTERVAL, idle_interval=15):
        self.manager = manager
        self.updater = updater
        self.request_restart = request_restart
        self.settings_path = manager.state_dir / "update-settings.json"
        self.settings = self._load_settings()
        self.check_interval = check_interval
        self.idle_interval = idle_interval
        self.operation = asyncio.Lock()
        self.stopping = asyncio.Event()
        self.wake = asyncio.Event()
        self.task = None
        self.next_check = 0.0
        self.restart_pending = False
        self.last_error = None
        self.auto_attempt = None
        self.auto_retry_at = 0.0
        self.deferred_reason = None

    @staticmethod
    def validate_settings(value):
        if (not isinstance(value, dict) or set(value) != set(DEFAULT_SETTINGS)
                or any(type(value[key]) is not bool for key in DEFAULT_SETTINGS)):
            raise ValueError("Update settings need enabled and auto_install booleans.")
        if value["auto_install"] and not value["enabled"]:
            raise ValueError("Enable automatic checks before automatic installation.")
        return dict(value)

    def _load_settings(self):
        if not self.settings_path.exists():
            return dict(DEFAULT_SETTINGS)
        return self.validate_settings(json.loads(self.settings_path.read_text(encoding="utf-8")))

    async def configure(self, value):
        settings = self.validate_settings(value)
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.settings_path.with_suffix(".json.tmp")
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                os.chmod(temporary, 0o600)
                stream.write(json.dumps(settings, indent=2) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.settings_path)
        finally:
            temporary.unlink(missing_ok=True)
        was_enabled = self.settings["enabled"]
        self.settings = settings
        self.auto_attempt = None
        self.auto_retry_at = 0.0
        if settings["enabled"] and not was_enabled:
            self.next_check = 0
        self.wake.set()
        return self.status()

    def status(self):
        result = dict(self.updater.status())
        result.update(self.settings)
        result["check_interval_hours"] = self.check_interval / 3600
        result["restart_pending"] = self.restart_pending
        result["waiting_for_stop"] = bool(
            self.settings["auto_install"] and result.get("update_available")
            and self.manager.state != "stopped")
        if self.settings["enabled"] and self.next_check:
            delay = max(0, self.next_check - time.monotonic())
            result["next_check_at"] = (
                datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=delay)
            ).isoformat(timespec="seconds")
        else:
            result["next_check_at"] = None
        if self.last_error:
            result["error"] = self.last_error
        result["waiting_for_other_sessions"] = bool(self.deferred_reason)
        if self.deferred_reason:
            result["error"] = None
            result["deferred_reason"] = self.deferred_reason
        return result

    async def check(self):
        async with self.operation:
            if self.restart_pending:
                return self.status()
            self.last_error = None
            try:
                result = await self.updater.check()
                if not result.get("error"):
                    self.auto_attempt = None
                    self.auto_retry_at = 0.0
            except (ValueError, OSError, RuntimeError) as exc:
                self.last_error = str(exc)
                raise
            finally:
                self.next_check = time.monotonic() + self.check_interval
            self.wake.set()
            return self.status()

    def _protected_paths(self):
        paths = [self.manager.config_path, self.manager.state_dir, self.settings_path]
        for name in ("game_data", "mod_dir", "web_client", "wine_prefix", "wine"):
            value = self.manager.config.get(name)
            if value:
                paths.append(Path(value))
        return [Path(path).resolve() for path in paths]

    def _schedule_restart(self):
        self.restart_pending = True
        self.manager.panel_closing = True
        asyncio.get_running_loop().call_later(0.75, self.request_restart)

    async def restart(self):
        async with self.operation:
            async with self.manager.lock:
                if (self.manager.state not in ("stopped", "failed") or
                        any(proc.returncode is None for proc in self.manager.processes.values())):
                    raise ValueError("Stop the game session before restarting the control panel.")
                if self.request_restart is None or self.stopping.is_set():
                    raise ValueError("This control panel cannot restart right now.")
                if not self.restart_pending:
                    self.manager.generation += 1
                    self.manager.intentional_stop = True
                    self._schedule_restart()
                return self.status()

    async def install(self, *, automatic=False):
        async with self.operation:
            async with self.manager.lock:
                if self.stopping.is_set():
                    raise ValueError("The control panel is closing.")
                if self.restart_pending:
                    raise ValueError("The control panel is restarting after an update.")
                allowed = ("stopped",) if automatic else ("stopped", "failed")
                if (self.manager.state not in allowed or
                        any(proc.returncode is None for proc in self.manager.processes.values())):
                    raise ValueError("Stop the game session before installing an update.")
                if self.request_restart is None:
                    raise ValueError("This control panel cannot restart automatically; update from the installed launcher.")
                # A delayed component-failure restart must not race a manual update.
                self.manager.generation += 1
                self.manager.intentional_stop = True
                self.updater.set_protected_paths(self._protected_paths())
                self.last_error = None
                self.deferred_reason = None
                try:
                    await self.updater.install()
                except (ValueError, OSError, RuntimeError) as exc:
                    self.last_error = str(exc)
                    raise
                self.manager.log("Release installed. Restarting the control panel; the game session remains stopped.", "updater")
                # Let the HTTP response reach the browser before its connection closes.
                self._schedule_restart()
                return self.status()

    async def tick(self):
        """One scheduler pass, also usable by deterministic lifecycle tests."""
        if self.stopping.is_set() or self.restart_pending or not self.settings["enabled"]:
            return
        if time.monotonic() >= self.next_check:
            try:
                await self.check()
            except (ValueError, OSError, RuntimeError) as exc:
                self.manager.log("Update check failed: " + str(exc), "updater")
        status = self.status()
        if (self.settings["auto_install"] and status.get("update_available")
                and status.get("install_supported") and not status.get("error")
                and self.manager.state == "stopped"
                and time.monotonic() >= self.auto_retry_at
                and self.auto_attempt != status.get("latest_version")):
            self.auto_attempt = status.get("latest_version")
            try:
                await self.install(automatic=True)
            except InstallationBusy as exc:
                self.auto_attempt = None
                self.auto_retry_at = time.monotonic() + self.idle_interval
                self.deferred_reason = str(exc)
            except (ValueError, OSError, RuntimeError) as exc:
                self.manager.log("Automatic update could not be installed: " + str(exc), "updater")

    def start(self):
        if self.task is None:
            self.task = asyncio.create_task(self._run(), name="release-update-checks")

    async def _run(self):
        while not self.stopping.is_set():
            self.wake.clear()
            await self.tick()
            if self.restart_pending:
                return
            try:
                await asyncio.wait_for(self.wake.wait(), timeout=self.idle_interval)
            except asyncio.TimeoutError:
                pass

    async def close(self):
        self.stopping.set()
        self.wake.set()
        if self.task:
            # Do not cancel a file transaction or its background worker mid-write.
            await self.task
            self.task = None
        async with self.operation:
            pass

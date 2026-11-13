"""Select core and retail display environments independently."""
from __future__ import annotations
import os
import shutil

from .config import ConfigError


def _xvfb(argv, environment, component):
    executable = shutil.which("xvfb-run")
    if not executable:
        raise ConfigError(f"{component} requires xvfb-run. Install Xvfb or configure an existing display.")
    return [executable, "-a", "-s", "-screen 0 640x480x24", *argv], environment


def configure_engine(mode, argv, environment):
    """Return a child argv/env and the selected, observable display backend."""
    argv, env = list(argv), environment.copy()
    if mode not in ("auto", "offscreen", "xvfb", "display"):
        raise ConfigError("engine_display must be auto, offscreen, xvfb or display.")
    if mode == "auto":
        driver = env.get("SDL_VIDEO_DRIVER") or env.get("SDL_VIDEODRIVER")
        if driver:
            return argv, env, "offscreen" if driver == "offscreen" else "display"
        if os.name == "nt" or env.get("DISPLAY") or env.get("WAYLAND_DISPLAY"):
            return argv, env, "display"
        mode = "offscreen"
    if mode == "offscreen":
        env.update(SDL_VIDEO_DRIVER="offscreen", SDL_VIDEODRIVER="offscreen", EGL_PLATFORM="surfaceless")
        return argv, env, "offscreen"
    if mode == "xvfb":
        if os.name == "nt":
            raise ConfigError("The xvfb engine display mode requires a Unix server.")
        env.update(SDL_VIDEO_DRIVER="x11", SDL_VIDEODRIVER="x11", EGL_PLATFORM="x11")
        argv, env = _xvfb(argv, env, "The engine's explicit Xvfb display mode")
        return argv, env, "xvfb"
    if os.name != "nt" and not (env.get("DISPLAY") or env.get("WAYLAND_DISPLAY")):
        raise ConfigError("The display engine mode requires DISPLAY or WAYLAND_DISPLAY.")
    return argv, env, "display"


def configure_retail(argv, environment):
    """Wine needs its own desktop display; core offscreen overrides do not apply."""
    argv, env = list(argv), environment.copy()
    for key in ("SDL_VIDEO_DRIVER", "SDL_VIDEODRIVER"):
        if env.get(key) == "offscreen":
            env.pop(key)
    if env.get("EGL_PLATFORM") == "surfaceless":
        env.pop("EGL_PLATFORM")
    env.pop("OPENJKDF2_SPECTATOR_FD", None)
    if os.name != "nt" and not env.get("DISPLAY"):
        argv, env = _xvfb(argv, env, "Retail/Wine hosting without DISPLAY")
    return argv, env

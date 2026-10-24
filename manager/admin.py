"""Loopback control panel. Game listeners live in separate adapters."""
from __future__ import annotations

import asyncio
import hmac
import ipaddress
from pathlib import Path
import secrets
from urllib.parse import urlsplit

from aiohttp import web
from . import config as conf
from .content import catalog, preflight

UI = Path(__file__).with_name("ui")


def create_admin_app(manager, *, port: int | None = 8765, token: str | None = None) -> web.Application:
    token = token or secrets.token_urlsafe(32)

    @web.middleware
    async def guard(request, handler):
        try:
            host = urlsplit("//" + request.host)
            valid_host = host.hostname in ("127.0.0.1", "localhost", "::1") and (port is None or host.port == port)
        except ValueError:
            valid_host = False
        remote = request.transport.get_extra_info("peername") if request.transport else None
        try:
            loopback = bool(remote and ipaddress.ip_address(remote[0]).is_loopback)
        except ValueError:
            loopback = False
        origin = request.headers.get("Origin")
        if (not valid_host or not loopback or
                (origin and origin != f"{request.scheme}://{request.host}") or
                request.headers.get("Sec-Fetch-Site") == "cross-site"):
            return web.json_response({"error": "The control panel accepts local, same-origin requests only."}, status=403)
        if request.path.startswith("/api/"):
            authorization = request.headers.get("Authorization", "")
            if not authorization.startswith("Bearer ") or not hmac.compare_digest(authorization[7:], token):
                return web.json_response({"error": "Control panel authentication required."}, status=401)
        try:
            response = await handler(request)
        except (conf.ConfigError, ValueError, OSError) as exc:
            response = web.json_response({"error": str(exc)}, status=400)
        except (RuntimeError, ConnectionError, TimeoutError) as exc:
            response = web.json_response({"error": str(exc) or type(exc).__name__}, status=500)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        return response

    async def index(request):
        markup = (UI / "index.html").read_text(encoding="utf-8")
        return web.Response(text=markup.replace("__ADMIN_TOKEN__", token), content_type="text/html")

    async def asset(request):
        name = request.match_info["name"]
        if name not in ("app.js", "style.css"):
            raise web.HTTPNotFound()
        return web.FileResponse(UI / name)

    async def get_config(request):
        return web.json_response(manager.config)

    async def put_config(request):
        return web.json_response(await manager.update_config(await request.json()))

    async def get_status(request):
        return web.json_response(manager.status())

    async def supplied_config(request):
        body = await request.json() if request.can_read_body else {}
        if not isinstance(body, dict):
            raise conf.ConfigError("Expected a JSON object.")
        return conf.validate(body.get("config", manager.config))

    async def get_catalog(request):
        value = await supplied_config(request)
        if not value["game_data"]:
            raise conf.ConfigError("Enter a game data folder first.")
        return web.json_response(await asyncio.to_thread(catalog, Path(value["game_data"])))

    async def run_preflight(request):
        value = conf.validate(await supplied_config(request), require_paths=True)
        return web.json_response(await asyncio.to_thread(preflight, value))

    async def start(request):
        return web.json_response(await manager.start())

    async def stop(request):
        return web.json_response(await manager.stop())

    app = web.Application(middlewares=[guard], client_max_size=128 * 1024)
    app.router.add_get("/", index)
    app.router.add_get("/ui/{name}", asset)
    app.router.add_get("/api/config", get_config)
    app.router.add_put("/api/config", put_config)
    app.router.add_get("/api/status", get_status)
    app.router.add_post("/api/catalog", get_catalog)
    app.router.add_post("/api/preflight", run_preflight)
    app.router.add_post("/api/start", start)
    app.router.add_post("/api/stop", stop)
    return app

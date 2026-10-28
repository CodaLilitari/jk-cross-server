"""Loopback control panel. Game listeners live in separate adapters."""
from __future__ import annotations

import asyncio
import hmac
import io
import ipaddress
from pathlib import Path
import secrets
from urllib.parse import urlsplit
import zipfile

from aiohttp import web
from . import config as conf
from .content import catalog, preflight
from .spectator import SpectatorError

UI = Path(__file__).with_name("ui")
OFFLINE_TOOLS = Path(__file__).resolve().parents[1] / "tools"


def create_admin_app(manager, *, port: int | None = 8765, token: str | None = None, updates=None) -> web.Application:
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
        except SpectatorError as exc:
            response = web.json_response({"error": str(exc)}, status=exc.status)
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
        if name not in ("app.js", "style.css", "spectator.js"):
            raise web.HTTPNotFound()
        return web.FileResponse(UI / name)

    async def get_config(request):
        return web.json_response(manager.config)

    async def put_config(request):
        return web.json_response(await manager.update_config(await request.json()))

    async def put_bot_behavior(request):
        return web.json_response(await manager.update_bot_behavior(await request.json()))

    async def get_bot_profiles(request):
        from bots.run import load_profiles
        return web.json_response([{"id": ident, "name": row["name"], "model": row["model"]}
                                  for ident, row in load_profiles().items()])

    async def get_status(request):
        result = manager.status()
        if updates:
            result["updates"] = updates.status()
        return web.json_response(result)

    async def get_spectator(request):
        return web.json_response(await manager.spectator_status())

    async def put_spectator(request):
        return web.json_response(await manager.configure_spectator(await request.json()))

    async def put_spectator_input(request):
        return web.json_response(await manager.spectator_input(await request.json()))

    async def get_spectator_frame(request):
        if (set(request.query) - {"after", "world_epoch", "control_epoch"} or
                len(request.query) != len(set(request.query))):
            raise ValueError("Frame fetch accepts after and optional world/control epochs only.")
        query = {}
        for key, text in request.query.items():
            if not text.isascii() or not text.isdecimal() or len(text) > 10:
                raise ValueError("Frame counters must be uint32 integers.")
            query[key] = int(text)
        frame = manager.spectator_frame(**query)
        if frame is None:
            return web.Response(status=204)
        return web.Response(body=frame["pixels"], content_type="application/octet-stream", headers={
            "X-JK-Frame-Width": str(frame["width"]), "X-JK-Frame-Height": str(frame["height"]),
            "X-JK-Frame-Sequence": str(frame["sequence"]),
            "X-JK-World-Epoch": str(frame["world_epoch"]),
            "X-JK-Control-Epoch": str(frame["control_epoch"]), "X-JK-Pixel-Format": "RGBA8"})

    def authority_store():
        store = getattr(manager, "authority_store", None)
        if store is None:
            raise RuntimeError("Persistent admin authority is unavailable.")
        return store

    async def get_admin_keys(request):
        return web.json_response(authority_store().metadata())

    def credential_download(issued):
        # The body is delivered once as a download; it never enters status,
        # game configuration, a run directory, a URL or a panel log message.
        return web.Response(body=issued["credential"].encode("ascii"),
                            content_type="application/octet-stream", headers={
                                "Content-Disposition": f'attachment; filename="{issued["filename"]}"',
                                "Pragma": "no-cache",
                            })

    async def issue_admin_key(request):
        body = await request.json()
        if not isinstance(body, dict) or set(body) != {"label", "capabilities"}:
            raise ValueError("Issuance accepts only label and capabilities.")
        issued = authority_store().issue(body["label"], body["capabilities"])
        return credential_download(issued)

    async def empty_key_action(request):
        if await request.read():
            raise ValueError("This key action does not accept a request body.")

    async def revoke_admin_key(request):
        await empty_key_action(request)
        return web.json_response(authority_store().revoke(request.match_info["key_id"]))

    async def rotate_admin_key(request):
        await empty_key_action(request)
        return credential_download(authority_store().rotate(request.match_info["key_id"]))

    async def offline_admin_helper(request):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for name in ("admin-helper.html", "admin-helper.js", "admin-helper.css"):
                bundle.writestr(name, (OFFLINE_TOOLS / name).read_bytes())
        return web.Response(body=output.getvalue(), content_type="application/zip", headers={
            "Content-Disposition": 'attachment; filename="jk-admin-offline-helper.zip"',
        })

    async def offline_admin_cli(request):
        return web.Response(body=(OFFLINE_TOOLS / "admin_key.py").read_bytes(),
                            content_type="application/octet-stream", headers={
                                "Content-Disposition": 'attachment; filename="admin_key.py"',
                            })

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

    async def update_status(request):
        return web.json_response(updates.status())

    async def update_settings(request):
        return web.json_response(await updates.configure(await request.json()))

    async def check_updates(request):
        return web.json_response(await updates.check())

    async def install_update(request):
        return web.json_response(await updates.install())

    async def restart_panel(request):
        return web.json_response(await updates.restart())

    app = web.Application(middlewares=[guard], client_max_size=128 * 1024)
    app.router.add_get("/", index)
    app.router.add_get("/ui/{name}", asset)
    app.router.add_get("/admin-helper.zip", offline_admin_helper)
    app.router.add_get("/admin-helper.py", offline_admin_cli)
    app.router.add_get("/api/config", get_config)
    app.router.add_put("/api/config", put_config)
    app.router.add_put("/api/bots/behavior", put_bot_behavior)
    app.router.add_get("/api/bots/profiles", get_bot_profiles)
    app.router.add_get("/api/status", get_status)
    app.router.add_get("/api/spectator", get_spectator)
    app.router.add_put("/api/spectator", put_spectator)
    app.router.add_put("/api/spectator/input", put_spectator_input)
    app.router.add_get("/api/spectator/frame", get_spectator_frame)
    app.router.add_get("/api/admin-keys", get_admin_keys)
    app.router.add_post("/api/admin-keys", issue_admin_key)
    app.router.add_post("/api/admin-keys/{key_id}/revoke", revoke_admin_key)
    app.router.add_post("/api/admin-keys/{key_id}/rotate", rotate_admin_key)
    app.router.add_post("/api/catalog", get_catalog)
    app.router.add_post("/api/preflight", run_preflight)
    app.router.add_post("/api/start", start)
    app.router.add_post("/api/stop", stop)
    if updates:
        app.router.add_get("/api/updates", update_status)
        app.router.add_put("/api/updates/settings", update_settings)
        app.router.add_post("/api/updates/check", check_updates)
        app.router.add_post("/api/updates/install", install_update)
        app.router.add_post("/api/updates/restart", restart_panel)
    return app

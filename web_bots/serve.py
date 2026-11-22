"""Private four-seat JKWeb arena: same-origin relay, WASM files and companion exchange."""
from __future__ import annotations

import argparse
import asyncio
import base64
import binascii
import contextlib
import hmac
import http.server
import json
import os
from pathlib import Path
import re
import runpy
import secrets
import signal
import socket
import struct
import sys
import threading
import time

from aiohttp import ClientSession, ClientTimeout, WSMsgType, web
from bots.companion import ACK, HEADER, Hub, create_private_directory

HERE = Path(__file__).resolve().parent
ASSETS = ("resource/Res1hi.gob", "resource/Res2.gob", "resource/jk_.cd", "episode/JK1MP.gob")
ARENA_MODES = ("ff-guns", "ff-sabers", "nf-guns", "nf-sabers")
SEATS = {
    "lily": ("Darth_Lilitari", "ky.3do", "ky.snd", "dark"),
    "boba": ("Bot_BobaFett", "kyh4.3do", "kybobafett.snd", "dark"),
    "jan": ("Bot_JanOrs", "kya10.3do", "kyfemale.snd", "light"),
    "yun": ("Bot_Yun", "kya18.3do", "kyyun.snd", "light"),
}
MAX_CHUNK, MAX_CAPTURE = 8*1024*1024, 512*1024*1024
CAPTURE_IDLE_SECONDS = 10.


def private_json(path, data):
    with os.fdopen(os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def game_file(root, relative):
    path = Path(root).resolve()
    for part in relative.split("/"):
        hits = [p for p in path.iterdir() if p.name.casefold() == part.casefold()]
        if len(hits) != 1:
            raise ValueError(f"Expected one installed {relative}.")
        path = hits[0]
    if not path.is_file():
        raise ValueError(f"Expected a game file for {relative}.")
    return path


def browser_pair():
    # AF_UNIX datagrams are unavailable on native Windows. Connected local UDP
    # endpoints preserve atomic record boundaries and filter unrelated peers.
    if os.name != "nt":
        return socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
    a = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        b = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            a.bind(("127.0.0.1",0))
            b.bind(("127.0.0.1",0))
            a.connect(b.getsockname())
            b.connect(a.getsockname())
            return a,b
        except BaseException:
            b.close()
            raise
    except BaseException:
        a.close()
        raise


def child_relay(path):
    # Import the pinned author's relay unchanged; restrict its HTTP handler to
    # the socket upgrade so even its private listener has no file-serving root.
    bootstrap = sys.stdin.buffer.readline(66)
    if not re.fullmatch(rb"[0-9a-f]{64}\n", bootstrap):
        raise RuntimeError("Private relay requires its supervisor bootstrap.")
    proxy_proof = bootstrap[:-1].decode("ascii")
    m = runpy.run_path(str(path))
    class RelayOnly(m["Handler"]):
        def do_GET(self):
            if self.path.partition("?")[0] != "/relay" or self.headers.get("Upgrade","").lower() != "websocket":
                self.send_error(404)
                return
            proof = self.headers.get_all("X-JK-Relay-Proof", [])
            if len(proof) != 1 or not proof[0].isascii() or not hmac.compare_digest(proof[0], proxy_proof):
                self.send_error(403)
                return
            self.handle_websocket()

        def do_POST(self):
            self.send_error(404)

        def log_message(self, *args):
            pass

    RelayOnly.ice = m["IceConfig"]([], [], None, None, None, 3600)
    RelayOnly.relay = m["Relay"](m["HOLD_S"], RelayOnly.ice, "host", None)
    with http.server.ThreadingHTTPServer(("127.0.0.1",0), RelayOnly) as server:
        def stop_with_parent():
            sys.stdin.buffer.read(1)
            server.shutdown()
        threading.Thread(target=stop_with_parent, daemon=True).start()
        print(server.server_port, flush=True)
        server.serve_forever()


class Host:
    def __init__(self, data, engine, runtime, room, model, chat, mode="ff-guns"):
        if mode not in ARENA_MODES:
            raise ValueError("Unknown arena mode. Choose one of " + ", ".join(ARENA_MODES) + ".")
        self.mode = mode
        if not isinstance(room,str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,31}",room) or room != room.strip():
            raise ValueError("Room must be 1..31 ASCII letters, digits, underscores or hyphens.")
        self.room, self.engine, self.runtime = room, Path(engine), Path(runtime)
        self.assets = [("/jk1/"+name, game_file(data,name)) for name in ASSETS]
        self.model = model is not None
        if model:
            if not Path(model).is_file() or Path(model).suffix.lower() != ".gob":
                raise ValueError("Supply a regular model GOB.")
            self.assets.append(("/jk1/jkmods/companion/lilitari.gob",Path(model).resolve()))
        for name in ("openjkdf2.js","openjkdf2.wasm"):
            if not (self.engine/name).is_file():
                raise ValueError("Supply the current bot-enabled JS/WASM engine directory.")
        create_private_directory(self.runtime, parents=True)
        self.secrets_dir = self.runtime/"engines"
        create_private_directory(self.secrets_dir)
        self.hub = Hub(self.runtime, SEATS, 0, allow_chat=chat, channel_factory=browser_pair)
        self.tokens = {ident: secrets.token_urlsafe(32) for ident in SEATS}
        self.channels = {ident:self.hub.open_browser_channel(ident) for ident in SEATS}
        self.seats = {ident: {"instance":None,"cookie":None,"poll":0., "seq_base":0,"world_base":0,
                              "graphics":None, "view":None, "stage":"waiting", "dropped":0} for ident in SEATS}
        self.proxy_proof = secrets.token_hex(32)
        self.port = self.relay_port = self.http = None
        self.capture = None

    def set_port(self, port):
        self.port = port
        self.url = f"http://127.0.0.1:{port}"
        for ident,token in self.tokens.items():
            private_json(self.secrets_dir/(ident+".json"),{"version":1,"id":ident,"url":self.url,"token":token})
        private_json(self.runtime/"run.json", {"url":self.url,"status":self.url+"/status","room":self.room,"mode":self.mode,
            "pages":{i:self.url+"/bot/"+i for i in SEATS}, "companion":self.hub.url,
            "engine_credentials":"engines","companion_credentials":"companion"})

    def close(self):
        for channel in self.channels.values():
            channel.close()
        self.hub.close()
        for ident in self.tokens:
            (self.secrets_dir/(ident+".json")).unlink(missing_ok=True)
        if self.capture and self.capture["file"]:
            self.capture["file"].close()
            self.capture["file"] = None

    def abort_capture(self, reason):
        if self.capture and self.capture["file"] is not None:
            self.capture["file"].close()
            self.capture.update(file=None, status="aborted", reason=reason)

    def expire_capture(self):
        if (self.capture and self.capture["file"] is not None and
                time.monotonic()-self.capture["last_chunk_mono"] >= CAPTURE_IDLE_SECONDS):
            # Keep the incomplete file for inspection, but release the handle
            # and capture slot after a crashed or disconnected recorder.
            self.abort_capture("Recording stopped sending chunks.")

    def app(self):
        @web.middleware
        async def guard(request,handler):
            peer = request.transport.get_extra_info("peername") if request.transport else None
            if (not peer or peer[0] != "127.0.0.1" or not self.port or
                    request.headers.getall("Host",[]) != [f"127.0.0.1:{self.port}"] or
                    request.headers.getall("Origin",[]) not in ([],[self.url]) or
                    request.headers.get("Sec-Fetch-Site") == "cross-site"):
                raise web.HTTPForbidden()
            if request.path.startswith("/engine/"):
                ident = request.match_info.get("ident")
                target = self.tokens.get(ident)
                auth = request.headers.getall("Authorization",[])
                if not target or len(auth) != 1 or not auth[0].isascii() or not hmac.compare_digest(auth[0],"Bearer "+target):
                    raise web.HTTPUnauthorized()
            response = await handler(request)
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = "no-referrer"
            return response

        app = web.Application(middlewares=[guard],client_max_size=MAX_CHUNK)
        app.router.add_get("/status",self.status)
        app.router.add_get("/bot/{ident}",self.page)
        app.router.add_get("/client.js",self.javascript)
        app.router.add_get("/wasm/{name}",self.wasm)
        app.router.add_post("/engine/{ident}/boot",self.boot)
        app.router.add_get("/engine/{ident}/assets/{idx}",self.asset)
        app.router.add_post("/engine/{ident}/frames",self.frames)
        app.router.add_post("/engine/{ident}/capture/{step}",self.record)
        app.router.add_get("/relay",self.relay)
        return app

    async def page(self, request):
        if request.match_info["ident"] not in SEATS:
            raise web.HTTPNotFound()
        return web.FileResponse(HERE/"index.html",headers={"Content-Security-Policy":
            "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'unsafe-inline'; "
            "worker-src 'self' blob:; connect-src 'self' ws://127.0.0.1:"+str(self.port)+"; frame-ancestors 'none'; base-uri 'none'"})

    async def javascript(self, request):
        return web.FileResponse(HERE/"client.js",headers={"Content-Type":"text/javascript"})

    async def wasm(self, request):
        name=request.match_info["name"]
        if name not in ("openjkdf2.js","openjkdf2.wasm"):
            raise web.HTTPNotFound()
        return web.FileResponse(self.engine/name,headers={"Content-Type":"application/wasm" if name.endswith("wasm") else "text/javascript"})

    @staticmethod
    async def body(request):
        if request.content_type != "application/json" or request.content_length is None or request.content_length > 35000:
            raise web.HTTPBadRequest(text="Expected a bounded JSON request.")
        try:
            data=await request.json()
        except (UnicodeError,ValueError,RecursionError):
            raise web.HTTPBadRequest(text="Malformed JSON.")
        if type(data) is not dict:
            raise web.HTTPBadRequest()
        return data

    async def boot(self, request):
        ident = request.match_info["ident"]
        body = await self.body(request)
        if set(body) != {"instance"} or not isinstance(body["instance"],str) or not re.fullmatch("[0-9a-f]{32}",body["instance"]):
            raise web.HTTPBadRequest()
        seat = self.seats[ident]
        if seat["instance"] != body["instance"]:
            if seat["instance"] and time.monotonic()-seat["poll"] < 8:
                raise web.HTTPConflict(text="This seat already has a live browser engine.")
            if ident == "lily" and seat["instance"]:
                self.abort_capture("Recording browser restarted.")
            # Make frames from a restarted WASM instance advance monotonically
            # across its reset. The hub's first new state invalidates old leases.
            self.hub.pump()
            with self.hub.lock:
                bot = self.hub.bots[ident]
                seat.update(world_base=bot.world,seq_base=bot.event_seq)
            self.channels[ident].outgoing_frames()
            seat.update(instance=body["instance"],cookie=secrets.token_urlsafe(24),stage="boot",graphics=None,view=None)
        seat["poll"] = time.monotonic()
        name,model,sound,side = SEATS[ident]
        if ident == "lily" and self.model:
            model,sound="dlil.3do","dlil.snd"
        response = web.json_response({"id":ident,"assets":[{"path":path,"url":f"/engine/{ident}/assets/{n}"} for n,(path,_) in enumerate(self.assets)],
            "mod":self.model,"env":{"JK_BOT_WEB_ROLE":"host" if ident=="lily" else "join","JK_BOT_WEB_ROOM":self.room,"JK_BOT_WEB_MODE":self.mode,
                "JK_BOT_WEB_NAME":name,"JK_BOT_WEB_MODEL":model,"JK_BOT_WEB_SOUND":sound,
                "JK_BOT_WEB_SABER_COLOR":"red" if ident=="lily" else "green",
                "JK_BOT_TRACE_FORCE":"1" if os.environ.get("JK_BOT_TRACE_FORCE")=="1" else "0",
                "JK_BOT_FORCE_SIDE":side,"JK_BOT_FORCE_STYLE":"competitive","JK_BOT_WEB_THIRD_PERSON":"1" if ident=="lily" else "0"}})
        response.set_cookie("jkrelay_"+ident,seat["cookie"],httponly=True,samesite="Strict",path="/relay")
        return response

    async def asset(self, request):
        idx=request.match_info["idx"]
        if not re.fullmatch(r"[0-9]{1,2}",idx) or int(idx)>=len(self.assets):
            raise web.HTTPNotFound()
        return web.FileResponse(self.assets[int(idx)][1],headers={"Content-Type":"application/octet-stream"})

    def session(self,ident,instance):
        seat=self.seats[ident]
        if not instance or instance != seat["instance"]:
            raise web.HTTPConflict(text="Browser engine session expired.")
        return seat

    async def frames(self, request):
        ident=request.match_info["ident"]
        msg=await self.body(request)
        if set(msg)-{"instance","frames","graphics","stage","dropped","view"} or not {"instance","frames"}<=msg.keys():
            raise web.HTTPBadRequest()
        seat=self.session(ident,msg["instance"])
        if not isinstance(msg["frames"],list) or len(msg["frames"])>32:
            raise web.HTTPBadRequest()
        frames=[]
        for text in msg["frames"]:
            if not isinstance(text,str) or len(text)>684:
                raise web.HTTPBadRequest()
            try:
                frame=bytearray(base64.b64decode(text,validate=True))
            except (ValueError,binascii.Error):
                raise web.HTTPBadRequest()
            if not HEADER.size<=len(frame)<=512:
                raise web.HTTPBadRequest()
            magic,ver,kind,length,world,life,seq=HEADER.unpack_from(frame)
            if magic!=b"JKCP" or ver!=1 or kind not in (1,2,3,4) or length!=len(frame)-20:
                raise web.HTTPBadRequest()
            struct.pack_into("<I",frame,8,(world+seat["world_base"])&0xffffffff)
            if kind!=ACK:
                struct.pack_into("<I",frame,16,(seq+seat["seq_base"])&0xffffffff)
            frames.append(bytes(frame))
        if "graphics" in msg:
            info=msg["graphics"]
            if (not isinstance(info,dict) or set(info)!={"vendor","renderer","width","height"} or
                any(type(info[k]) is not str or len(info[k])>256 for k in ("vendor","renderer")) or
                any(type(info[k]) is not int or not 0<=info[k]<=16384 for k in ("width","height"))):
                raise web.HTTPBadRequest()
            seat["graphics"]=info
        if "view" in msg:
            view=msg["view"]
            if (type(view) is not dict or set(view)!={"flags","model"} or type(view["flags"]) is not int
                    or not 0<=view["flags"]<=15 or type(view["model"]) is not str or len(view["model"])>96):
                raise web.HTTPBadRequest()
            seat["view"]=view
        stage=msg.get("stage","running")
        if stage not in ("assets","startup","running","failed"):
            raise web.HTTPBadRequest()
        dropped=msg.get("dropped",seat["dropped"])
        if type(dropped) is not int or not 0<=dropped<=2**32-1:
            raise web.HTTPBadRequest()
        seat.update(stage=stage,poll=time.monotonic(),dropped=dropped)
        for frame in frames:
            self.channels[ident].enqueue_native_frame(frame)
        self.hub.pump()
        result=[]
        for frame in self.channels[ident].outgoing_frames():
            raw=bytearray(frame)
            world=struct.unpack_from("<I",raw,8)[0]
            if world<=seat["world_base"]:
                continue
            struct.pack_into("<I",raw,8,world-seat["world_base"])
            result.append(base64.b64encode(raw).decode())
        return web.json_response({"frames":result,"server_mono":self.hub.clock()})

    async def status(self, request):
        self.expire_capture()
        self.hub.pump()
        seats={}
        now=time.monotonic()
        with self.hub.lock:
            for ident,seat in self.seats.items():
                b=self.hub.bots[ident]
                active=bool(b.state and now-b.observed<=3 and b.world>seat["world_base"])
                seats[ident]={"joined":active,"world_epoch":b.world,"life_epoch":b.life,
                    "self":None if not active else {k:b.state[k] for k in ("slot","net_id","position","health","kills","deaths","mode")},
                    "graphics":seat["graphics"],"view":seat["view"],"stage":seat["stage"],"browser_dropped":seat["dropped"]}
        capture={k:v for k,v in self.capture.items() if k not in ("file","capture_id","instance")} if self.capture else None
        return web.json_response({"room":self.room,"mode":self.mode,"joined_count":sum(v["joined"] for v in seats.values()),
                                  "custom_model":self.model,"seats":seats,"capture":capture})

    async def record(self, request):
        ident=request.match_info["ident"]
        if ident!="lily":
            raise web.HTTPForbidden()
        instance=request.headers.get("X-Engine-Instance","")
        self.session(ident,instance)
        self.expire_capture()
        step=request.match_info["step"]
        if step=="start":
            meta=await self.body(request)
            if (set(meta)!={"mime","audio_tracks","width","height"} or type(meta["mime"]) is not str or
                not meta["mime"].startswith("video/webm") or len(meta["mime"])>128 or
                any(type(meta[k]) is not int for k in ("audio_tracks","width","height")) or
                not 0<=meta["audio_tracks"]<=2 or not all(1<=meta[k]<=8192 for k in ("width","height"))):
                raise web.HTTPBadRequest()
            self.session(ident,instance)
            self.expire_capture()
            if self.capture and self.capture["file"] is not None:
                raise web.HTTPConflict(text="A recording is in progress.")
            key=secrets.token_hex(12)
            path=self.runtime/("canyon-"+key+".webm.part")
            now=time.monotonic()
            self.capture={**meta,"capture_id":key,"instance":instance,"bytes":0,"chunks":0,"status":"recording",
                          "started_mono":now,"last_chunk_mono":now,
                          "file":os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),"wb")}
            return web.json_response({"capture_id":key})
        cap=self.capture
        if not cap or not cap["file"] or request.headers.get("X-Capture-ID")!=cap["capture_id"] or instance!=cap["instance"]:
            raise web.HTTPConflict(text="No matching recording.")
        key=cap["capture_id"]
        if step=="chunk":
            if (request.content_length is None or not 0<request.content_length<=MAX_CHUNK or
                    cap["bytes"]+request.content_length>MAX_CAPTURE):
                raise web.HTTPRequestEntityTooLarge(max_size=MAX_CHUNK,actual_size=request.content_length or 0)
            if request.headers.get("X-Chunk-Index")!=str(cap["chunks"]):
                raise web.HTTPConflict(text="Recording chunk is out of sequence.")
            data=await request.read()
            if cap is not self.capture or not cap["file"] or request.headers.get("X-Chunk-Index")!=str(cap["chunks"]):
                raise web.HTTPConflict()
            if cap["chunks"] == 0 and not data.startswith(b"\x1a\x45\xdf\xa3"):
                raise web.HTTPBadRequest(text="First recording chunk is missing its WebM header.")
            cap["file"].write(data)
            cap["chunks"]+=1
            cap["bytes"]+=len(data)
            cap["last_chunk_mono"]=time.monotonic()
        elif step=="finish":
            meta=await self.body(request)
            if cap is not self.capture or not cap["file"]:
                raise web.HTTPConflict(text="Recording changed while finishing.")
            if (set(meta)!={"chunks","duration_seconds"} or type(meta["chunks"]) is not int or
                    meta["chunks"]!=cap["chunks"] or not cap["bytes"] or
                    type(meta["duration_seconds"]) not in (float,int) or not 0<meta["duration_seconds"]<=360):
                raise web.HTTPBadRequest()
            cap["file"].close()
            cap["file"]=None
            path=self.runtime/("canyon-"+key+".webm")
            (self.runtime/(path.name+".part")).rename(path)
            cap.update(status="saved",filename=path.name,duration_seconds=meta["duration_seconds"])
        elif step=="abort":
            self.abort_capture("Recording browser aborted.")
        else:
            raise web.HTTPNotFound()
        return web.json_response({"chunks":cap["chunks"],"bytes":cap["bytes"],"status":cap["status"]})

    async def relay(self,request):
        if not any(s["cookie"] and hmac.compare_digest(request.cookies.get("jkrelay_"+ident,""),s["cookie"])
                   for ident,s in self.seats.items()):
            raise web.HTTPForbidden()
        if not self.relay_port or self.http is None:
            raise web.HTTPServiceUnavailable()
        ws=web.WebSocketResponse(max_msg_size=65536)
        suffix=request.rel_url.query_string
        url=f"http://127.0.0.1:{self.relay_port}/relay"+("?"+suffix if suffix else "")
        async with self.http.ws_connect(url, max_msg_size=65536, compress=0,
                                        headers={"X-JK-Relay-Proof":self.proxy_proof}) as upstream:
            await ws.prepare(request)
            async def forward(source,dest):
                async for message in source:
                    if message.type==WSMsgType.TEXT:
                        await dest.send_str(message.data)
                    elif message.type==WSMsgType.BINARY:
                        await dest.send_bytes(message.data)
                    else:
                        break
            tasks=[asyncio.create_task(forward(ws,upstream)),asyncio.create_task(forward(upstream,ws))]
            try:
                await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks,return_exceptions=True)
                await ws.close()
        return ws


def relay_ready_port(line):
    """Decode the relay's complete ASCII port line on Unix or Windows."""
    if not re.fullmatch(rb"[0-9]{1,5}\r?\n", line):
        raise ValueError("Missing or malformed relay port.")
    port = int(line)
    if not 1 <= port <= 65535:
        raise ValueError("Relay port outside 1..65535.")
    return port


async def serve(args):
    run=Path(args.runtime)/("arena-"+time.strftime("%Y%m%d-%H%M%S")+"-"+secrets.token_hex(4))
    host=Host(args.data,args.engine_dir,run,args.room,args.model_gob,args.companion_chat,mode=args.mode)
    runner=web.AppRunner(host.app(),access_log=None,shutdown_timeout=1.)
    proc=drain=None
    try:
        if not args.relay_script.is_file():
            raise ValueError("Supply relay/relay.py from the current pinned JKWeb relay repository.")
        relay_log = run / "relay.stderr.log"
        log_fd = os.open(relay_log, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(log_fd, "wb") as errors:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-u", "-m", "web_bots.serve", "--relay-child",
                str(args.relay_script.resolve()), stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=errors)
        try:
            proc.stdin.write(host.proxy_proof.encode("ascii") + b"\n")
            await proc.stdin.drain()
            line = await asyncio.wait_for(proc.stdout.readline(), 10)
            host.relay_port = relay_ready_port(line)
        except (OSError, ValueError, TimeoutError) as error:
            raise RuntimeError(f"Private upstream relay did not report a valid port. See {relay_log}.") from error
        async def discard():
            while await proc.stdout.read(8192):
                pass
        drain=asyncio.create_task(discard())
        # Bound the local relay's TCP/HTTP upgrade. A live WebSocket's receive
        # lifetime remains unlimited; this is not a match-duration timeout.
        async with ClientSession(timeout=ClientTimeout(total=None,connect=5,sock_connect=5,sock_read=5)) as session:
            host.http=session
            await runner.setup()
            site=web.TCPSite(runner,"127.0.0.1",args.port)
            await site.start()
            host.set_port(runner.addresses[0][1])
            print(json.dumps({"runtime":str(run.resolve()),"url":host.url,"pages":list(SEATS),"room":host.room,"mode":host.mode}),flush=True)
            while proc.returncode is None:
                host.hub.pump()
                host.expire_capture()
                await asyncio.sleep(.05)
            raise RuntimeError(f"Private relay exited with {proc.returncode}.")
    finally:
        await runner.cleanup()
        if proc and proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(),3)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
        if drain:
            drain.cancel()
            await asyncio.gather(drain,return_exceptions=True)
        host.close()


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--relay-child",type=Path,help=argparse.SUPPRESS)
    p.add_argument("--data",type=Path)
    p.add_argument("--engine-dir",type=Path,default=HERE.parent/"bin"/"bots-jkweb")
    p.add_argument("--relay-script",type=Path)
    p.add_argument("--runtime",type=Path,default=HERE.parent/"runtime"/"web-bots")
    p.add_argument("--model-gob",type=Path)
    p.add_argument("--port",type=int,default=0)
    p.add_argument("--mode", choices=ARENA_MODES, default="ff-guns", help="Force profile and bot weapon policy on Canyon Oasis.")
    p.add_argument("--room",default="Canyon_"+secrets.token_hex(4))
    p.add_argument("--companion-chat",action="store_true")
    args=p.parse_args(argv)
    if args.relay_child:
        child_relay(args.relay_child)
        return
    if args.data is None or args.relay_script is None or not 0<=args.port<=65535:
        p.error("Supply --data, --relay-script and a valid port.")
    async def run():
        loop=asyncio.get_running_loop()
        task=asyncio.current_task()
        for sig in (signal.SIGINT,signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig,task.cancel)
        await serve(args)
    try:
        asyncio.run(run())
    except (KeyboardInterrupt,asyncio.CancelledError):
        pass


if __name__=="__main__":
    main()

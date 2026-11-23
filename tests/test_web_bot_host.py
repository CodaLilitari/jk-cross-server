import asyncio
import base64
from contextlib import asynccontextmanager
import sys
import json
import os
import subprocess
import struct
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from aiohttp import ClientSession
from aiohttp.test_utils import TestClient, TestServer
from web_bots import serve
from bots import companion as cp
from bots import companion_cli as cli


class RelayReadyTests(unittest.TestCase):
    def test_windows_and_unix_relay_port_lines(self):
        for line, expected in ((b"12345\r\n",12345),(b"65535\n",65535),(b"1\n",1)):
            with self.subTest(line=line):
                self.assertEqual(serve.relay_ready_port(line),expected)
        for line in (b"",b"0\n",b"65536\r\n",b"123456\n",b"-1\n",b" 42\n",b"42 \n",
                     b"42\r",b"42",b"42\r\r\n",b"42\nextra",b"port 42\n"):
            with self.subTest(line=line), self.assertRaises(ValueError):
                serve.relay_ready_port(line)


class HostTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for filename in serve.ASSETS:
            f = self.root / "game" / filename
            f.parent.mkdir(exist_ok=True,parents=True)
            f.write_bytes(b"fixture")
        engine = self.root/"engine"
        engine.mkdir()
        (engine/"openjkdf2.js").write_text("")
        (engine/"openjkdf2.wasm").write_bytes(b"x")
        self.host = serve.Host(self.root/"game", engine, self.root/"run", "My_Room", None, False)
        self.server = TestServer(self.host.app(), host="127.0.0.1")
        self.client = TestClient(self.server)
        await self.client.start_server()
        self.host.set_port(self.server.port)
        self.addAsyncCleanup(self.client.close)
        self.addCleanup(self.host.close)
        self.auth = {"Authorization":"Bearer "+self.host.tokens["lily"]}

    @unittest.skipUnless(os.name == "nt", "Windows token SID and filesystem DACL")
    async def test_generated_windows_credentials_and_lease(self):
        # Each depth receives a file through its ordinary production path.
        self.assertEqual(cli.load_private(self.host.runtime / "run.json")["room"], "My_Room")
        self.assertEqual(cli.load_private(self.host.secrets_dir / "lily.json")["id"], "lily")
        credential = self.host.hub.directory / "lily.json"
        self.assertEqual(cli.load_private(credential)["bot_id"], "lily")
        await self.boot()
        state = bytearray(144)
        struct.pack_into("<4I", state, 0, 1, 42, 88, 13)
        struct.pack_into("<iII", state, 60, -1, 4, 0xffffffff)
        self.assertEqual((await self.exchange([cp.frame(cp.STATE,1,1,1,state)])).status, 200)

        def command(*args):
            return cli.execute(cli.parser().parse_args(["--credentials", str(credential), *args]))

        self.assertEqual(command("observe")["state"]["net_id"], 42)
        lease = Path(command("attach", "test")["lease_file"])
        self.assertEqual(cli.load_private(lease)["run_id"], self.host.hub.run_id)
        self.assertEqual(command("renew")["expires_in"], 30)
        command("release", "--wait", "0")
        self.assertFalse(lease.exists())

        # A separate synthetic marker contains no credential or lease.
        marker = self.host.hub.directory / "test-acl.json"
        marker.write_text("{}", encoding="utf-8")
        subprocess.run(["icacls.exe", str(marker), "/grant", "*S-1-5-32-545:R"],
                       check=True, capture_output=True)
        with self.assertRaisesRegex(ValueError, "restricted to your account"):
            cli.load_private(marker)

    async def test_scoped_asset_and_boot(self):
        url = "/engine/lily/boot"
        body = {"instance":"a"*32}
        self.assertEqual((await self.client.post(url,json=body)).status,401)
        res = await self.client.post(url,json=body,headers=self.auth)
        self.assertEqual(res.status,200)
        data = await res.json()
        self.assertEqual(data["env"]["JK_BOT_WEB_ROLE"],"host")
        self.assertNotIn(self.host.tokens["lily"],json.dumps(data))
        self.assertNotIn("JK_BOT_LILY", data["env"])
        self.assertEqual((await self.exchange([cp.frame(5,1,1,2,struct.pack("<IIB",42,13,0))])).status,400)
        self.assertEqual((await self.client.post("/engine/yun/boot",json=body,headers=self.auth)).status,401)
        self.assertEqual((await self.client.get("/engine/lily/assets/0",headers=self.auth)).status,200)
        self.assertEqual((await self.client.get("/engine/lily/assets/0")).status,401)
        self.assertEqual((await self.client.get("/engine/lily/assets/999",headers=self.auth)).status,404)
        self.assertEqual((await self.client.get("/status",headers={"Origin":"https://invalid.test"})).status,403)

    async def boot(self):
        result=await self.client.post("/engine/lily/boot",json={"instance":"a"*32},headers=self.auth)
        self.assertEqual(result.status,200)
        return await result.json()

    async def exchange(self, datagrams, **extra):
        body=dict(instance="a"*32,frames=[base64.b64encode(raw).decode() for raw in datagrams],**extra)
        return await self.client.post("/engine/lily/frames",json=body,headers=self.auth)

    async def test_four_competitive_modes_reach_every_seat_and_manifest(self):
        for mode in ("ff-guns","ff-sabers","nf-guns","nf-sabers"):
            with self.subTest(mode=mode):
                arena = serve.Host(self.root/"game", self.root/"engine", self.root/mode,
                                   "Canyon", None, False, mode=mode)
                browser = TestClient(TestServer(arena.app(), host="127.0.0.1"))
                try:
                    await browser.start_server()
                    arena.set_port(browser.server.port)
                    self.assertEqual(json.loads((arena.runtime/"run.json").read_text())["mode"],mode)
                    self.assertEqual((await (await browser.get("/status")).json())["mode"],mode)
                    for ident in serve.SEATS:
                        res = await browser.post(f"/engine/{ident}/boot",json={"instance":"a"*32},
                                   headers={"Authorization":"Bearer "+arena.tokens[ident]})
                        self.assertEqual(res.status,200)
                        self.assertEqual((await res.json())["env"]["JK_BOT_WEB_MODE"],mode)
                finally:
                    await browser.close()
                    arena.close()
        self.assertEqual((await self.boot())["env"]["JK_BOT_WEB_MODE"],"ff-guns")
        with self.assertRaisesRegex(ValueError, "mode"):
            serve.Host(self.root/"game", self.root/"engine", self.root/"invalid",
                       "Canyon", None, False, mode="anything")
        self.assertFalse((self.root/"invalid").exists())

    async def test_model_and_engine_credential_never_served_as_public_files(self):
        conf=await self.boot()
        self.assertFalse(conf["mod"])
        self.assertEqual([f["path"] for f in conf["assets"]],["/jk1/"+f for f in serve.ASSETS])
        for route in ("/engines/lily.json","/wasm/other","/bot/unknown"):
            self.assertEqual((await self.client.get(route)).status,404)
        self.assertEqual((await self.client.get("/status",headers={"Host":"someone-else.example"})).status,403)
        result=await self.client.get("/relay")
        self.assertIn(result.status,(403,503))

    async def test_datagram_http_round_trip_and_epoch_fencing(self):
        await self.boot()
        state=bytearray(144)
        struct.pack_into("<4I",state,0,1,42,88,13)
        struct.pack_into("<iII",state,60,-1,4,0xffffffff)
        res=await self.exchange([cp.frame(cp.STATE,1,1,1,state)],view={"flags":7,"model":"dlil.3do"})
        self.assertEqual(res.status,200)
        status=await (await self.client.get("/status")).json()
        self.assertEqual(status["joined_count"],1)
        self.assertEqual(status["seats"]["lily"]["view"],{"flags":7,"model":"dlil.3do"})
        hub=self.host.hub
        token=hub.bots["lily"].token
        fence={"run_id":hub.run_id,"world_epoch":1,"life_epoch":1}
        _,lease=hub.request("POST","lily","attach","",token,dict(fence,controller="Coda"))
        _,pending=hub.request("POST","lily","strategy","",token,
                             dict(fence,lease_id=lease["lease_id"],request_id="web",mode="recover"))
        self.assertEqual(pending["status"],"pending")
        response=await (await self.exchange([])).json()
        raw=base64.b64decode(response["frames"][0]); _,_,kind,_,world,life,seq=cp.HEADER.unpack_from(raw)
        self.assertEqual((kind,world,life),(16,1,1))
        self.assertLessEqual(struct.unpack_from("<d",raw,20)[0]-response["server_mono"],10)
        await self.exchange([cp.frame(cp.ACK,1,1,seq,struct.pack("<BBH",0,kind,0))])
        self.assertEqual(hub.request("GET","lily","commands/web","",token,None)[1]["status"],"applied")
        self.assertEqual((await self.exchange([b"bad"])).status,400)
        self.assertEqual((await self.client.post("/engine/lily/boot",json={"instance":"b"*32},headers=self.auth)).status,409)
        self.host.seats["lily"]["poll"]-=9
        await self.client.post("/engine/lily/boot",json={"instance":"b"*32},headers=self.auth)
        self.assertEqual((await self.exchange([])).status,409)
        data={"instance":"b"*32,"frames":[base64.b64encode(cp.frame(cp.STATE,1,1,1,state)).decode()]}
        self.assertEqual((await self.client.post("/engine/lily/frames",json=data,headers=self.auth)).status,200)
        self.assertEqual(hub.bots["lily"].world,2)
        self.assertIsNone(hub.bots["lily"].lease)

    async def test_adaptive_restart_preserves_native_ids_and_revokes_tickets_at_boot(self):
        arena = serve.Host(self.root/"game", self.root/"engine", self.root/"adaptive",
                           "Canyon", None, False, adaptive_lily=True)
        self.addCleanup(arena.close)
        browser = TestClient(TestServer(arena.app(), host="127.0.0.1"))
        await browser.start_server()
        self.addAsyncCleanup(browser.close)
        arena.set_port(browser.server.port)
        async def send(seat, route, instance, frames=None):
            body = {"instance": instance * 32}
            if frames is not None:
                body["frames"] = [base64.b64encode(f).decode() for f in frames]
            return await browser.post(f"/engine/{seat}/{route}", json=body,
                                      headers={"Authorization": "Bearer " + arena.tokens[seat]})
        def request(route, body=None):
            bot = arena.hub.bots["lily"]
            return arena.hub.request("GET" if body is None else "POST", "lily", route, "", bot.token, body)[1]
        state = bytearray(144)
        struct.pack_into("<4I", state, 0, 1, 42, 14, 88)
        struct.pack_into("<iII", state, 60, -1, 4, 0xffffffff)
        initial = cp.frame(1, 1, 1, 1, state)
        offer = cp.frame(5, 1, 1, 2, struct.pack("<IIB", 83, 90, 0))
        self.assertNotIn("JK_BOT_LILY", (await (await send("yun", "boot", "a")).json())["env"])
        self.assertEqual((await send("yun", "frames", "a", [offer])).status, 400)
        self.assertEqual((await (await send("lily", "boot", "a")).json())["env"]["JK_BOT_LILY"], "1")
        self.assertEqual((await send("lily", "frames", "a", [initial, offer])).status, 200)
        obs = request("observation")
        fence = {key: obs[key] for key in cp.FENCE}
        lease = dict(fence, lease_id=request("attach", dict(fence, controller="fixture"))["lease_id"])
        request("strategy", dict(lease, request_id="old", mode="recover"))
        arena.seats["lily"]["poll"] -= 9
        self.assertEqual((await send("lily", "boot", "b")).status, 200)
        self.assertIsNone(request("observation")["lily"]["offers"])
        self.assertFalse(request("observation")["native_active"])
        with self.assertRaises(cp.Problem):
            request("renew", lease)
        self.assertEqual((await send("lily", "frames", "a", [])).status, 409)
        resp = await (await send("lily", "frames", "b", [initial, offer])).json()
        self.assertEqual(resp["frames"], [])
        obs = request("observation")
        self.assertEqual(obs["world_epoch"], 2)
        self.assertEqual(obs["lily"]["offers"], {"sample_id":83, "offer_id":90, "choices":[]})
        sense = cp.lily.SENSE_HEADER.pack(83, 0, 0, 0, -1, 0, 0, 1, 1, 0,
                                          *([0.] * 14), 16., *([0.] * 4), 0, 0, 0, 0)
        self.assertEqual((await send("lily", "frames", "b", [cp.frame(7, 1, 1, 3, sense)])).status, 200)
        fresh = {key: obs[key] for key in cp.FENCE}
        ticket = request("attach", dict(fresh, controller="fixture"))
        action = dict(fresh, lease_id=ticket["lease_id"], request_id="lily.1", revision=5,
                      sample_id=83, steps=[{"duration_ms": 80}])
        receipt = request("motor", action)
        exchanged = await (await send("lily", "frames", "b", [])).json()
        packet = base64.b64decode(exchanged["frames"][0])
        self.assertEqual(cp.HEADER.unpack_from(packet)[4:], (1, 1, receipt["action_seq"]))
        self.assertEqual(cp.lily.MOTOR_HEADER.unpack_from(packet, cp.HEADER.size)[1:], (83, 5, 1))
        ack = cp.frame(2, 1, 1, receipt["action_seq"], struct.pack("<BBH", 0, 20, 0))
        self.assertEqual((await send("lily", "frames", "b", [ack])).status, 200)
        self.assertEqual(request("commands/lily.1")["status"], "applied")

    async def test_ordered_and_bounded_private_video_file(self):
        await self.boot()
        prefix="/engine/lily/capture/"
        hdr={**self.auth,"X-Engine-Instance":"a"*32}
        meta={"mime":"video/webm","audio_tracks":1,"width":640,"height":360}
        cap=await (await self.client.post(prefix+"start",json=meta,headers=hdr)).json()
        hdr["X-Capture-ID"]=cap["capture_id"]
        raw=bytes.fromhex("1a45dfa3")+b"fixture"
        self.assertEqual((await self.client.post(prefix+"chunk",data=raw,headers={**hdr,"X-Chunk-Index":"1"})).status,409)
        self.assertEqual((await self.client.post(prefix+"chunk",data=raw,headers={**hdr,"X-Chunk-Index":"0"})).status,200)
        self.assertEqual((await self.client.post(prefix+"finish",json={"chunks":1,"duration_seconds":2.1},headers=hdr)).status,200)
        status=await (await self.client.get("/status")).json()
        self.assertNotIn("capture_id",status["capture"])
        self.assertEqual((self.host.runtime/status["capture"]["filename"]).read_bytes(),raw)

    async def test_crashed_recorder_releases_handle_and_rejects_late_chunks(self):
        await self.boot()
        prefix="/engine/lily/capture/"
        hdr={**self.auth,"X-Engine-Instance":"a"*32}
        meta={"mime":"video/webm","audio_tracks":1,"width":640,"height":360}
        first=await (await self.client.post(prefix+"start",json=meta,headers=hdr)).json()
        old={**hdr,"X-Capture-ID":first["capture_id"],"X-Chunk-Index":"0"}
        handle=self.host.capture["file"]
        self.host.capture["last_chunk_mono"]-=serve.CAPTURE_IDLE_SECONDS+1
        status=await (await self.client.get("/status")).json()
        self.assertEqual(status["capture"]["status"],"aborted")
        self.assertTrue(handle.closed)
        self.assertTrue((self.host.runtime/("canyon-"+first["capture_id"]+".webm.part")).exists())
        second=await (await self.client.post(prefix+"start",json=meta,headers=hdr)).json()
        raw=bytes.fromhex("1a45dfa3")+b"new recording"
        self.assertEqual((await self.client.post(prefix+"chunk",data=raw,headers=old)).status,409)
        current={**hdr,"X-Capture-ID":second["capture_id"],"X-Chunk-Index":"0"}
        self.assertEqual((await self.client.post(prefix+"chunk",data=raw,headers=current)).status,200)
        self.assertEqual((await self.client.post(prefix+"finish",json={"chunks":1,"duration_seconds":2},headers=current)).status,200)
        self.assertEqual((self.host.runtime/self.host.capture["filename"]).read_bytes(),raw)

    async def test_restarted_browser_aborts_previous_capture(self):
        await self.boot()
        hdr={**self.auth,"X-Engine-Instance":"a"*32}
        response=await self.client.post("/engine/lily/capture/start",headers=hdr,
            json={"mime":"video/webm","audio_tracks":1,"width":640,"height":360})
        self.assertEqual(response.status,200)
        handle=self.host.capture["file"]
        self.host.seats["lily"]["poll"]-=9
        response=await self.client.post("/engine/lily/boot",json={"instance":"b"*32},headers=self.auth)
        self.assertEqual(response.status,200)
        self.assertTrue(handle.closed)
        self.assertEqual(self.host.capture["status"],"aborted")

    @asynccontextmanager
    async def paused_capture_request(self, step, headers, metadata):
        """Stop one real handler inside its awaited JSON read."""
        entered, resume = asyncio.Event(), asyncio.Event()
        read = self.host.body

        async def controlled_read(request):
            if request.headers.get("X-Test-Pause") == "1":
                entered.set()
                await resume.wait()
            return await read(request)

        with patch.object(self.host, "body", controlled_read):
            task = asyncio.create_task(self.client.post("/engine/lily/capture/" + step,
                headers={**headers, "X-Test-Pause":"1"}, json=metadata))
            try:
                await asyncio.wait_for(entered.wait(), timeout=3)
                yield
            finally:
                resume.set()
                response = await asyncio.wait_for(task, timeout=3)
                try:
                    self.assertEqual(response.status, 409)
                finally:
                    response.release()

    async def test_paused_start_cannot_displace_live_capture_or_claim_restarted_seat(self):
        await self.boot()
        headers = {**self.auth, "X-Engine-Instance":"a"*32}
        metadata = {"mime":"video/webm", "audio_tracks":1, "width":640, "height":360}
        prefix = "/engine/lily/capture/"
        async with self.paused_capture_request("start", headers, metadata):
            current = await self.client.post(prefix+"start", headers=headers, json=metadata)
            self.assertEqual(current.status, 200)
            ident = (await current.json())["capture_id"]
        self.assertEqual(self.host.capture["capture_id"], ident)
        self.assertEqual(len(list(self.host.runtime.glob("*.webm.part"))), 1)
        abort = await self.client.post(prefix+"abort", headers={**headers,"X-Capture-ID":ident})
        self.assertEqual(abort.status, 200)

        async with self.paused_capture_request("start", headers, metadata):
            self.host.seats["lily"]["poll"] -= 9
            reboot = await self.client.post("/engine/lily/boot", headers=self.auth, json={"instance":"b"*32})
            self.assertEqual(reboot.status, 200)
        self.assertEqual(self.host.capture["status"], "aborted")
        self.assertEqual(len(list(self.host.runtime.glob("*.webm.part"))), 1)

    async def test_paused_finish_cannot_finalize_expired_or_replaced_capture(self):
        await self.boot()
        headers = {**self.auth, "X-Engine-Instance":"a"*32}
        metadata = {"mime":"video/webm", "audio_tracks":1, "width":640, "height":360}
        prefix = "/engine/lily/capture/"
        initial = await self.client.post(prefix+"start", headers=headers, json=metadata)
        self.assertEqual(initial.status, 200)
        old_id = (await initial.json())["capture_id"]
        old_headers = {**headers, "X-Capture-ID":old_id}
        raw = bytes.fromhex("1a45dfa3")+b"first capture"
        uploaded = await self.client.post(prefix+"chunk", headers={**old_headers,"X-Chunk-Index":"0"}, data=raw)
        self.assertEqual(uploaded.status, 200)
        async with self.paused_capture_request("finish", old_headers, {"chunks":1,"duration_seconds":1}):
            self.host.capture["last_chunk_mono"] -= serve.CAPTURE_IDLE_SECONDS+1
            await self.client.get("/status")
            replacement = await self.client.post(prefix+"start", headers=headers, json=metadata)
            self.assertEqual(replacement.status, 200)
            new_id = (await replacement.json())["capture_id"]
        self.assertEqual((self.host.runtime/("canyon-"+old_id+".webm.part")).read_bytes(), raw)
        self.assertFalse((self.host.runtime/("canyon-"+old_id+".webm")).exists())
        self.assertEqual(self.host.capture["capture_id"], new_id)
        self.assertEqual(self.host.capture["status"], "recording")

    async def test_internal_relay_accepts_only_the_proxy_proof(self):
        # The upstream handler doubles as an observable upgrade marker. This
        # exercises the private child process independently of the public API.
        fixture = self.root / "relay_fixture.py"
        fixture.write_text("""from http.server import BaseHTTPRequestHandler
HOLD_S = 60
class Handler(BaseHTTPRequestHandler):
    def handle_websocket(self):
        self.send_response(204)
        self.end_headers()
def IceConfig(*args): return None
def Relay(*args): return None
""")
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-u", "-m", "web_bots.serve", "--relay-child", str(fixture),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE)
        try:
            proof = "c" * 64
            proc.stdin.write((proof + "\n").encode())
            await proc.stdin.drain()
            port = serve.relay_ready_port(await asyncio.wait_for(proc.stdout.readline(), 5))
            async with ClientSession() as session:
                for supplied, status in ((None,403),("wrong",403),(proof,204)):
                    headers = {"Upgrade":"websocket","Origin":"https://other.invalid"}
                    if supplied is not None:
                        headers["X-JK-Relay-Proof"] = supplied
                    async with session.get(f"http://127.0.0.1:{port}/relay?net=2",headers=headers) as res:
                        self.assertEqual(res.status,status)
                        self.assertNotIn(proof,await res.text())
        finally:
            proc.stdin.close()
            await asyncio.wait_for(proc.wait(),5)
        self.assertNotIn(proof.encode(),await proc.stderr.read())

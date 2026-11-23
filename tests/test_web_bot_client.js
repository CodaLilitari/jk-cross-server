/* Exercise browser boot/clock adaptation with synthetic exports; no game assets. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const crypto = require("node:crypto");
const delay = ms => new Promise(resolve => setTimeout(resolve,ms));

async function check(mode, adaptive) {
  const nodes = new Map();
  const el = id => {
    if (!nodes.has(id)) nodes.set(id,{});
    return nodes.get(id);
  };
  const dirs = [], files = [], delivered = [];
  const heap = new Uint8Array(2048);
  let sent = false, payloadReceived = false, inited = false;
  let wasmNow = 100;
  const clockCmd = new Uint8Array(20+28);
  clockCmd.set(Buffer.from("JKCP")); clockCmd[4]=1; clockCmd[5]=16;
  const view = new DataView(clockCmd.buffer);
  view.setUint16(6,28,true); view.setFloat64(20,5002,true);
  const command = (kind, deadline) => {
    const bytes = clockCmd.slice(), v = new DataView(bytes.buffer);
    bytes[5] = kind; v.setFloat64(20,deadline,true);
    v.setUint32(28,73,true);
    return Buffer.from(bytes).toString("base64");
  };
  const forwardedKinds = new Set();
  const ctx = { crypto:crypto.webcrypto, Uint8Array, DataView, TextDecoder, Blob, console, btoa, atob,
    location:{pathname:"/bot/lily",host:"127.0.0.1:3912",origin:"http://127.0.0.1:3912"},
    document:{querySelector:el,createElement:()=>({}),head:{append(script) {
      const m=ctx.Module;
      m.FS={mkdirTree:x=>dirs.push(x),writeFile:(p,b)=>files.push([p,b.length])};
      m.HEAPU8=heap; m.ENV={};
      m._jkBotWebNow=()=>wasmNow;
      m._jkBotWebInbox=()=>160;
      m._jkBotWebReceive=n=>delivered.push(heap.slice(160,160+n));
      m._jkBotWebViewFlags=()=>0;
      m._jkBotWebRenderedModel=()=>0;
      m.preRun[0](); m.onRuntimeInitialized(); script.onload();
      for (const kind of [1,5,7]) {
        const frame = new Uint8Array(24); frame[5] = kind; m.onJkBotEvent(frame);
      }
      inited=true;
    }}},
    setTimeout:(fn,ms)=>setTimeout(fn,Math.min(3,ms)).unref(),
    __JK_BOT_TOKEN:"synthetic-key",
    fetch:async (url, opts)=>{
      assert.equal(opts.headers.Authorization,"Bearer synthetic-key");
      if(url.endsWith("/boot")) return {ok:true,json:async()=>({mod:true,assets:[{path:"/jk1/resource/Res2.gob"}],
        env:{JK_BOT_LILY:adaptive ? "1" : "0",JK_BOT_WEB_NAME:"Darth_Lilitari",JK_BOT_WEB_MODEL:"dlil.3do",JK_BOT_WEB_SOUND:"dlil.snd",
             JK_BOT_WEB_MODE:mode,JK_BOT_WEB_ROOM:"Canyon",JK_BOT_WEB_ROLE:"host",JK_BOT_FORCE_SIDE:"dark",JK_BOT_FORCE_STYLE:"competitive",JK_BOT_WEB_THIRD_PERSON:"1"}})};
      if(url.endsWith("/assets/0"))return {ok:true,arrayBuffer:async()=>new ArrayBuffer(17)};
      assert.ok(url.endsWith("/frames"));
      const msg=JSON.parse(opts.body);
      assert.ok(!("token" in msg));
      if(msg.frames.length)payloadReceived=true;
      for (const data of msg.frames) forwardedKinds.add(Buffer.from(data,"base64")[5]);
      const send=inited && !sent;
      if (send) {
        sent=true;
        wasmNow+=0.75; // The POST began at 100; the response arrives at 100.75.
      }
      return {ok:true,json:async()=>({frames:send?[command(16,5002),command(19,5001),command(20,5002),command(20,4999),command(20,5000.5),command(16,5000.5)]:[],server_mono:5000})};
    }
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,"../web_bots/client.js"),"utf8"),ctx);
  for(let i=0;!delivered.length && i<50;i++)await delay(5);
  assert.equal(ctx.__JK_BOT_TOKEN,undefined);
  assert.ok(dirs.includes("/jk1/player") && dirs.includes("/mots/persist"));
  assert.deepEqual(files,[["/jk1/resource/Res2.gob",17]]);
  assert.equal(ctx.Module.jkSavesMounted,true);
  assert.equal(ctx.Module.jkBotConfig.mode,mode);
  assert.equal(ctx.Module.ENV.JK_BOT_WEB_MODE,mode);
  assert.equal(ctx.Module.jkBotConfig.elite,true);
  assert.equal(ctx.Module.jkBotConfig.sound,"dlil.snd");
  assert.equal(ctx.Module.jkRelayUrl,"ws://127.0.0.1:3912/relay");
  assert.equal(payloadReceived,true);
  assert.deepEqual(Array.from(forwardedKinds), adaptive ? [1,5,7] : [1]);
  assert.equal(ctx.Module.jkBotConfig.lily,adaptive);
  assert.deepEqual(delivered.map(frame=>frame[5]), adaptive ? [16,19,20] : [16]);
  for (const frame of delivered) {
    const v = new DataView(frame.buffer);
    assert.equal(v.getFloat64(20,true), frame[5] === 19 ? 101 : 102);
    assert.equal(v.getUint32(28,true),73);
  }
  assert.equal(new DataView(delivered[0].buffer).getFloat64(20,true),102);
  console.log("Browser client boot, scoped MEMFS, frame transfer and monotonic TTL mapping passed.");
}
Promise.all(["ff-guns","ff-sabers","nf-guns","nf-sabers"].map((mode,i)=>check(mode, i%2===1))).catch(e=>{console.error(e);process.exitCode=1;});

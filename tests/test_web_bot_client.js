/* Exercise browser boot/clock adaptation with synthetic exports; no game assets. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const crypto = require("node:crypto");
const delay = ms => new Promise(resolve => setTimeout(resolve,ms));

async function check(mode) {
  const nodes = new Map();
  const el = id => {
    if (!nodes.has(id)) nodes.set(id,{});
    return nodes.get(id);
  };
  const dirs = [], files = [], delivered = [];
  const heap = new Uint8Array(2048);
  let sent = false, payloadReceived = false, inited = false;
  const clockCmd = new Uint8Array(20+28);
  // Sabers modes carry a tactics command (21); guns modes a strategy (16).
  clockCmd.set(Buffer.from("JKCP")); clockCmd[4]=1; clockCmd[5]=mode.endsWith("sabers") ? 21 : 16;
  const view = new DataView(clockCmd.buffer);
  view.setUint16(6,28,true); view.setFloat64(20,5002,true);
  const ctx = { crypto:crypto.webcrypto, Uint8Array, DataView, TextDecoder, Blob, console, btoa, atob,
    location:{pathname:"/bot/lily",host:"127.0.0.1:3912",origin:"http://127.0.0.1:3912"},
    document:{querySelector:el,createElement:()=>({}),head:{append(script) {
      const m=ctx.Module;
      m.FS={mkdirTree:x=>dirs.push(x),writeFile:(p,b)=>files.push([p,b.length])};
      m.HEAPU8=heap; m.ENV={};
      m._jkBotWebNow=()=>100;
      m._jkBotWebInbox=()=>160;
      m._jkBotWebReceive=n=>delivered.push(heap.slice(160,160+n));
      m._jkBotWebViewFlags=()=>0;
      m._jkBotWebRenderedModel=()=>0;
      m.preRun[0](); m.onRuntimeInitialized(); script.onload();
      m.onJkBotEvent(new Uint8Array(24)); inited=true;
    }}},
    setTimeout:(fn,ms)=>setTimeout(fn,Math.min(3,ms)).unref(),
    __JK_BOT_TOKEN:"synthetic-key",
    fetch:async (url, opts)=>{
      assert.equal(opts.headers.Authorization,"Bearer synthetic-key");
      if(url.endsWith("/boot")) return {ok:true,json:async()=>({mod:true,assets:[{path:"/jk1/resource/Res2.gob"}],
        env:{JK_BOT_WEB_NAME:"Darth_Lilitari",JK_BOT_WEB_MODEL:"dlil.3do",JK_BOT_WEB_SOUND:"dlil.snd",
             JK_BOT_WEB_MODE:mode,JK_BOT_WEB_ROOM:"Canyon",JK_BOT_WEB_ROLE:"host",JK_BOT_FORCE_SIDE:"dark",JK_BOT_FORCE_STYLE:"competitive",JK_BOT_WEB_THIRD_PERSON:"1"}})};
      if(url.endsWith("/assets/0"))return {ok:true,arrayBuffer:async()=>new ArrayBuffer(17)};
      assert.ok(url.endsWith("/frames"));
      const msg=JSON.parse(opts.body);
      assert.ok(!("token" in msg));
      if(msg.frames.length)payloadReceived=true;
      const send=inited && !sent;
      if(send)sent=true;
      return {ok:true,json:async()=>({frames:send?[Buffer.from(clockCmd).toString("base64")]:[],server_mono:5000})};
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
  assert.equal(delivered.length,1);
  assert.equal(new DataView(delivered[0].buffer).getFloat64(20,true),102);
  assert.equal(delivered[0][5],mode.endsWith("sabers") ? 21 : 16);
  console.log("Browser client boot, scoped MEMFS, frame transfer and monotonic TTL mapping passed.");
}
Promise.all(["ff-guns","ff-sabers","nf-guns","nf-sabers"].map(check)).catch(e=>{console.error(e);process.exitCode=1;});

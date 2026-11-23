/* Current JKWeb private arena. The native game loop never waits for this bridge. */
(() => {
  "use strict";
  const id = location.pathname.split("/").pop();
  const canvas = document.querySelector("#canvas");
  const status = document.querySelector("#state");
  const error = document.querySelector("#error");
  const record = document.querySelector("#record");
  const instance = Array.from(crypto.getRandomValues(new Uint8Array(16)), x => x.toString(16).padStart(2,"0")).join("");
  let token, mod, stage = "waiting", polling = false, captured = null, dropped = 0;
  const queue = [];
  let render = null, adaptiveLily = false;
  let latestView = {flags:0, model:""};

  function message(err) {
    error.textContent = err.message || String(err);
  }
  function heap() {
    return mod.HEAPU8 || globalThis.HEAPU8;
  }
  function wasmClock() {
    return stage === "running" && mod && typeof mod._jkBotWebNow === "function" ? mod._jkBotWebNow() : null;
  }
  function graphics() {
    if (!mod || typeof mod._jkBotWebViewFlags !== "function" || wasmClock() === null) return;
    const flags = mod._jkBotWebViewFlags();
    if (!flags) return;
    const ptr = mod._jkBotWebRenderedModel();
    const bytes = heap();
    let model = "";
    if (ptr > 0 && bytes && ptr < bytes.length) {
      const part = bytes.subarray(ptr, Math.min(bytes.length, ptr+96));
      const end = part.indexOf(0);
      if (end >= 0) model = new TextDecoder().decode(part.subarray(0,end));
    }
    latestView = {flags, model};
    // Query the game's own context after rendering starts. Creating a fresh
    // probing canvas could yield a different backend from the actual view.
    const gl = globalThis.GL?.currentContext?.GLctx || canvas.getContext("webgl2");
    if (!gl || gl.isContextLost()) return;
    const debug = gl.getExtension("WEBGL_debug_renderer_info");
    render = {renderer: String(gl.getParameter(debug ? debug.UNMASKED_RENDERER_WEBGL : gl.RENDERER)),
              vendor: String(gl.getParameter(debug ? debug.UNMASKED_VENDOR_WEBGL : gl.VENDOR)),
              width:gl.drawingBufferWidth, height:gl.drawingBufferHeight};
  }

  async function api(path, body, extra = {}) {
    const headers = {Authorization:"Bearer "+token, ...extra};
    const options = {headers, cache:"no-store"};
    if (body !== undefined) {
      options.method = "POST";
      if (body instanceof Blob) options.body = body;
      else {
        headers["Content-Type"] = "application/json";
        options.body = JSON.stringify(body);
      }
    }
    const res = await fetch("/engine/"+id+"/"+path, options);
    if (!res.ok) throw new Error(path+" returned "+res.status+": "+(await res.text()).slice(0,180));
    return res;
  }
  function outgoing(bytes) {
    if (!(bytes instanceof Uint8Array) || bytes.length < 20 || bytes.length > 512) return;
    const kind = bytes[5];
    if (![1,2,3,4].includes(kind) && !(adaptiveLily && [5,6,7].includes(kind))) return;
    if (queue.length >= 128) {
      const stateIndex = queue.findIndex(f => f[5] === 1);
      queue.splice(stateIndex < 0 ? 0 : stateIndex, 1);
      dropped++;
    }
    queue.push(bytes.slice());
  }
  function deliver(encoded, t0, serverMono) {
    if (t0 === null || !Number.isFinite(serverMono)) return;
    const data = Uint8Array.from(atob(encoded), c => c.charCodeAt(0));
    if (data.length < 28 || data.length > 512) return;
    const view = new DataView(data.buffer);
    const allowed = [16,17,18].includes(data[5]) || (adaptiveLily && [19,20].includes(data[5]));
    if (!allowed || view.getUint16(6,true) !== data.length-20) return;
    // Charge the full poll latency against TTL. Absolute clock origins in
    // Python and Emscripten need not agree. Dequeued commands are sent once.
    const expires = t0 + (view.getFloat64(20,true)-serverMono);
    if (!Number.isFinite(expires) || wasmClock() >= expires) return;
    view.setFloat64(20,expires,true);
    const ptr = mod._jkBotWebInbox();
    const bytes = heap();
    if (ptr <= 0 || ptr + data.length > bytes.length) throw new Error("Invalid native companion inbox.");
    bytes.set(data,ptr);
    mod._jkBotWebReceive(data.length);
  }
  async function pump() {
    let ticks = 0;
    while (polling) {
      try {
        if (stage === "running" && ticks++ % 20 === 0) graphics();
        const batch = queue.splice(0,32);
        const packet = {instance, frames:batch.map(f => btoa(String.fromCharCode(...f))),
                        dropped, stage, view:latestView};
        if (render) packet.graphics = render;
        const t0 = wasmClock();
        const reply = await (await api("frames",packet)).json();
        for (const data of reply.frames) deliver(data,t0,reply.server_mono);
      } catch (err) {
        message(err);
      }
      await new Promise(done => setTimeout(done,50));
    }
  }

  async function start(auth) {
    if (token) throw new Error("An engine has already started on this page.");
    token = auth;
    let boot;
    try { boot = await (await api("boot",{instance})).json(); }
    catch (err) { token = null; throw err; }
    adaptiveLily = id === "lily" && boot.env.JK_BOT_LILY === "1";
    document.querySelector("#login").hidden = true;
    document.querySelector("#title").textContent = boot.env.JK_BOT_WEB_NAME;
    document.title = boot.env.JK_BOT_WEB_NAME+" · JKWeb";
    stage = "assets";
    polling = true;
    void pump();
    try {
      const loaded = [];
      for (const [i,item] of boot.assets.entries()) {
        status.textContent = "Loading game files "+(i+1)+" / "+boot.assets.length;
        const r = await api("assets/"+i);
        loaded.push([item.path,new Uint8Array(await r.arrayBuffer())]);
      }
      const env = boot.env;
      stage = "startup";
      status.textContent = "Starting JKWeb";
      mod = globalThis.Module = {
        canvas,
        arguments: boot.mod ? ["-path","jkmods/companion"] : [],
        jkBotConfig:{lily:adaptiveLily,mode:env.JK_BOT_WEB_MODE,role:env.JK_BOT_WEB_ROLE,room:env.JK_BOT_WEB_ROOM,name:env.JK_BOT_WEB_NAME,
                     model:env.JK_BOT_WEB_MODEL,sound:env.JK_BOT_WEB_SOUND,side:env.JK_BOT_FORCE_SIDE,
                     saberColor:env.JK_BOT_WEB_SABER_COLOR,trace:env.JK_BOT_TRACE_FORCE==="1",
                     style:env.JK_BOT_FORCE_STYLE,thirdPerson:env.JK_BOT_WEB_THIRD_PERSON==="1",elite:true},
        jkRelayUrl:"ws://"+location.host+"/relay",
        locateFile:name => "/wasm/"+name,
        onJkBotEvent:outgoing,
        print:line => console.log(line), printErr:line => console.error(line),
        onAbort:reason => { stage="failed"; status.textContent="Engine stopped"; message(String(reason)); },
        preRun:[() => {
          const fs = mod.FS;
          for (const path of ["/jk1/player","/jk1/persist","/mots/player","/mots/persist"]) fs.mkdirTree(path);
          mod.jkSavesMounted = true;
          for (const [path,data] of loaded) {
            fs.mkdirTree(path.slice(0,path.lastIndexOf("/")));
            fs.writeFile(path,data,{canOwn:true});
          }
          loaded.length=0;
          if (mod.ENV || globalThis.ENV) Object.assign(mod.ENV || globalThis.ENV,env);
        }],
        onRuntimeInitialized:() => {
          if (![mod._jkBotWebNow,mod._jkBotWebInbox,mod._jkBotWebReceive,
                mod._jkBotWebViewFlags,mod._jkBotWebRenderedModel].every(x=>typeof x==="function")) {
            stage="failed"; message("This WASM lacks the JKWeb companion exports."); return;
          }
          stage="running";
          status.textContent="Engine running";
          record.hidden = id !== "lily";
        }
      };
      await new Promise((resolve,reject)=>{
        const script=document.createElement("script");
        script.src="/wasm/openjkdf2.js"; script.onload=resolve;
        script.onerror=()=>reject(new Error("Could not load JKWeb engine."));
        document.head.append(script);
      });
    } catch (err) {
      stage="failed"; status.textContent="Startup failed"; throw err;
    }
  }

  async function startRecording(seconds=120) {
    if (id!=="lily" || stage!=="running" || captured) throw new Error("Lily's running view is required.");
    if (!(Number.isFinite(seconds) && seconds>0 && seconds<=240)) throw new Error("Duration must be more than 0 and at most 240 seconds.");
    if (!canvas.captureStream || typeof MediaRecorder==="undefined") throw new Error("Canvas recording is unavailable.");
    graphics();
    const stream=canvas.captureStream(30);
    const ctx=globalThis.AL?.currentCtx;
    let tap=null;
    if (ctx?.gain && ctx.audioCtx) {
      if (ctx.audioCtx.state!=="running") {
        try { await Promise.race([ctx.audioCtx.resume(),new Promise(resolve=>setTimeout(resolve,400))]); }
        catch (_) {}
      }
      if (ctx.audioCtx.state==="running") {
        tap=ctx.audioCtx.createMediaStreamDestination();
        ctx.gain.connect(tap);
        for (const track of tap.stream.getAudioTracks()) stream.addTrack(track);
      }
    }
    const mime=["video/webm;codecs=vp9,opus","video/webm;codecs=vp8,opus","video/webm"].find(x=>MediaRecorder.isTypeSupported(x));
    if (!mime) { for (const t of stream.getTracks()) t.stop(); throw new Error("No WebM encoder available."); }
    const rec=new MediaRecorder(stream,{mimeType:mime,videoBitsPerSecond:6000000});
    let n=0, queued=0, failure=null, writes=Promise.resolve();
    const headers={"X-Engine-Instance":instance};
    const cleanup=()=>{
      for (const t of stream.getTracks()) t.stop();
      if (tap) ctx.gain.disconnect(tap);
    };
    try {
      const reply=await (await api("capture/start",{mime,audio_tracks:stream.getAudioTracks().length,
                                   width:canvas.width,height:canvas.height},headers)).json();
      headers["X-Capture-ID"]=reply.capture_id;
    } catch (err) { cleanup(); throw err; }
    const started=performance.now();
    let timer;
    captured={rec,status:"recording",seconds};
    record.disabled=true; record.textContent="Recording…";
    rec.ondataavailable=ev=>{
      if (!ev.data.size || failure) return;
      if (queued+ev.data.size>24*1024*1024) {
        failure=new Error("Local recording upload fell behind."); if(rec.state==="recording")rec.stop(); return;
      }
      const idx=n++;
      queued+=ev.data.size;
      writes=writes.then(async()=>{
        if (!failure) await api("capture/chunk",ev.data,{...headers,"X-Chunk-Index":String(idx)});
      }).catch(err=>{failure=err; if(rec.state==="recording")rec.stop();}).finally(()=>{queued-=ev.data.size;});
    };
    rec.onerror=ev=>{failure=ev.error || new Error("Encoder failed."); if(rec.state==="recording")rec.stop();};
    rec.onstop=async()=>{
      clearTimeout(timer);
      const elapsed=(performance.now()-started)/1000;
      await writes;
      try {
        if (failure) throw failure;
        const res=await (await api("capture/finish",{chunks:n,duration_seconds:elapsed},headers)).json();
        status.textContent="Recording saved ("+res.bytes+" bytes)";
      } catch(err) {
        message(err);
        try { await api("capture/abort",{},headers); } catch (_) {}
      } finally {
        cleanup(); captured=null; record.disabled=false; record.textContent="Record 120 seconds";
      }
    };
    try {
      rec.start(1000);
      timer=setTimeout(()=>{if(rec.state==="recording")rec.stop();},seconds*1000);
    } catch(err) {
      await api("capture/abort",{},headers); cleanup(); captured=null; record.disabled=false; throw err;
    }
    return {seconds,audio_tracks:stream.getAudioTracks().length,mime};
  }
  globalThis.jkBot = {startRecording,info:()=>({id,stage,graphics:render,view:latestView,
                                 dropped,recording:captured?.status || null})};
  record.onclick=()=>startRecording().catch(message);
  document.querySelector("#credential").onchange=async ev=>{
    try {
      const file=ev.target.files[0];
      if (!file || file.size>4096) throw new Error("Choose this seat's engine credential.");
      const cred=JSON.parse(await file.text());
      if(cred.id!==id || cred.url!==location.origin) throw new Error("Credential belongs to another seat or run.");
      await start(cred.token);
    } catch(err) { message(err); }
  };
  if (globalThis.__JK_BOT_TOKEN) {
    const auth=globalThis.__JK_BOT_TOKEN;
    delete globalThis.__JK_BOT_TOKEN;
    start(auth).catch(message);
  }
})();

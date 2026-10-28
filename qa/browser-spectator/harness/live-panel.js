const {chromium}=require('/opt/codex/runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const out=__dirname,prefix=process.argv[2]||'pilot';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 const browser=await chromium.launch({executablePath:'/tmp/jk-chrome/chrome-linux64/chrome',headless:true,args:['--no-sandbox','--enable-unsafe-swiftshader','--use-gl=angle','--use-angle=swiftshader']});
 const record={utc:new Date().toISOString(),browser:await browser.version(),observations:[],page_errors:[],http_failures:[],geometry_frames:[],checks:{},scope:'Actual local stock JK1MP/m2 world, two ordinary bot clients, production panel and renderer. Read-only instrumentation records production draw calls and samples actual pixels.'};
 let page;const pending=[];
 try{
  page=await browser.newPage({viewport:{width:1440,height:1050}});
  await page.addInitScript(()=>{
   let value;
   window.geometryProbe={draws:0,first:null,last:null};
   Object.defineProperty(window,'JKSGGeometry',{configurable:true,get(){return value;},set(module){
    const original=module.createRenderer;value={...module,createRenderer(canvas,options){const renderer=original(canvas,options);const draw=renderer.draw;renderer.draw=frame=>{draw(frame);const gl=canvas.getContext('webgl2'),pixel=new Uint8Array(4),samples=[];for(const [x,y] of [[160,90],[320,180],[480,270]]){gl.readPixels(x,y,1,1,gl.RGBA,gl.UNSIGNED_BYTE,pixel);samples.push([...pixel]);}const e={sequence:frame.sequence,world_epoch:frame.world_epoch,control_epoch:frame.control_epoch,vertices:frame.vertices.byteLength/20,indices:frame.indices.length,age_ms:frame.age_ms,samples,gl_error:gl.getError()};window.geometryProbe.draws++;window.geometryProbe.first??=e;window.geometryProbe.last=e;};return renderer;}};
   }});
  });
  page.on('pageerror',e=>record.page_errors.push(e.message));
  page.on('response',response=>{
   const u=new URL(response.url());if(u.pathname.startsWith('/api/spectator')&&response.status()>=400)record.http_failures.push({path:u.pathname,status:response.status()});
   if(u.pathname==='/api/spectator/geometry'&&response.status()===200){const p=response.body().then(b=>{record.geometry_frames.push({bytes:b.length,sequence:b.readUInt32LE(24),world_epoch:b.readUInt32LE(16),control_epoch:b.readUInt32LE(20),vertices:b.readUInt32LE(40),indices:b.readUInt32LE(44),age_ms:b.readUInt32LE(36),sha256:crypto.createHash('sha256').update(b).digest('hex'),payload_sha256:crypto.createHash('sha256').update(b.subarray(64)).digest('hex')});}).catch(()=>{});pending.push(p);}
  });
  await page.goto('http://127.0.0.1:48765/');
  const status=()=>page.evaluate(async()=>{const token=document.querySelector('meta[name="admin-token"]').content;const d=await(await fetch('/api/status',{headers:{Authorization:'Bearer '+token}})).json();const s=await(await fetch('/api/spectator',{headers:{Authorization:'Bearer '+token}})).json();return {state:d.state,session:d.session,bots:d.bots,spectator:s,engine:d.processes?.engine,native_connected:d.native_connected};});
  const observe=async label=>{const value=await status();record.observations.push({label,...value});return value;};
  await page.waitForFunction(()=>!document.getElementById('spectator-toggle').disabled,{timeout:20000});
  const before=await observe('before-opening');
  if(before.spectator.enabled){await page.click('#spectator-toggle');await page.waitForFunction(()=>document.getElementById('spectator-toggle').textContent==='Open spectator');}
  record.checks.image_default=await page.inputValue('#spectator-backend')==='image';
  await page.click('#spectator-toggle');
  await page.waitForFunction(()=>/Frame \d+/.test(document.getElementById('spectator-frame-detail').textContent),{timeout:15000});
  const image=await observe('image-view');await page.locator('#spectator-panel').screenshot({path:path.join(out,prefix+'-image.png')});
  await page.selectOption('#spectator-backend','geometry');
  await page.waitForFunction(()=>window.geometryProbe.draws>=3,{timeout:15000});
  const geometry=await observe('geometry-view');await page.locator('#spectator-panel').screenshot({path:path.join(out,prefix+'-geometry.png')});
  record.checks.backend_switch_preserves_epochs=image.spectator.world_epoch===geometry.spectator.world_epoch&&image.spectator.control_epoch===geometry.spectator.control_epoch;
  record.paired_capture=await page.evaluate(async()=>{
   const token=document.querySelector('meta[name="admin-token"]').content,headers={Authorization:'Bearer '+token};
   for(let i=0;i<10;i++){
    const s=await(await fetch('/api/spectator',{headers})).json();const q=`?after=0&world_epoch=${s.world_epoch}&control_epoch=${s.control_epoch}`;
    const [g,r]=await Promise.all([fetch('/api/spectator/geometry'+q,{headers}),fetch('/api/spectator/frame'+q,{headers})]);
    if(g.status===200&&r.status===200){const b=await g.arrayBuffer(),pixels=await r.arrayBuffer(),v=new DataView(b);const value={geometry_sequence:v.getUint32(24,true),image_sequence:Number(r.headers.get('X-JK-Frame-Sequence')),world_epoch:v.getUint32(16,true),control_epoch:v.getUint32(20,true),geometry_bytes:b.byteLength,image_bytes:pixels.byteLength};if(value.geometry_sequence===value.image_sequence)return {matched:true,...value};}
    await new Promise(resolve=>setTimeout(resolve,100));
   }
   return {matched:false};
  });
  record.checks.geometry_and_image_share_capture_sequence=record.paired_capture.matched;

  await page.locator('#spectator-geometry-canvas').focus();await page.keyboard.down('w');await sleep(600);await page.keyboard.up('w');await sleep(250);
  const moved=await observe('free-camera-moved');
  record.checks.free_camera_moved=JSON.stringify(geometry.spectator.pose.position)!==JSON.stringify(moved.spectator.pose.position);
  await page.selectOption('#spectator-mode','follow');
  await page.waitForFunction(()=>document.getElementById('spectator-state').textContent==='Following player');
  await sleep(700);const follow1=await observe('follow-player-first');await sleep(1000);const follow2=await observe('follow-player-later');
  record.checks.follow_tracks_player=follow1.spectator.mode==='follow'&&follow2.spectator.mode==='follow'&&JSON.stringify(follow1.spectator.pose)!==JSON.stringify(follow2.spectator.pose);
  await page.locator('#spectator-panel').screenshot({path:path.join(out,prefix+'-follow-geometry.png')});
  record.probe=await page.evaluate(()=>window.geometryProbe);
  await page.setViewportSize({width:390,height:844});await page.locator('#spectator-panel').screenshot({path:path.join(out,prefix+'-mobile.png')});
  record.checks.mobile_no_horizontal_overflow=await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth);
  await page.setViewportSize({width:1440,height:1050});
  await page.evaluate(()=>document.getElementById('spectator-geometry-canvas').getContext('webgl2').getExtension('WEBGL_lose_context').loseContext());
  await page.waitForFunction(()=>document.getElementById('spectator-backend').value==='image'&&/lost/i.test(document.getElementById('spectator-backend-status').textContent));
  await page.waitForFunction(()=>/Frame \d+/.test(document.getElementById('spectator-frame-detail').textContent)&&!document.getElementById('spectator-frame-detail').textContent.includes('Geometry'));
  const fallback=await observe('context-loss-image-fallback');record.checks.context_loss_fallback=fallback.spectator.enabled;
  await page.locator('#spectator-panel').screenshot({path:path.join(out,prefix+'-context-loss-fallback.png')});
  await page.click('#spectator-toggle');await page.waitForFunction(()=>document.getElementById('spectator-toggle').textContent==='Open spectator');
  const closed=await observe('after-closing');
  record.checks.close_keeps_server_running=closed.state==='running'&&!closed.spectator.enabled&&closed.engine.pid===before.engine.pid;
  record.checks.players_unchanged=record.observations.every(x=>x.session.players===2&&x.spectator.players.length===2&&x.bots.joined_count===2);
  record.checks.actual_geometry_draws=record.probe.draws>=3&&record.probe.last.indices>0&&record.probe.last.gl_error===0;
  record.checks.world_geometry_changes=new Set(record.geometry_frames.map(f=>f.payload_sha256)).size>1;
  await page.close();
  // A separate fresh page proves unsupported WebGL falls back through the real UI.
  page=await browser.newPage({viewport:{width:1000,height:850}});
  await page.addInitScript(()=>{const original=HTMLCanvasElement.prototype.getContext;HTMLCanvasElement.prototype.getContext=function(type,...rest){return type==='webgl2'?null:original.call(this,type,...rest);};});
  page.on('pageerror',e=>record.page_errors.push(e.message));
  await page.goto('http://127.0.0.1:48765/');await page.waitForFunction(()=>!document.getElementById('spectator-toggle').disabled);
  await page.click('#spectator-toggle');await page.waitForFunction(()=>document.getElementById('spectator-toggle').textContent==='Close spectator');
  await page.selectOption('#spectator-backend','geometry');await page.waitForFunction(()=>document.getElementById('spectator-backend').value==='image'&&/unavailable/i.test(document.getElementById('spectator-backend-status').textContent));
  await page.waitForFunction(()=>/Frame \d+/.test(document.getElementById('spectator-frame-detail').textContent));
  record.checks.unsupported_webgl_fallback=true;await page.locator('#spectator-panel').screenshot({path:path.join(out,prefix+'-unsupported-fallback.png')});
  await page.click('#spectator-toggle');
 }catch(error){record.error=error.stack;if(page){record.failure_ui=await page.evaluate(()=>({backend:document.getElementById('spectator-backend')?.value,status:document.getElementById('spectator-backend-status')?.textContent,message:document.getElementById('spectator-message')?.textContent,detail:document.getElementById('spectator-frame-detail')?.textContent,probe:window.geometryProbe})).catch(()=>null);await page.screenshot({path:path.join(out,prefix+'-failure.png'),fullPage:true}).catch(()=>{});}}
 finally{await Promise.allSettled(pending);await browser.close();record.finished_utc=new Date().toISOString();record.passed=!record.error&&record.page_errors.length===0&&Object.values(record.checks).every(Boolean);fs.writeFileSync(path.join(out,prefix+'-live-panel.json'),JSON.stringify(record,null,2)+'\n');console.log(JSON.stringify({passed:record.passed,error:record.error,checks:record.checks,frames:record.geometry_frames.length,probe:record.probe, failure_ui:record.failure_ui,page_errors:record.page_errors}));if(!record.passed)process.exitCode=1;}
})();

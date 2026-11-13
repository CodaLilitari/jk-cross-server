'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const geometryPath=path.join(__dirname,'../manager/ui/spectator-geometry.js');
const geometry=fs.existsSync(geometryPath)?require(geometryPath):{};
const epoch={world_epoch:7,control_epoch:3};
// Literal 136-byte envelope: one red, clockwise triangle, clip z=-0.5, w=1.
const triangle=()=>Uint8Array.from(Buffer.from(
  '4a4b534701000000800200006801000007000000030000000900000048000000'+
  '0000000064000000030000000300000000000000000000000000000000000000'+
  '000040bf000000bf000000bf0000803fff0000ff'+
  '000000000000003f000000bf0000803fff0000ff'+
  '0000403f000000bf000000bf0000803fff0000ff'+
  '000000000100000002000000','hex')).buffer;
function decode(buffer=triangle(),expected=epoch,after=8,elapsed=0){
  assert.equal(typeof geometry.decodeGeometry,'function','geometry decoder must be implemented');
  return geometry.decodeGeometry(buffer,expected,after,elapsed);
}
function change(offset,value,type='u32'){
  const buffer=triangle(),view=new DataView(buffer);
  if(type==='f32')view.setFloat32(offset,value,true);else if(type==='u8')view.setUint8(offset,value);else view.setUint32(offset,value,true);
  return buffer;
}

test('JKSG literal preserves four clip coordinates, opaque colour and index order',()=>{
  const frame=decode();
  assert.deepEqual([frame.width,frame.height,frame.sequence,frame.age_ms],[640,360,9,100]);
  assert.deepEqual([...frame.indices],[0,1,2]);
  assert.equal(frame.vertices.byteLength,60);
  const position=new DataView(frame.vertices.buffer,frame.vertices.byteOffset,16);
  assert.deepEqual([0,4,8,12].map(offset=>position.getFloat32(offset,true)),[-.75,-.5,-.5,1]);
  assert.deepEqual([...frame.vertices.slice(16,20)],[255,0,0,255]);
});

test('JKSG rejects malformed envelope size and hostile count products before allocating',()=>{
  assert.equal(typeof geometry.decodeGeometry,'function','geometry decoder must be implemented');
  for(const offset of [0,4,8,12,16,20,24,28,32,40,44,48,52,56,60]){
    const values={0:0,4:2,8:641,12:361,16:0,20:0,24:0,28:71,32:1,40:65537,44:196609,48:1,52:1,56:1,60:1};
    assert.throws(()=>decode(change(offset,values[offset])),undefined,'header offset '+offset);
  }
  for(const length of [0,63,64,135,137,2097217])assert.throws(()=>decode(new ArrayBuffer(length)));
  assert.throws(()=>decode(change(40,0xffffffff)));
  assert.throws(()=>decode(change(44,0xffffffff)));
  assert.throws(()=>decode(change(8,0)));assert.throws(()=>decode(change(12,0)));
  assert.throws(()=>decode(change(44,0)),'nonempty unreferenced vertices');
  const partial=triangle().slice(0,124);new DataView(partial).setUint32(28,60,true);new DataView(partial).setUint32(44,0,true);
  assert.throws(()=>decode(partial));
});

test('JKSG rejects nonfinite coordinates, nonopaque colours and out-of-range indices',()=>{
  assert.equal(typeof geometry.decodeGeometry,'function','geometry decoder must be implemented');
  for(const offset of [64,68,72,76,84,88,92,96,104,108,112,116]){
    for(const value of [NaN,Infinity,-Infinity])assert.throws(()=>decode(change(offset,value,'f32')));
  }
  for(const offset of [83,103,123])assert.throws(()=>decode(change(offset,254,'u8')));
  for(const offset of [124,128,132])assert.throws(()=>decode(change(offset,3)));
});

test('JKSG checks current epochs, sequence and inclusive capture plus transfer age',()=>{
  assert.throws(()=>decode(triangle(),{world_epoch:8,control_epoch:3}));
  assert.throws(()=>decode(triangle(),{world_epoch:7,control_epoch:4}));
  assert.throws(()=>decode(triangle(),epoch,9));
  assert.throws(()=>decode(triangle(),epoch,10));
  assert.equal(decode(triangle(),epoch,8,1900).age_ms,2000);
  assert.throws(()=>decode(triangle(),epoch,8,1901));
  for(const elapsed of [-1,NaN,Infinity])assert.throws(()=>decode(triangle(),epoch,8,elapsed));
  assert.throws(()=>decode(change(36,2001)));assert.throws(()=>decode(change(36,0xffffffff)));
});

test('JKSG accepts empty geometry as an explicitly cleared current frame',()=>{
  const buffer=triangle().slice(0,64),view=new DataView(buffer);
  view.setUint32(28,0,true);view.setUint32(40,0,true);view.setUint32(44,0,true);
  const frame=decode(buffer);assert.equal(frame.vertices.length,0);assert.equal(frame.indices.length,0);
});

const {mountedFixture,settle}=require('./spectator_fixture.js');
function geometryFetches(f){return f.requests.filter(r=>r.url.startsWith('/api/spectator/geometry?'));}
function imageFetches(f){return f.requests.filter(r=>r.url.startsWith('/api/spectator/frame?'));}
function select(f,value){f.nodes['spectator-backend'].value=value;f.nodes['spectator-backend'].emit('change');}
function response(buffer){return {status:200,ok:true,arrayBuffer:async()=>buffer};}
function currentTriangle(world=4,control=8){const b=triangle(),v=new DataView(b);v.setUint32(16,world,true);v.setUint32(20,control,true);return b;}

test('mounted image default never activates geometry; explicit selection polls geometry and retains read-only ownership',async()=>{
  const f=mountedFixture();f.update();await settle();f.intervals.get(200)();await settle();
  assert.equal(geometryFetches(f).length,0);assert.equal(imageFetches(f).length,1);
  select(f,'geometry');f.intervals.get(200)();await settle();
  assert.equal(geometryFetches(f).length,1);
  assert.equal(f.nodes['spectator-canvas'].hidden,true);assert.equal(f.nodes['spectator-geometry-canvas'].hidden,false);
  assert.equal(f.inputs().length,0);assert.equal(f.nodes['spectator-take-control'].hidden,false);
  assert.equal(f.requests.filter(r=>r.method==='PUT'&&r.url==='/api/spectator').length,0,'selection never reconfigures camera');
});

test('backend selection releases held movement and geometry canvas uses existing explicit camera ownership',async()=>{
  const f=mountedFixture();f.update();await settle();f.nodes['spectator-take-control'].emit('click');await settle();
  f.nodes['spectator-canvas'].emit('keydown',{code:'KeyW'});
  select(f,'geometry');await settle();
  assert.equal(f.inputs().length,1,'backend selection releases held movement');
  assert.equal(f.inputs().at(-1).body.forward,0);
  assert.equal(f.nodes['spectator-take-control'].hidden,true);
  f.nodes['spectator-geometry-canvas'].emit('keydown',{code:'KeyD'});
  await new Promise(resolve=>setTimeout(resolve,100)); // Input cadence follows the existing 95-ms limiter.
  f.intervals.get(100)();await settle();assert.equal(f.inputs().at(-1).body.right,1);
  assert.equal(f.requests.filter(r=>r.method==='PUT'&&r.url==='/api/spectator').length,1);
});

test('late geometry replies after switching away and back cannot draw in the newly selected view',async()=>{
  const f=mountedFixture();f.update();await settle();
  let finish;f.setGeometryResponse(()=>new Promise(resolve=>{finish=resolve;}));
  select(f,'geometry');f.intervals.get(200)();await settle();
  assert.equal(typeof finish,'function','geometry selection starts the requested fetch');
  select(f,'image');select(f,'geometry');finish(response(currentTriangle()));await settle();
  assert.equal(f.glCalls.filter(c=>c[0]==='drawElements').length,0);
  assert.match(f.nodes['spectator-frame-detail'].textContent,/Waiting/);
});

test('late geometry replies after epoch change or engine restart never draw',async()=>{
  for(const reset of ['epoch','session']){
    const f=mountedFixture();f.update();await settle();let finish;
    f.setGeometryResponse(()=>new Promise(resolve=>{finish=resolve;}));
    select(f,'geometry');f.intervals.get(200)();await settle();
    assert.equal(typeof finish,'function','geometry selection starts the requested fetch');
    if(reset==='epoch')f.change({world_epoch:5,control_epoch:1});else f.setPid(43);
    f.update();finish(response(currentTriangle()));await settle();
    assert.equal(f.glCalls.filter(c=>c[0]==='drawElements').length,0,reset);
  }
});

test('unavailable or lost WebGL falls back to usable image and stops geometry polling without claiming controls',async()=>{
  for(const failure of ['unavailable','lost']){
    const f=mountedFixture();f.update();await settle();
    if(failure==='unavailable')f.nodes['spectator-geometry-canvas'].getContext=()=>null;
    select(f,'geometry');
    if(failure==='lost')f.nodes['spectator-geometry-canvas'].emit('webglcontextlost');
    f.intervals.get(200)();await settle();
    assert.equal(f.nodes['spectator-backend'].value,'image');
    assert.equal(f.nodes['spectator-canvas'].hidden,false);assert.equal(geometryFetches(f).length,0);
    assert.equal(imageFetches(f).length,1);assert.match(f.nodes['spectator-backend-status'].textContent,/WebGL|context/i);
    assert.equal(f.inputs().length,0);
  }
});

test('fresh geometry reaches indexed opaque WebGL draw; hidden page stops polling',async()=>{
  const f=mountedFixture();f.update();await settle();f.setGeometryResponse(()=>response(currentTriangle()));
  select(f,'geometry');f.intervals.get(200)();await settle();
  assert.deepEqual(f.glCalls.filter(c=>c[0]==='drawElements'),[['drawElements',4,3,5125,0]]);
  assert.ok(f.glCalls.some(c=>c[0]==='depthFunc'&&c[1]===513));
  assert.ok(f.glCalls.some(c=>c[0]==='depthMask'&&c[1]===true));
  assert.ok(f.glCalls.some(c=>c[0]==='disable'&&c[1]===3042));
  assert.ok(f.glCalls.some(c=>c[0]==='disable'&&c[1]===2884));
  assert.match(f.nodes['spectator-frame-detail'].textContent,/9/);
  f.document.hidden=true;f.document.emit('visibilitychange');f.intervals.get(200)();await settle();
  assert.equal(geometryFetches(f).length,1);
});

test('geometry channel failure returns to image and cannot disable the observer',async()=>{
  const f=mountedFixture();f.update();await settle();select(f,'geometry');
  f.change({geometry:{available:false,frame_available:false,sequence:0,age_ms:null,reason:'Geometry channel closed.',profile:'flat-colour-v1'}});f.update();
  f.intervals.get(200)();await settle();
  assert.equal(f.nodes['spectator-backend'].value,'image');assert.equal(imageFetches(f).length,1);
  assert.equal(f.nodes['spectator-view'].hidden,false);assert.equal(geometryFetches(f).length,0);
  assert.match(f.nodes['spectator-backend-status'].textContent,/closed/);
});

test('falling back while a geometry body is delayed immediately permits image polling',async()=>{
  const f=mountedFixture();f.update();await settle();let finishBody;
  f.setGeometryResponse(()=>({status:200,ok:true,arrayBuffer:()=>new Promise(resolve=>{finishBody=resolve;})}));
  select(f,'geometry');f.intervals.get(200)();await settle();
  assert.equal(typeof finishBody,'function');
  f.nodes['spectator-geometry-canvas'].emit('webglcontextlost');
  f.intervals.get(200)();await settle();
  assert.equal(imageFetches(f).length,1,'image fallback must not wait on an obsolete geometry body');
  finishBody(currentTriangle());await settle();
  assert.equal(f.glCalls.filter(c=>c[0]==='drawElements').length,0);
});

test('a native sequence superseding an in-flight envelope prevents older geometry from being drawn',async()=>{
  const f=mountedFixture();f.update();await settle();let finish;
  f.setGeometryResponse(()=>new Promise(resolve=>{finish=resolve;}));
  select(f,'geometry');f.intervals.get(200)();await settle();
  f.change({geometry:{available:true,frame_available:true,sequence:10,age_ms:0,reason:'',profile:'flat-colour-v1'}});f.update();
  finish(response(currentTriangle()));await settle();
  assert.equal(f.glCalls.filter(c=>c[0]==='drawElements').length,0);
});

test('an authoritative newer image status rejects delayed geometry when geometry status has no current frame',async()=>{
  const f=mountedFixture();f.update();await settle();let finish;
  f.setGeometryResponse(()=>new Promise(resolve=>{finish=resolve;}));
  select(f,'geometry');f.intervals.get(200)();await settle();
  assert.equal(typeof finish,'function','geometry fetch must already be in flight');
  f.change({
    geometry:{available:true,frame_available:false,sequence:0,age_ms:null,reason:'',profile:'flat-colour-v1'},
    frame:{available:true,sequence:10,age_ms:0}
  });f.update();
  finish(response(currentTriangle()));await settle();
  assert.equal(f.glCalls.filter(c=>c[0]==='drawElements').length,0,'capture 9 is superseded by known image capture 10');
  assert.match(f.nodes['spectator-frame-detail'].textContent,/Waiting/);
  assert.equal(f.nodes['spectator-overlay'].hidden,false,'superseded response cannot hide the waiting overlay');
});

test('original visual fixture decodes the full independent clip-space shape and index set',()=>{
  const bytes=fs.readFileSync(path.join(__dirname,'fixtures/spectator_geometry.jksg'));
  const frame=decode(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength));
  assert.equal(frame.vertices.byteLength,460);assert.equal(frame.indices.length,33);
  assert.deepEqual([...frame.indices.slice(0,12)],[0,1,2,0,3,2,4,5,6,4,7,6]);
  assert.equal(frame.indices.at(-1),22);
  const vertices=new DataView(frame.vertices.buffer,frame.vertices.byteOffset,frame.vertices.byteLength);
  assert.deepEqual([0,4,8,12].map(i=>vertices.getFloat32(320+i,true)),[2.75,Math.fround(3.1111111111),-1,4]);
});

test('JKSG rejects invalid replay cursors rather than bypassing sequence comparison',()=>{
  for(const after of [-1,NaN,Infinity,undefined,'8',0x100000000]){
    assert.throws(()=>geometry.decodeGeometry(triangle(),epoch,after),undefined,String(after));
  }
  assert.equal(decode(triangle(),epoch,0).sequence,9);
});

test('a session readiness interruption revokes input ownership even if PID and epochs are reused',async()=>{
  const f=mountedFixture();f.update();await settle();
  f.nodes['spectator-take-control'].emit('click');await settle();
  assert.equal(f.nodes['spectator-take-control'].hidden,true);
  select(f,'geometry');await settle();const sent=f.inputs().length;
  f.update({session_ready:false});f.update();await settle();
  f.nodes['spectator-geometry-canvas'].emit('keydown',{code:'KeyW'});
  await new Promise(resolve=>setTimeout(resolve,100));f.intervals.get(100)();await settle();
  assert.equal(f.nodes['spectator-take-control'].hidden,false,'session resumption requires explicit camera control');
  assert.equal(f.inputs().length,sent);
});

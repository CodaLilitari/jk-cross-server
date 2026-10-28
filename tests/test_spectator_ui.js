'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const {ObserverInput,parseTarget,decodeFrame,olderSnapshot,ownsControl,mount}=require('../manager/ui/spectator.js');

test('camera motion cancels opposing keys and releases both movement and accumulated look',()=>{
  const input=new ObserverInput();
  input.setEpoch(7,3);
  for(const code of ['KeyW','KeyD','KeyE'])assert.equal(input.key(code,true),true);
  assert.equal(input.key('KeyF',true),false);
  assert.deepEqual(input.packet(),{world_epoch:7,control_epoch:3,sequence:1,
    forward:1,right:1,up:1,yaw_delta:0,pitch_delta:0});
  for(const code of ['KeyS','KeyA','KeyQ'])input.key(code,true);
  const opposed=input.packet();
  assert.deepEqual([opposed.forward,opposed.right,opposed.up],[0,0,0]);
  input.look(.5,-.4);
  input.clear();
  assert.deepEqual(input.packet(),{world_epoch:7,control_epoch:3,sequence:3,
    forward:0,right:0,up:0,yaw_delta:0,pitch_delta:0});
});

test('sequence advances within an epoch and only a new world/control epoch resets replay protection',()=>{
  const input=new ObserverInput();
  input.setEpoch(2,9);
  assert.equal(input.packet().sequence,1);
  assert.equal(input.setEpoch(2,9),false);
  assert.equal(input.packet().sequence,2);
  input.key('KeyW',true);input.look(.2,.3);
  assert.equal(input.setEpoch(2,10),true);
  assert.deepEqual(input.packet(),{world_epoch:2,control_epoch:10,sequence:1,
    forward:0,right:0,up:0,yaw_delta:0,pitch_delta:0});
  input.key('KeyD',true);
  assert.equal(input.setEpoch(3,10),true);
  assert.equal(input.packet().right,0);
});

test('look deltas stay finite and bounded, are consumed once, and arrows follow native yaw convention',()=>{
  const input=new ObserverInput();input.setEpoch(1,1);
  input.look(100,-100);input.look(NaN,Infinity);
  const first=input.packet(),next=input.packet();
  assert.deepEqual([first.yaw_delta,first.pitch_delta],[Math.PI,-Math.PI]);
  assert.deepEqual([next.yaw_delta,next.pitch_delta],[0,0]);
  input.key('ArrowRight',true);assert.ok(input.packet().yaw_delta<0);
  input.key('ArrowRight',false);input.key('ArrowLeft',true);assert.ok(input.packet().yaw_delta>0);
  input.key('ArrowLeft',false);input.key('ArrowUp',true);assert.ok(input.packet().pitch_delta>0);
});

test('a follow choice carries canonical peer plus connection generation, never just a slot or name',()=>{
  assert.deepEqual(parseTarget('101:17'),{peer_id:101,generation:17});
  assert.deepEqual(parseTarget('101:18'),{peer_id:101,generation:18});
  assert.notDeepEqual(parseTarget('101:17'),parseTarget('101:18'));
  for(const value of ['', 'Kyle', '3', '0:1', '2:0', '-1:4', '1.1:2', '2:3:4',
    '2:Infinity', '4294967296:1', '2:4294967296', null, 71]){
    assert.equal(parseTarget(value),null,String(value));
  }
});

test('older snapshots cannot undo newer epochs and a reloaded/read-only tab does not own active controls',()=>{
  const current={enabled:true,mode:'free',world_epoch:5,control_epoch:8};
  assert.equal(olderSnapshot(current,{world_epoch:4,control_epoch:90}),true);
  assert.equal(olderSnapshot(current,{world_epoch:5,control_epoch:7}),true);
  assert.equal(olderSnapshot(current,{world_epoch:5,control_epoch:8}),false);
  assert.equal(olderSnapshot(current,{world_epoch:6,control_epoch:1}),false);
  assert.equal(ownsControl(null,current),false);
  const owned={world_epoch:5,control_epoch:8};
  assert.equal(ownsControl(owned,current),true);
  for(const change of [{world_epoch:6},{control_epoch:9},{enabled:false},{mode:'follow'}]){
    assert.equal(ownsControl(owned,{...current,...change}),false);
  }
});

function headers(overrides={}){
  return new Headers({'X-JK-Frame-Width':'2','X-JK-Frame-Height':'1',
    'X-JK-Frame-Sequence':'9','X-JK-World-Epoch':'3','X-JK-Control-Epoch':'4',...overrides});
}

test('current RGBA frame retains dimensions, sequence and exact pixel order',()=>{
  const bytes=new Uint8Array([1,2,3,255,4,5,6,255]);
  const result=decodeFrame(headers(),bytes.buffer,{world_epoch:3,control_epoch:4},8);
  assert.equal(result.width,2);assert.equal(result.height,1);assert.equal(result.sequence,9);
  assert.deepEqual([...result.pixels],[...bytes]);
});

test('malformed, oversized, mismatched and replayed frames are rejected before drawing',()=>{
  const epoch={world_epoch:3,control_epoch:4},data=new ArrayBuffer(8);
  const invalid=[
    ['X-JK-Frame-Width','0'],['X-JK-Frame-Width','641'],['X-JK-Frame-Height','361'],
    ['X-JK-Frame-Height','-1'],['X-JK-Frame-Width','2px'],['X-JK-Frame-Width','2e0'],
    ['X-JK-Frame-Sequence','0'],['X-JK-Frame-Sequence','8'],['X-JK-Frame-Sequence','4294967296'],
    ['X-JK-World-Epoch','2'],['X-JK-Control-Epoch','3'],['X-JK-Control-Epoch','NaN'],
  ];
  for(const [key,value] of invalid){
    assert.throws(()=>decodeFrame(headers({[key]:value}),data,epoch,8),undefined,key+'='+value);
  }
  const missing=headers();missing.delete('X-JK-World-Epoch');
  assert.throws(()=>decodeFrame(missing,data,epoch,8));
  assert.throws(()=>decodeFrame(headers(),data,epoch,9));
  for(const length of [0,7,9])assert.throws(()=>decodeFrame(headers(),new ArrayBuffer(length),epoch,8));
});

// This small event surface exercises the real mounted controller without a
// browser dependency. Real layout, rendering and pointer capture stay in live QA.
class Element {
  constructor(id=''){
    this.id=id;this.value='';this.hidden=false;this.disabled=false;this.textContent='';
    this.children=[];this.listeners=new Map();this.style={};this.attributes={};this.dataset={};
    const classes=new Set();this.classList={add:value=>classes.add(value),remove:value=>classes.delete(value)};
  }
  addEventListener(name,listener){
    if(!this.listeners.has(name))this.listeners.set(name,[]);
    this.listeners.get(name).push(listener);
  }
  emit(name,values={}){
    const event={preventDefault(){this.defaultPrevented=true;},...values};
    for(const listener of this.listeners.get(name)||[])listener(event);
    return event;
  }
  setAttribute(name,value){this.attributes[name]=value;}
  replaceChildren(...children){this.children=children;this.value=children[0]?.value||'';}
  focus(){}
  setPointerCapture(){}
}

function mountedFixture(){
  const ids=('spectator-panel spectator-canvas spectator-toggle spectator-mode spectator-target '+
    'spectator-overlay spectator-frame-detail spectator-view spectator-follow-choice spectator-movement '+
    'spectator-take-control spectator-state spectator-message spectator-position').split(' ');
  const nodes=Object.fromEntries(ids.map(id=>[id,new Element(id)]));
  nodes['spectator-mode'].value='free';
  nodes['spectator-canvas'].width=640;nodes['spectator-canvas'].height=360;
  nodes['spectator-canvas'].getContext=()=>({fillRect(){},putImageData(){}});
  const movement=['KeyW','KeyS','KeyA','KeyD','KeyE','KeyQ'].map(code=>{
    const element=new Element();element.dataset.spectatorKey=code;return element;
  });
  nodes['spectator-panel'].querySelectorAll=()=>movement;
  const document=new Element();
  document.hidden=false;
  document.getElementById=id=>{assert.ok(nodes[id],'fixture needs '+id);return nodes[id];};
  document.querySelector=selector=>{assert.equal(selector,'meta[name="admin-token"]');return {content:'fixture-private-token'};};
  document.createElement=()=>new Element();
  const window=new Element(),intervals=new Map(),requests=[];
  let timeoutId=0,lastInput=600;
  let native={available:true,enabled:true,mode:'free',world_epoch:4,control_epoch:8,
    players:[{peer_id:71,generation:5,slot:1,name:'Kyle'}],target:null,reason:'',
    frame:{available:false},pose:{position:[0,0,0],sector:0}};
  const snapshot=()=>structuredClone(native);
  window.setInterval=(callback,delay)=>{intervals.set(delay,callback);return delay;};
  window.setTimeout=()=>++timeoutId;window.clearTimeout=()=>{};
  window.location={reload(){throw new Error('Unexpected authentication reload');}};
  window.fetch=async(url,options)=>{
    const body=options.body===undefined?undefined:JSON.parse(options.body);
    requests.push({url,method:options.method,headers:options.headers,body});
    assert.equal(options.headers.Authorization,'Bearer fixture-private-token');
    assert.equal(options.cache,'no-store');
    const response=(status,value)=>({status,ok:status<400,json:async()=>structuredClone(value)});
    if(url.startsWith('/api/spectator/frame?'))return response(204,null);
    if(options.method==='GET')return response(200,snapshot());
    if(body.world_epoch!==native.world_epoch||body.control_epoch!==native.control_epoch){
      return response(409,{error:'Stale control epoch'});
    }
    if(url==='/api/spectator/input'){
      if(body.sequence<=lastInput)return response(409,{error:'Replayed input'});
      lastInput=body.sequence;
    }else{
      native={...native,control_epoch:native.control_epoch+1,mode:body.mode,
        enabled:body.mode!=='off',target:body.target};
      lastInput=0;
    }
    return response(200,snapshot());
  };
  const controller=mount(document,window);
  const update=()=>controller.updateStatus({state:'running',native_connected:true,session_ready:true,
    processes:{engine:{pid:42}},spectator:snapshot()});
  return {nodes,window,document,requests,intervals,update,
    change:value=>{native={...native,...value};},
    inputs:()=>requests.filter(request=>request.url==='/api/spectator/input')};
}

const settle=()=>new Promise(resolve=>setImmediate(resolve));

test('a mounted reload waits for explicit control, then starts a fresh sequence and rightward drag turns right',async()=>{
  const fixture=mountedFixture();
  fixture.update();await settle();
  fixture.nodes['spectator-canvas'].emit('keydown',{code:'KeyW'});
  fixture.intervals.get(100)();await settle();
  assert.equal(fixture.inputs().length,0,'opening a second page must not send stationary or held input');
  assert.equal(fixture.nodes['spectator-take-control'].hidden,false);
  fixture.nodes['spectator-take-control'].emit('click');await settle();
  assert.equal(fixture.nodes['spectator-take-control'].hidden,true);
  const canvas=fixture.nodes['spectator-canvas'];
  canvas.emit('keydown',{code:'KeyW'});
  canvas.emit('pointerdown',{button:0,pointerId:1,clientX:10,clientY:20});
  canvas.emit('pointermove',{pointerId:1,clientX:30,clientY:10});
  fixture.intervals.get(100)();await settle();
  assert.equal(fixture.inputs().length,1);
  const input=fixture.inputs()[0].body;
  assert.equal(input.sequence,1);assert.equal(input.world_epoch,4);assert.equal(input.control_epoch,9);
  assert.equal(input.forward,1);assert.ok(input.yaw_delta<0);assert.ok(input.pitch_delta>0);
  assert.deepEqual(Object.keys(input).sort(),
    ['world_epoch','control_epoch','sequence','forward','right','up','yaw_delta','pitch_delta'].sort());
  fixture.window.emit('blur');await settle();
  assert.deepEqual(fixture.inputs().at(-1).body,{world_epoch:4,control_epoch:9,sequence:2,
    forward:0,right:0,up:0,yaw_delta:0,pitch_delta:0});
});

test('an external epoch revokes mounted control and stale status cannot re-enable input',async()=>{
  const fixture=mountedFixture();fixture.update();await settle();
  fixture.nodes['spectator-take-control'].emit('click');await settle();
  fixture.nodes['spectator-canvas'].emit('keydown',{code:'KeyW'});
  fixture.change({control_epoch:10});fixture.update();await settle();
  fixture.window.emit('blur');await settle();
  assert.equal(fixture.inputs().length,0,'even a forced release must not emit INPUT for another owner');
  assert.equal(fixture.nodes['spectator-take-control'].hidden,false);
  fixture.change({control_epoch:9});fixture.update();await settle();
  fixture.nodes['spectator-canvas'].emit('keydown',{code:'KeyW'});
  fixture.intervals.get(100)();await settle();
  assert.equal(fixture.inputs().length,0);
});

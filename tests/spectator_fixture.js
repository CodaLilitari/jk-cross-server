'use strict';
const assert=require('node:assert/strict');
const {mount}=require('../manager/ui/spectator.js');
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
  removeEventListener(name,listener){this.listeners.set(name,(this.listeners.get(name)||[]).filter(value=>value!==listener));}
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
    'spectator-take-control spectator-state spectator-message spectator-position spectator-backend '+
    'spectator-geometry-canvas spectator-backend-status').split(' ');
  const nodes=Object.fromEntries(ids.map(id=>[id,new Element(id)]));
  nodes['spectator-mode'].value='free';
  nodes['spectator-backend'].value='image';
  const glCalls=[];
  const glConstants={VERTEX_SHADER:35633,FRAGMENT_SHADER:35632,COMPILE_STATUS:35713,LINK_STATUS:35714,ARRAY_BUFFER:34962,ELEMENT_ARRAY_BUFFER:34963,STREAM_DRAW:35040,FLOAT:5126,UNSIGNED_BYTE:5121,TRIANGLES:4,UNSIGNED_INT:5125,DEPTH_TEST:2929,LESS:513,BLEND:3042,CULL_FACE:2884,COLOR_BUFFER_BIT:16384,DEPTH_BUFFER_BIT:256};
  const gl=new Proxy(glConstants,{get(object,key){if(key in object)return object[key];if(key==='getShaderParameter'||key==='getProgramParameter')return ()=>true;if(key==='isContextLost')return ()=>false;if(String(key).startsWith('create'))return ()=>({});return (...args)=>glCalls.push([key,...args]);}});
  nodes['spectator-geometry-canvas'].getContext=kind=>{assert.equal(kind,'webgl2');return gl;};
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
  let timeoutId=0,lastInput=600,pid=42,geometryResponse=null,frameResponse=null;
  const geometryPath=require('node:path').join(__dirname,'../manager/ui/spectator-geometry.js');
  window.JKSGGeometry=require('node:fs').existsSync(geometryPath)?require(geometryPath):null;
  let native={available:true,enabled:true,mode:'free',world_epoch:4,control_epoch:8,
    players:[{peer_id:71,generation:5,slot:1,name:'Kyle'}],target:null,reason:'',
    geometry:{available:true,frame_available:false,sequence:0,age_ms:null,reason:'',profile:'flat-colour-v1'},
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
    if(url.startsWith('/api/spectator/frame?'))return frameResponse?frameResponse():response(204,null);
    if(url.startsWith('/api/spectator/geometry?'))return geometryResponse?geometryResponse():response(204,null);
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
  const update=(overrides={})=>controller.updateStatus({state:'running',native_connected:true,session_ready:true,
    processes:{engine:{pid}},spectator:snapshot(),...overrides});
  return {nodes,window,document,requests,intervals,update,glCalls,
    setGeometryResponse:value=>{geometryResponse=value;},setFrameResponse:value=>{frameResponse=value;},setPid:value=>{pid=value;},
    change:value=>{native={...native,...value};},
    inputs:()=>requests.filter(request=>request.url==='/api/spectator/input')};
}

const settle=()=>new Promise(resolve=>setImmediate(resolve));
module.exports={Element,mountedFixture,settle};

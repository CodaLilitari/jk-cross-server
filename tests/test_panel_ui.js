'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {panelPresentation}=require('../manager/ui/app.js');
const ui=path.join(__dirname,'../manager/ui');
const descriptor={name:'Review match',episode:'JK1MP',map:'m2.jkl',players:2,max:15};
const running={state:'running',native_connected:true,session_ready:true,session:descriptor,
  browser:{players:9,max:9,episode:'STALE',map:'stale.jkl'},engine_display_backend:'offscreen'};

test('current native descriptor supplies all-route player count and map without subtracting the host twice',()=>{
  const result=panelPresentation(running,{web_enabled:true});
  assert.equal(result.ready,true);assert.equal(result.session,'Ready');
  assert.equal(result.players,'2 / 15');assert.equal(result.map,'JK1MP / m2.jkl');
  assert.equal(result.display,'offscreen');
  assert.equal(panelPresentation({...running,session:{...descriptor,players:0}}).players,'0 / 15');
});

test('an older manager without session_ready remains supported when its native descriptor is current',()=>{
  const legacy={...running};delete legacy.session_ready;
  assert.equal(panelPresentation(legacy).ready,true);
  for(const change of [{native_connected:false},{session:null},{state:'starting'}]){
    assert.equal(panelPresentation({...legacy,...change}).ready,false);
  }
});

test('disconnect, stale descriptor, startup and stopped/failed states retire session-derived presentation',()=>{
  for(const change of [{native_connected:false},{session_ready:false},{session_ready:null},
    {state:'starting'},{state:'stopping'},{state:'stopped'},{state:'failed'},{state:'disconnected'},
    {session:null}]){
    const result=panelPresentation({...running,...change},{web_enabled:true});
    assert.equal(result.ready,false,JSON.stringify(change));
    assert.equal(result.players,'—');assert.equal(result.map,'No active session');
    assert.notEqual(result.session,'Ready');
  }
  assert.equal(panelPresentation({...running,state:'failed'}).display,'—');
});

test('missing or malformed native metadata never falls back to browser-only metadata',()=>{
  const invalid=[null,{},...[
    {name:undefined},{episode:null},{map:[]},{players:-1},{players:1.5},{players:'2'},
    {players:NaN},{max:0},{max:32},{max:'15'}
  ].map(change=>({...descriptor,...change}))];
  for(const session of invalid){
    const result=panelPresentation({...running,session});
    assert.equal(result.ready,false);
    assert.equal(result.players,'—');assert.equal(result.map,'No active session');
  }
});

test('transport listener status remains distinct from game-session readiness',()=>{
  const waiting=panelPresentation({...running,session_ready:false},{web_enabled:true,retail_enabled:true});
  assert.equal(waiting.web,'Listening');assert.equal(waiting.native,'Connected');
  assert.equal(waiting.session,'Waiting for current session');assert.equal(waiting.retail,'Waiting');
  const stopped=panelPresentation({state:'stopped',native_connected:false},{web_enabled:false,retail_enabled:false});
  assert.equal(stopped.web,'Disabled');assert.equal(stopped.retail,'Disabled');
});

// Read the actual static document, retaining ancestors to catch accidental
// placement inside fieldsets disabled while the match runs.
function documentNodes(){
  const html=fs.readFileSync(path.join(ui,'index.html'),'utf8'),nodes=[],stack=[];
  const voidTags=new Set(['area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr']);
  for(const match of html.matchAll(/<!--[\s\S]*?-->|<\/?([A-Za-z][\w:-]*)\b[^>]*>/g)){
    if(!match[1])continue;
    const tag=match[1].toLowerCase(),token=match[0];
    if(token.startsWith('</')){
      const at=stack.map(node=>node.tag).lastIndexOf(tag);
      assert.ok(at>=0,'unmatched closing '+tag);stack.length=at;continue;
    }
    const attributes={};
    const suffix=token.slice(token.indexOf(match[1])+match[1].length,-1);
    for(const attribute of suffix.matchAll(/([^\s=/>]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g)){
      attributes[attribute[1]]=attribute[2]??attribute[3]??attribute[4]??'';
    }
    const node={tag,attributes,ancestors:[...stack]};nodes.push(node);
    if(!voidTags.has(tag)&&!token.endsWith('/>'))stack.push(node);
  }
  return {html,nodes};
}

test('static panel preserves unique required controls, legacy settings and script bindings',()=>{
  const {html,nodes}=documentNodes();
  const identified=nodes.filter(node=>node.attributes.id);
  const ids=new Map();
  for(const node of identified){
    assert.equal(ids.has(node.attributes.id),false,'duplicate ID '+node.attributes.id);
    ids.set(node.attributes.id,node);
  }
  const required=('settings settings-fields bot-behavior-fields preflight save start stop catalog episodes maps '+
    'native-status session-status retail-status web-status player-status display-status map-status logs play-link '+
    'bot-profiles bot-status bot-player-detail bot-behavior-save admin-keys-panel admin-key-form admin-key-list '+
    'admin-key-label admin-key-issue admin-cap-next admin-cap-kick admin-keys-refresh update-panel update-check '+
    'update-install update-restart updates-enabled updates-auto-install asset-panel spectator-panel spectator-canvas '+
    'spectator-toggle spectator-take-control spectator-mode spectator-target spectator-view').split(' ');
  for(const id of required)assert.ok(ids.has(id),'missing required control '+id);
  for(const filename of ['app.js','spectator.js']){
    const source=fs.readFileSync(path.join(ui,filename),'utf8');
    for(const match of source.matchAll(/\bbyId\(['"]([^'"]+)['"]\)/g)){
      assert.ok(ids.has(match[1]),filename+' references absent element '+match[1]);
    }
  }
  const names=new Set(nodes.map(node=>node.attributes.name).filter(Boolean));
  for(const name of ('game name episode map password max_players rank tick_ms score_limit time_limit teams '+
    'auto_restart game_data engine web_client mod_dir web_asset_downloads retail_enabled web_enabled native_port '+
    'web_bind web_port directplay_bridge wine wine_prefix ipc_port broker_port engine_display spectator_rendering '+
    'game_flags web_origins web_ice_servers bots_enabled bots_taunts bots_engine bots_sabers_only bots_fists_peace '+
    'bots_force_enabled').split(' '))assert.ok(names.has(name),'missing saved setting '+name);
  assert.match(html,/<title>JK Cross Server<\/title>/);
  const scripts=nodes.filter(node=>node.tag==='script');
  assert.deepEqual(scripts.map(node=>node.attributes.src),['/ui/spectator.js','/ui/app.js']);
  for(const script of scripts)assert.ok(Object.hasOwn(script.attributes,'defer'));
  assert.match(fs.readFileSync(path.join(ui,'app.js'),'utf8'),/window\.jkSpectator\?\.updateStatus\(value\)/);
});

test('spectator and live bot controls stay outside the disabled settings fieldset',()=>{
  const {nodes}=documentNodes();
  const byId=id=>nodes.find(node=>node.attributes.id===id);
  const settingsAncestor=node=>node.ancestors.some(parent=>parent.attributes.id==='settings-fields');
  assert.equal(settingsAncestor(byId('spectator-panel')),false);
  assert.equal(byId('spectator-panel').ancestors.some(parent=>parent.tag==='form'),false);
  assert.equal(settingsAncestor(byId('bot-behavior-fields')),false);
  for(const id of ['spectator-toggle','spectator-take-control']){
    assert.equal(byId(id).attributes.type,'button');assert.equal(settingsAncestor(byId(id)),false);
  }
  const camera=byId('spectator-canvas');
  assert.equal(camera.attributes.width,'640');assert.equal(camera.attributes.height,'360');
  assert.ok(Number(camera.attributes.tabindex)>=0);
  const movements=nodes.filter(node=>Object.hasOwn(node.attributes,'data-spectator-key'));
  assert.deepEqual(movements.map(node=>node.attributes['data-spectator-key']).sort(),
    ['KeyW','KeyS','KeyA','KeyD','KeyE','KeyQ'].sort());
  for(const node of movements)assert.equal(settingsAncestor(node),false);
  assert.equal(settingsAncestor(nodes.find(node=>node.attributes.name==='spectator_rendering')),true);
});

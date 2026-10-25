'use strict';
const token=document.querySelector('meta[name="admin-token"]').content;
const form=document.querySelector('#settings');
const fields=document.querySelector('#settings-fields');
let config=null, catalog=null, lastStatus=null, lastUpdate=null, busy=false, updateBusy=false, reconnecting=false, authorityBusy=false;
const numeric=['max_players','rank','tick_ms','score_limit','time_limit','native_port','ipc_port','broker_port','web_port','game_flags'];
const bools=['teams','web_enabled','web_asset_downloads','retail_enabled','auto_restart',
  'bots_enabled','bots_taunts','bots_sabers_only','bots_fists_peace','bots_force_enabled'];
const behaviorKeys=['bots_sabers_only','bots_fists_peace','bots_force_enabled'];
const byId=id=>document.getElementById(id);

async function api(path,method='GET',body){
  const headers={'Authorization':'Bearer '+token};
  if(body!==undefined) headers['Content-Type']='application/json';
  const response=await fetch('/api/'+path,{method,headers,body:body===undefined?undefined:JSON.stringify(body),cache:'no-store'});
  if(response.status===401){window.location.reload();throw new Error('Reconnecting to the restarted control panel…');}
  const result=await response.json();
  if(!response.ok) throw new Error(result.error||('Request failed: '+response.status));
  return result;
}
function notice(message,type='success'){
  const node=byId('notice');node.textContent=message;node.className=type;node.hidden=false;
}
function fill(value){
  config=value;
  for(const [key,item] of Object.entries(value)){
    const input=form.elements.namedItem(key);if(!input)continue;
    if(bools.includes(key))input.checked=item;
    else input.value=key==='web_origins'?item.join('\n'):key==='web_ice_servers'?JSON.stringify(item,null,2):String(item);
  }
  for(const input of byId('bot-profiles').querySelectorAll('input'))input.checked=value.bots_profiles.includes(input.value);
  updateRankHint();
}
function updateRankHint(){byId('rank-hint').hidden=form.elements.namedItem('game').value!=='mots';}
function current(){
  const value={...config};
  for(const key of Object.keys(config)){
    const input=form.elements.namedItem(key);if(!input)continue;
    value[key]=bools.includes(key)?input.checked:numeric.includes(key)?Number(input.value):
      key==='web_origins'?input.value.split(/\r?\n/).map(s=>s.trim()).filter(Boolean):
      key==='web_ice_servers'?JSON.parse(input.value||'[]'):
      key==='password'?input.value:input.value.trim();
  }
  value.bots_profiles=[...byId('bot-profiles').querySelectorAll('input:checked')].map(input=>input.value);
  return value;
}
function mapChoices(){
  const episode=form.elements.namedItem('episode').value.toLowerCase();
  const selected=catalog?.episodes.find(e=>e.episode.toLowerCase()===episode);
  byId('maps').replaceChildren(...(selected?.maps||[]).map(name=>{const n=document.createElement('option');n.value=name;return n;}));
}
function updateControls(){
  const state=lastStatus?.state||'stopped';
  const editable=['stopped','failed'].includes(state);
  fields.disabled=!editable||busy;
  const liveBots=state==='running'&&Boolean(lastStatus?.bots?.enabled);
  byId('bot-behavior-fields').disabled=busy||(!editable&&!liveBots);
  byId('bot-behavior-save').hidden=!liveBots;
  byId('save').disabled=!editable||busy;
  byId('preflight').disabled=!editable||busy;
  byId('start').disabled=!editable||busy||Boolean(lastUpdate?.installing||lastUpdate?.restart_required||lastUpdate?.restart_pending);
  byId('stop').disabled=editable||busy;
  byId('edit-hint').textContent=editable?'Save settings, check the files, then start the session.':liveBots?'Bot combat rules can change live. Stop the session to change the roster or other settings.':'Stop the session to change its settings.';
  if(lastUpdate){
    const updating=lastUpdate.installing||lastUpdate.restart_pending;
    byId('update-check').disabled=busy||updateBusy||updating||lastUpdate.checking;
    byId('update-install').disabled=busy||updateBusy||updating||lastUpdate.checking||!editable||!lastUpdate.update_available||!lastUpdate.install_supported||lastUpdate.restart_required;
    byId('update-restart').disabled=busy||updateBusy||updating||!editable;
    byId('updates-enabled').disabled=busy||updateBusy||updating;
    byId('updates-auto-install').disabled=busy||updateBusy||updating||!lastUpdate.install_supported;
  }
}
function renderUpdates(value){
  lastUpdate=value;
  byId('update-panel').hidden=!value;if(!value)return;
  byId('update-version').textContent='v'+value.running_version;
  byId('updates-enabled').checked=value.enabled;
  byId('updates-auto-install').checked=value.auto_install;
  let status='Waiting for an update check…';
  if(value.restart_pending){status='Update installed. Restarting the control panel…';reconnecting=true;}
  else if(value.installing)status='Downloading and installing the release…';
  else if(value.checking)status='Checking GitLab…';
  else if(value.restart_required)status='v'+value.current_version+' is installed. Restart this panel to use it.';
  else if(value.error)status='The update could not be completed.';
  else if(value.update_available)status='v'+value.latest_version+' is available.'+(value.waiting_for_other_sessions?' Automatic installation is waiting for other sessions to stop.':value.waiting_for_stop?' Automatic installation is waiting for the session to stop.':'');
  else if(value.last_checked)status='No newer release is available.';
  else if(!value.enabled)status='Automatic update checks are disabled.';
  byId('update-status').textContent=status;
  byId('update-detail').textContent=[value.error,value.install_block_reason].filter(Boolean).join(' ');
  byId('update-restart').hidden=!value.restart_required||value.restart_pending;
  const link=byId('update-release');
  link.href=value.release_url?.startsWith('https://gitlab.com/codalilitari/jk-cross-server/')?value.release_url:'https://gitlab.com/codalilitari/jk-cross-server/-/releases';
  byId('update-checked').textContent=value.last_checked?'Last checked: '+new Date(value.last_checked).toLocaleString():'';
}
function byteLabel(value){
  if(!Number.isFinite(value)||value<0)return '—';
  if(value<1024)return value+' B';
  if(value<1024*1024)return (value/1024).toFixed(1)+' KiB';
  return (value/(1024*1024)).toFixed(1)+' MiB';
}
function renderAssets(value){
  const assets=value.browser_assets, panel=byId('asset-panel');
  panel.hidden=!assets;if(!assets)return;
  byId('asset-policy').textContent=assets.download_enabled?'Downloads enabled':'Downloads disabled';
  const labels={'ok':'Ready to send','ready':'Ready to send','retail':'Original game content','retail-only':'Uses original game content only','disabled':'Downloads disabled','no-mod':'No active mod','none':'No transferable content','missing':'File unavailable','not-gob':'Not a supported episode archive','too-big':'Exceeds browser download limit','too-many-files':'Exceeds browser file-count limit','local-required':'Matching pack required on each client','error':'Unavailable'};
  const offers=[];
  for(const [kind,title] of [['map','Episode'],['mod','Active mod'],['remastered','Required local pack']]){
    if(kind==='remastered'&&!assets[kind])continue;
    const item=assets[kind], box=document.createElement('div');box.className='asset-offer';
    const heading=document.createElement('strong');heading.textContent=title+(item?.name?' · '+item.name:'');box.append(heading);
    const detail=document.createElement('p');detail.className='hint';
    if(!item)detail.textContent='No active mod.';
    else{
      const parts=[labels[item.status]||item.status||'Preparing'];
      if(Number.isFinite(item.size))parts.push(byteLabel(item.size)+' installed');
      if(Number.isFinite(item.stream_size))parts.push(byteLabel(item.stream_size)+' transfer');
      if(item.retail_references)parts.push(item.retail_references+' original-content references');
      detail.textContent=parts.join(' · ');
    }
    box.append(detail);
    if(item?.sha256){const hash=document.createElement('p');hash.className='asset-hash';hash.textContent='SHA-256 '+item.sha256;box.append(hash);}
    offers.push(box);
  }
  byId('asset-offers').replaceChildren(...offers);
  const transfer=value.browser_transfer||{};
  byId('asset-transfer').textContent=(transfer.active_asset_transfers||0)+' active transfers · '+(transfer.asset_chunks||0)+' chunks sent · '+byteLabel(transfer.asset_bytes||0)+' sent this session';
}
function renderStatus(value){
  lastStatus=value;
  const state=byId('state');state.textContent=value.state;state.className='badge '+value.state;
  const seconds=value.uptime_seconds||0;
  byId('uptime').textContent=seconds?Math.floor(seconds/3600)+'h '+Math.floor(seconds%3600/60)+'m '+seconds%60+'s':'Local control panel';
  byId('native-status').textContent=value.native_connected?'Connected':'Offline';
  byId('retail-status').textContent=value.retail_ready?'Connected':config?.retail_enabled?'Waiting':'Disabled';
  byId('web-status').textContent=value.browser?'Listening':config?.web_enabled?'Offline':'Disabled';
  const game=value.browser?.games?.[0];
  byId('player-status').textContent=value.session?value.session.players+' / '+value.session.max:game?game.players+' / '+game.max:'—';
  const bots=value.bots;
  byId('bot-status').textContent=bots?.enabled?bots.joined_count+' / '+bots.configured_count+' · '+bots.state:'Disabled';
  byId('bot-player-detail').textContent=bots?.error||bots?.players?.map(player=>player.name+(player.joined?' · joined':' · joining')).join('  /  ')||'';
  const log=byId('logs'), atBottom=log.scrollHeight-log.scrollTop-log.clientHeight<50;
  log.textContent=value.logs?.map(row=>row.time+' ['+row.source+'] '+row.text).join('\n')||'No server output yet.';
  if(atBottom)log.scrollTop=log.scrollHeight;
  const play=byId('play-link');play.hidden=!value.browser;
  if(value.browser)play.href='http://127.0.0.1:'+config.web_port+'/';
  renderAssets(value);
  renderUpdates(value.updates);
  updateControls();
}
async function action(fn){
  if(busy)return;busy=true;updateControls();
  try{await fn();}catch(error){notice(error.message,'error');}
  finally{busy=false;updateControls();}
}
async function updateAction(fn){
  if(updateBusy||busy)return;updateBusy=true;updateControls();
  try{await fn();}catch(error){notice(error.message,'error');}
  finally{updateBusy=false;updateControls();}
}
async function save(){const value=await api('config','PUT',current());fill(value);return value;}
function authorityControls(){
  for(const node of byId('admin-keys-panel').querySelectorAll('button,input'))node.disabled=authorityBusy;
}
async function loadAuthority(){
  try{
    const value=await api('admin-keys');
    const active=value.credentials.filter(row=>row.status==='active').length;
    byId('admin-authority-state').textContent=value.server_id?
      active+' active credential(s) · Server '+value.server_id:'No keys issued. The first explicit issuance creates this server’s persistent authority.';
    byId('admin-key-list').replaceChildren(...value.credentials.map(row=>{
      const box=document.createElement('article');box.className='admin-key-row';
      const title=document.createElement('strong');title.textContent=row.label;
      const detail=document.createElement('p');detail.className='hint';
      detail.textContent=row.id+' · '+row.status+' · '+row.capabilities.map(c=>c==='match.next'?'Next level':'Kick players').join(', ');
      const dates=document.createElement('p');dates.className='hint';
      dates.textContent='Issued '+new Date(row.created_at).toLocaleString()+(row.last_used_at?' · Last used '+new Date(row.last_used_at).toLocaleString():'')+(row.revoked_at?' · Revoked '+new Date(row.revoked_at).toLocaleString():'');
      box.append(title,detail,dates);
      if(row.status==='active'){
        const controls=document.createElement('div');controls.className='admin-key-actions';
        const rotate=document.createElement('button');rotate.type='button';rotate.className='quiet';rotate.textContent='Rotate and download';
        rotate.addEventListener('click',()=>authorityAction(async()=>{await downloadCredential('admin-keys/'+row.id+'/rotate');notice('Replacement download prepared. The old key is revoked.');}));
        const revoke=document.createElement('button');revoke.type='button';revoke.className='danger';revoke.textContent='Revoke key';
        revoke.addEventListener('click',()=>authorityAction(async()=>{await api('admin-keys/'+row.id+'/revoke','POST');notice('Credential revoked. Further privileged commands using it are denied.');}));
        controls.append(rotate,revoke);box.append(controls);
      }
      return box;
    }));
  }catch(error){byId('admin-authority-state').textContent='Authority unavailable: '+error.message;}
}
async function downloadCredential(path,body){
  const headers={'Authorization':'Bearer '+token};
  if(body!==undefined)headers['Content-Type']='application/json';
  const response=await fetch('/api/'+path,{method:'POST',headers,body:body===undefined?undefined:JSON.stringify(body),cache:'no-store'});
  if(!response.ok){const result=await response.json();throw new Error(result.error||'Credential action failed.');}
  const match=/^attachment; filename="(jk-admin-key-[0-9a-f]{16}\.cog)"$/.exec(response.headers.get('Content-Disposition')||'');
  if(!match)throw new Error('Credential download headers are invalid. Revoke or rotate the new key if the download was lost.');
  const blob=await response.blob();
  const url=URL.createObjectURL(blob), link=document.createElement('a');
  link.href=url;link.download=match[1];document.body.append(link);
  try{link.click();}finally{link.remove();setTimeout(()=>URL.revokeObjectURL(url),250);}
  // No credential text is decoded, stored in DOM/config/storage, or logged.
}
async function authorityAction(fn){
  if(authorityBusy)return;authorityBusy=true;authorityControls();
  try{await fn();}catch(error){notice(error.message,'error');}
  finally{await loadAuthority();authorityBusy=false;authorityControls();}
}
byId('admin-keys-refresh').addEventListener('click',()=>authorityAction(async()=>{}));
byId('admin-key-form').addEventListener('submit',event=>{
  event.preventDefault();if(!event.currentTarget.reportValidity())return;
  const capabilities=[];if(byId('admin-cap-next').checked)capabilities.push('match.next');if(byId('admin-cap-kick').checked)capabilities.push('player.kick');
  if(!capabilities.length){notice('Choose at least one admin capability.','error');return;}
  authorityAction(async()=>{
    await downloadCredential('admin-keys',{label:byId('admin-key-label').value,capabilities});
    byId('admin-key-form').reset();notice('Private key download prepared. Keep it outside game content; it cannot be downloaded again.');
  });
});
byId('bot-behavior-save').addEventListener('click',()=>action(async()=>{
  const values=Object.fromEntries(behaviorKeys.map(key=>[key,form.elements.namedItem(key).checked]));
  const saved=await api('bots/behavior','PUT',values);
  Object.assign(config,saved);
  notice('Bot combat rules saved. Running bots reload the rules within one second.');
}));
form.addEventListener('submit',event=>{event.preventDefault();action(async()=>{await save();notice('Settings saved.');});});
form.elements.namedItem('episode').addEventListener('input',mapChoices);
form.elements.namedItem('game').addEventListener('change',()=>{
  const mots=form.elements.namedItem('game').value==='mots';
  form.elements.namedItem('episode').value=mots?'JKM_MP':'JK1MP';
  form.elements.namedItem('map').value=mots?'mdm02_freezer.jkl':'m2.jkl';
  form.elements.namedItem('rank').value=mots?'7':'0';
  updateRankHint();
  catalog=null;byId('episodes').replaceChildren();byId('maps').replaceChildren();
  notice('Select the matching game data folder, read its catalog, and choose a map.');
});
byId('catalog').addEventListener('click',()=>action(async()=>{
  catalog=await api('catalog','POST',{config:current()});
  const suffix=current().game==='mots'?'.goo':'.gob';
  const episodes=catalog.episodes.filter(e=>e.file.toLowerCase().endsWith(suffix));
  byId('episodes').replaceChildren(...episodes.map(e=>{const n=document.createElement('option');n.value=e.episode;n.label=e.maps.length+' maps';return n;}));
  mapChoices();
  notice(episodes.length+' episodes found. Choose an episode and map from the suggestions.'+(catalog.errors.length?' '+catalog.errors.length+' archive(s) could not be read.':''));
}));
byId('preflight').addEventListener('click',()=>action(async()=>{
  const result=await api('preflight','POST',{config:current()});
  notice('Files checked: '+result.episode+' → '+result.map+'\nSHA-256: '+result.episode_sha256);
}));
byId('start').addEventListener('click',()=>action(async()=>{
  if(!form.reportValidity())return;
  await save();notice('Starting the engine and enabled transports…');
  renderStatus(await api('start','POST'));notice('Session started.');
}));
byId('stop').addEventListener('click',()=>action(async()=>{
  notice('Stopping the session…');renderStatus(await api('stop','POST'));notice('Session stopped.');
}));
byId('update-check').addEventListener('click',()=>updateAction(async()=>{
  notice('Checking the published GitLab releases…');renderUpdates(await api('updates/check','POST'));
  notice(lastUpdate.update_available?'A newer release is available.':lastUpdate.error||'No newer release is available.',lastUpdate.error?'error':'success');
}));
byId('update-install').addEventListener('click',()=>action(async()=>{
  notice('Downloading and verifying the update…');renderUpdates(await api('updates/install','POST'));
  notice('Update installed. The control panel is restarting; the game session will stay stopped.');
}));
byId('update-restart').addEventListener('click',()=>action(async()=>{
  renderUpdates(await api('updates/restart','POST'));notice('Restarting the control panel…');
}));
for(const id of ['updates-enabled','updates-auto-install'])byId(id).addEventListener('change',()=>updateAction(async()=>{
  if(id==='updates-enabled'&&!byId(id).checked)byId('updates-auto-install').checked=false;
  if(id==='updates-auto-install'&&byId(id).checked)byId('updates-enabled').checked=true;
  renderUpdates(await api('updates/settings','PUT',{enabled:byId('updates-enabled').checked,auto_install:byId('updates-auto-install').checked}));
  notice('Update preferences saved.');
}));
async function poll(){try{renderStatus(await api('status'));}catch(error){byId('state').textContent=reconnecting?'Restarting':'Disconnected';notice(reconnecting?'Reconnecting after the update…':error.message,reconnecting?'success':'error');}}
(async()=>{try{
  const profiles=await api('bots/profiles');
  byId('bot-profiles').replaceChildren(...profiles.map(profile=>{
    const label=document.createElement('label'),input=document.createElement('input');
    input.type='checkbox';input.value=profile.id;input.name='bot_profile';
    label.append(input,document.createTextNode(profile.name.replace(/^Bot_/,'')));return label;
  }));
  fill(await api('config'));await poll();setInterval(poll,1500);await loadAuthority();
}catch(error){notice(error.message,'error');}})();

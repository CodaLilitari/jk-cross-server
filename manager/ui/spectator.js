(function(root,factory){
  'use strict';
  const observer=factory();
  if(typeof module==='object'&&module.exports)module.exports=observer;
  else root.jkSpectator=observer.mount(root.document,root);
})(typeof window==='undefined'?globalThis:window,function(){
  'use strict';
  const keys=new Set(['KeyW','KeyS','KeyA','KeyD','KeyQ','KeyE','ArrowLeft','ArrowRight','ArrowUp','ArrowDown']);
  const clamp=value=>Math.max(-Math.PI,Math.min(Math.PI,value));
  const uint=value=>Number.isInteger(value)&&value>0&&value<=0xffffffff;

  class ObserverInput {
    constructor(){this.world=0;this.control=0;this.sequence=0;this.held=new Set();this.yaw=0;this.pitch=0;}
    setEpoch(world,control){
      if(world===this.world&&control===this.control)return false;
      this.world=world;this.control=control;this.sequence=0;this.clear();return true;
    }
    clear(){this.held.clear();this.yaw=0;this.pitch=0;}
    key(code,down){if(!keys.has(code))return false;if(down)this.held.add(code);else this.held.delete(code);return true;}
    look(yaw,pitch){if(Number.isFinite(yaw))this.yaw=clamp(this.yaw+yaw);if(Number.isFinite(pitch))this.pitch=clamp(this.pitch+pitch);}
    packet(){
      const axis=(positive,negative)=>Number(this.held.has(positive))-Number(this.held.has(negative));
      const result={world_epoch:this.world,control_epoch:this.control,sequence:++this.sequence,
        forward:axis('KeyW','KeyS'),right:axis('KeyD','KeyA'),up:axis('KeyE','KeyQ'),
        yaw_delta:clamp(this.yaw+.09*axis('ArrowLeft','ArrowRight')),
        pitch_delta:clamp(this.pitch+.09*axis('ArrowUp','ArrowDown'))};
      this.yaw=0;this.pitch=0;return result;
    }
  }

  function parseTarget(value){
    if(typeof value!=='string'||!/^\d+:\d+$/.test(value))return null;
    const [peer_id,generation]=value.split(':').map(Number);
    return uint(peer_id)&&uint(generation)?{peer_id,generation}:null;
  }

  function olderSnapshot(current,incoming){
    return Boolean(current&&incoming.world_epoch&&incoming.control_epoch&&
      (incoming.world_epoch<current.world_epoch||
       (incoming.world_epoch===current.world_epoch&&incoming.control_epoch<current.control_epoch)));
  }

  function ownsControl(owned,status){
    return Boolean(owned&&status?.enabled&&status.mode==='free'&&
      owned.world_epoch===status.world_epoch&&owned.control_epoch===status.control_epoch);
  }

  function decodeFrame(headers,buffer,epoch,after){
    const number=name=>{
      const value=headers.get(name);
      if(value===null||!/^\d+$/.test(value))throw new Error('Invalid spectator frame header.');
      const result=Number(value);
      if(!uint(result))throw new Error('Invalid spectator frame number.');
      return result;
    };
    const width=number('X-JK-Frame-Width'),height=number('X-JK-Frame-Height');
    const sequence=number('X-JK-Frame-Sequence');
    const world=number('X-JK-World-Epoch'),control=number('X-JK-Control-Epoch');
    if(width>640||height>360||buffer.byteLength!==width*height*4)throw new Error('Invalid spectator frame size.');
    if(world!==epoch.world_epoch||control!==epoch.control_epoch||sequence<=after)throw new Error('Expired spectator frame.');
    return {width,height,sequence,pixels:new Uint8ClampedArray(buffer)};
  }

  function mount(document,window){
    const byId=id=>document.getElementById(id);
    const panel=byId('spectator-panel');
    if(!panel)return {updateStatus(){}};
    const token=document.querySelector('meta[name="admin-token"]').content;
    const canvas=byId('spectator-canvas'),context=canvas.getContext('2d',{alpha:false});
    const toggle=byId('spectator-toggle'),mode=byId('spectator-mode'),target=byId('spectator-target');
    const input=new ObserverInput();
    let status=null,serverActive=false,controlBusy=false,statusBusy=false,inputBusy=false,frameBusy=false;
    let revision=0,frameSequence=0,message='',releasePending=false,lastRoster='',pointer=null,enginePid=null,lastInputAt=0,lastFrameAt=0,videoUnavailable=true,owned=null;

    function clearFrame(){
      frameSequence=0;lastFrameAt=0;videoUnavailable=true;context.fillStyle='#060a07';context.fillRect(0,0,canvas.width,canvas.height);
      byId('spectator-overlay').hidden=false;
      byId('spectator-frame-detail').textContent='Waiting for a frame';
    }
    function release(){
      input.clear();pointer=null;releasePending=true;
      for(const button of panel.querySelectorAll('[data-spectator-key]'))button.classList.remove('held');
      void sendInput(true);
    }
    async function request(path,method='GET',body,raw=false){
      const controller=new AbortController(),timeout=window.setTimeout(()=>controller.abort(),2500);
      try{
        const headers={Authorization:'Bearer '+token};
        if(body!==undefined)headers['Content-Type']='application/json';
        const response=await window.fetch('/api/spectator'+path,{method,headers,
          body:body===undefined?undefined:JSON.stringify(body),cache:'no-store',signal:controller.signal});
        if(response.status===401){window.location.reload();throw new Error('Reconnecting to the control panel…');}
        if(raw&&response.ok)return response;
        const result=await response.json();
        if(!response.ok){const error=new Error(result.error||'Spectator request failed.');error.status=response.status;throw error;}
        return result;
      }finally{window.clearTimeout(timeout);}
    }
    function render(){
      const enabled=serverActive&&status?.enabled===true;
      toggle.textContent=controlBusy?'Applying…':enabled?'Close spectator':'Open spectator';
      toggle.disabled=controlBusy||!serverActive||(!enabled&&!status?.available);
      toggle.setAttribute('aria-expanded',String(enabled));
      byId('spectator-view').hidden=!enabled;
      mode.disabled=controlBusy||!serverActive||!status?.available;
      target.disabled=controlBusy||mode.value!=='follow'||!status?.players?.length||!serverActive;
      byId('spectator-follow-choice').disabled=!status?.players?.length;
      byId('spectator-movement').hidden=!enabled||status.mode!=='free';
      byId('spectator-take-control').hidden=!enabled||status.mode!=='free'||ownsControl(owned,status);
      byId('spectator-take-control').disabled=controlBusy;
      for(const button of panel.querySelectorAll('[data-spectator-key]'))button.disabled=!ownsControl(owned,status)||controlBusy;
      const label=enabled?(status.mode==='follow'?'Following player':'Free camera'):status?.available?'Ready':'Unavailable';
      byId('spectator-state').textContent=label;
      byId('spectator-state').className='badge'+(enabled?' running':'');
      byId('spectator-message').textContent=message||status?.reason||(!serverActive?'Start a session to observe the game.':enabled?(status.mode==='follow'?'Following the selected player.':ownsControl(owned,status)?'Free flight is active.':'Take camera control to move this open view.'):'Spectator view is closed.');
      const pose=status?.pose,position=pose?.position;
      byId('spectator-position').textContent=enabled&&Array.isArray(position)&&position.every(Number.isFinite)?
        'Position '+position.map(n=>n.toFixed(2)).join(' / ')+' · '+(pose.sector<0?'Outside the level':'Sector '+pose.sector):'';
      const stale=videoUnavailable||!lastFrameAt||Date.now()-lastFrameAt>2500;
      byId('spectator-overlay').hidden=!stale&&!(pose?.sector<0);
      byId('spectator-overlay').textContent=enabled&&pose?.sector<0?'Outside the level — fly back toward the map.':frameSequence?'Waiting for a fresh frame…':'Waiting for the game view…';
    }
    function applySnapshot(value){
      if(!value||!Number.isInteger(value.world_epoch)||!Number.isInteger(value.control_epoch))return;
      if(olderSnapshot({world_epoch:input.world,control_epoch:input.control},value))return;
      const changed=value.world_epoch&&value.control_epoch&&input.setEpoch(value.world_epoch,value.control_epoch);
      if(changed){input.clear();pointer=null;clearFrame();}
      status=value;
      if(!ownsControl(owned,value))owned=null;
      if(value.frame)videoUnavailable=value.frame.available===false;
      if(value.enabled)mode.value=value.mode;
      if(!value.enabled||!value.available){input.clear();clearFrame();}
      const players=Array.isArray(value.players)?value.players:[];
      const roster=JSON.stringify(players);
      if(roster!==lastRoster){
        const previous=target.value;lastRoster=roster;
        const options=players.map(player=>{const option=document.createElement('option');option.value=player.peer_id+':'+player.generation;option.textContent=player.name||'Player '+player.slot;return option;});
        if(!options.length){const option=document.createElement('option');option.value='';option.textContent='No joined players';options.push(option);}
        target.replaceChildren(...options);
        if(players.some(player=>player.peer_id+':'+player.generation===previous))target.value=previous;
      }
      if(value.mode==='follow'&&value.target)target.value=value.target.peer_id+':'+value.target.generation;
      if(!value.enabled&&mode.value==='follow'&&!players.length)mode.value='free';
      render();
    }
    async function refresh(){
      if(statusBusy||controlBusy||!serverActive)return;
      statusBusy=true;const started=revision;
      try{const value=await request('');if(started===revision&&serverActive)applySnapshot(value);}
      catch(error){if(started===revision){message=error.name==='AbortError'?'Spectator status timed out.':error.message;render();}}
      finally{statusBusy=false;}
    }
    async function configure(nextMode){
      if(controlBusy||!status||!serverActive)return;
      const selected=nextMode==='follow'?parseTarget(target.value):null;
      if(nextMode==='follow'&&!selected){message='Choose a joined player to follow.';render();return;}
      controlBusy=true;input.clear();pointer=null;message='';const started=++revision;render();
      try{
        const value=await request('','PUT',{world_epoch:status.world_epoch,control_epoch:status.control_epoch,mode:nextMode,target:selected});
        if(started===revision&&serverActive){owned=value.enabled&&value.mode==='free'?{world_epoch:value.world_epoch,control_epoch:value.control_epoch}:null;applySnapshot(value);if(value.enabled)canvas.focus({preventScroll:true});}
      }catch(error){if(started===revision){message=error.message;}}
      finally{controlBusy=false;render();void refresh();}
    }
    async function sendInput(force=false){
      if(inputBusy||controlBusy||!serverActive||!ownsControl(owned,status)||(document.hidden&&!force))return;
      if(!force&&Date.now()-lastInputAt<95)return;
      lastInputAt=Date.now();
      inputBusy=true;releasePending=false;const started=revision;
      try{const value=await request('/input','PUT',input.packet());if(started===revision&&serverActive)applySnapshot(value);}
      catch(error){
        if(started===revision){if(error.status!==429){input.clear();message=error.message;render();}if(error.status===409)void refresh();}
      }finally{inputBusy=false;if(releasePending)void sendInput(true);}
    }
    async function fetchFrame(){
      if(frameBusy||controlBusy||!serverActive||!status?.enabled||document.hidden)return;
      frameBusy=true;const started=revision;
      const epoch={world_epoch:status.world_epoch,control_epoch:status.control_epoch};
      try{
        const response=await request('/frame?after='+frameSequence+'&world_epoch='+epoch.world_epoch+'&control_epoch='+epoch.control_epoch,'GET',undefined,true);
        if(response.status===204)return;
        const buffer=await response.arrayBuffer();
        if(started!==revision||!serverActive||!status?.enabled||epoch.world_epoch!==status.world_epoch||epoch.control_epoch!==status.control_epoch)return;
        const frame=decodeFrame(response.headers,buffer,epoch,frameSequence);
        if(canvas.width!==frame.width||canvas.height!==frame.height){canvas.width=frame.width;canvas.height=frame.height;}
        context.putImageData(new ImageData(frame.pixels,frame.width,frame.height),0,0);frameSequence=frame.sequence;lastFrameAt=Date.now();videoUnavailable=false;
        byId('spectator-frame-detail').textContent=frame.width+' × '+frame.height+' · Frame '+frame.sequence;
        message='';render();
      }catch(error){
        if(started===revision){videoUnavailable=true;message=error.name==='AbortError'?'Waiting for the spectator video…':error.message;render();if(error.status===409)void refresh();}
      }finally{frameBusy=false;}
    }
    // Event wiring is kept below the state machine so all releases share one path.
    toggle.addEventListener('click',()=>void configure(status?.enabled?'off':mode.value));
    byId('spectator-take-control').addEventListener('click',()=>void configure('free'));
    mode.addEventListener('change',()=>{release();render();if(status?.enabled)void configure(mode.value);});
    target.addEventListener('change',()=>{if(status?.enabled&&mode.value==='follow')void configure('follow');});
    canvas.addEventListener('keydown',event=>{
      if(ownsControl(owned,status)&&input.key(event.code,true))event.preventDefault();
      if(event.code==='Escape')release();
    });
    window.addEventListener('keyup',event=>{if(input.key(event.code,false)&&status?.enabled&&status.mode==='free')void sendInput();});
    canvas.addEventListener('blur',release);
    canvas.addEventListener('pointerdown',event=>{
      if(!ownsControl(owned,status)||event.button!==0)return;
      canvas.focus({preventScroll:true});canvas.setPointerCapture(event.pointerId);pointer={id:event.pointerId,x:event.clientX,y:event.clientY};event.preventDefault();
    });
    canvas.addEventListener('pointermove',event=>{
      if(!pointer||pointer.id!==event.pointerId)return;
      input.look((pointer.x-event.clientX)*.006,(pointer.y-event.clientY)*.006);
      pointer.x=event.clientX;pointer.y=event.clientY;
    });
    canvas.addEventListener('pointerup',event=>{if(pointer?.id===event.pointerId)pointer=null;});
    canvas.addEventListener('pointercancel',release);
    for(const button of panel.querySelectorAll('[data-spectator-key]')){
      button.addEventListener('pointerdown',event=>{
        if(!ownsControl(owned,status))return;
        event.preventDefault();button.setPointerCapture(event.pointerId);input.key(button.dataset.spectatorKey,true);button.classList.add('held');
      });
      const lift=()=>{input.key(button.dataset.spectatorKey,false);button.classList.remove('held');void sendInput();};
      button.addEventListener('pointerup',lift);button.addEventListener('pointercancel',lift);
      button.addEventListener('keydown',event=>{if(event.code==='Space'||event.code==='Enter'){event.preventDefault();input.key(button.dataset.spectatorKey,true);button.classList.add('held');}});
      button.addEventListener('keyup',event=>{if(event.code==='Space'||event.code==='Enter'){event.preventDefault();lift();}});
      button.addEventListener('blur',lift);
    }
    window.addEventListener('blur',release);
    document.addEventListener('visibilitychange',()=>{release();if(!document.hidden)void refresh();});
    window.setInterval(()=>void refresh(),1000);
    window.setInterval(()=>void sendInput(),100);
    window.setInterval(()=>void fetchFrame(),200);
    clearFrame();render();
    return {updateStatus(value){
      const active=value.state==='running'&&value.native_connected===true&&value.session_ready!==false;
      const pid=value.processes?.engine?.pid??null;
      if(pid!==enginePid){revision++;input.setEpoch(0,0);status=null;owned=null;serverActive=false;lastRoster='';clearFrame();enginePid=pid;}
      if(!active){if(serverActive){revision++;input.clear();pointer=null;status=null;clearFrame();}serverActive=false;message='';render();return;}
      const justStarted=!serverActive;serverActive=true;
      if(value.spectator&&!controlBusy)applySnapshot(value.spectator);
      if(justStarted)void refresh();
    }};
  }
  return {ObserverInput,parseTarget,decodeFrame,olderSnapshot,ownsControl,mount};
});

'use strict';
(() => {
  const HEADER='# JK Cross Server offline admin credential. Keep outside game content.';
  const PREFIX='# JKADMIN-KEY-V1 ';
  const FIELDS=['capabilities','format','key_id','label','secret','server_id','version'];
  const CAPS=['match.next','player.kick'];
  function validate(value){
    if(!value||typeof value!=='object'||Array.isArray(value)||JSON.stringify(Object.keys(value).sort())!==JSON.stringify(FIELDS))throw new Error('The credential metadata schema is invalid.');
    if(value.format!=='JKADMIN-KEY'||value.version!==1)throw new Error('This credential version is unsupported.');
    for(const [name,length] of [['server_id',32],['key_id',16],['secret',64]])if(typeof value[name]!=='string'||!(new RegExp('^[0-9a-f]{'+length+'}$')).test(value[name]))throw new Error('The credential identifiers or secret have an invalid format.');
    if(typeof value.label!=='string'||value.label!==value.label.trim()||!/^[\x20-\x7e]{1,80}$/.test(value.label))throw new Error('The credential label is invalid.');
    const caps=value.capabilities;
    if(!Array.isArray(caps)||caps.length<1||caps.length>2||caps.some(c=>typeof c!=='string'||!CAPS.includes(c))||JSON.stringify(caps)!==JSON.stringify([...new Set(caps)].sort()))throw new Error('The credential capability list is invalid.');
    return value;
  }
  function parseCredential(text){
    if(typeof text!=='string'||text.length>16384||/[^\x00-\x7f]/.test(text))throw new Error('Choose an unmodified issued key file.');
    const lines=text.replace(/\r\n/g,'\n').split('\n');if(lines.at(-1)==='')lines.pop();
    if(lines.length!==6||lines[0]!==HEADER||!lines[1].startsWith(PREFIX)||JSON.stringify(lines.slice(2))!==JSON.stringify(['symbols','end','code','end']))throw new Error('The key must be the inert issued credential container.');
    const encoded=lines[1].slice(PREFIX.length);let value;
    try{value=JSON.parse(encoded);}catch(_){throw new Error('The credential metadata is not valid JSON.');}
    validate(value);
    if(encoded!==JSON.stringify(value,FIELDS))throw new Error('The credential metadata has been changed or duplicated.');
    return value;
  }
  async function proofFor(value,challenge,cryptoProvider=globalThis.crypto){
    validate(value);
    const match=typeof challenge==='string'?/^JKADMIN1:([0-9a-f]{32}):([0-9a-f]{32})$/.exec(challenge):null;
    if(!match)throw new Error('Paste the complete JKADMIN1 challenge exactly.');
    if(match[1]!==value.server_id)throw new Error('This challenge belongs to a different server.');
    if(!cryptoProvider?.subtle)throw new Error('Web Crypto is unavailable here. Use the offline Python helper.');
    const bytes=Uint8Array.from(value.secret.match(/../g),c=>parseInt(c,16));
    try{
      const key=await cryptoProvider.subtle.importKey('raw',bytes,{name:'HMAC',hash:'SHA-256'},false,['sign']);
      const input=new TextEncoder().encode('JKADMIN1\n'+match[1]+'\n'+match[2]+'\n'+value.key_id);
      const signature=await cryptoProvider.subtle.sign('HMAC',key,input);
      const mac=[...new Uint8Array(signature)].map(b=>b.toString(16).padStart(2,'0')).join('');
      return 'admin prove '+value.key_id+' '+mac;
    }finally{bytes.fill(0);}
  }
  // Node's standard Web Crypto runs the same helper in deterministic tests.
  if(typeof module!=='undefined'&&module.exports){module.exports={parseCredential,proofFor};return;}
  const byId=id=>document.getElementById(id);
  const form=byId('proof-form'), output=byId('proof'), message=byId('message');
  function clearOutput(){output.value='';byId('copy').disabled=true;}
  for(const id of ['key-file','challenge'])byId(id).addEventListener('input',clearOutput);
  form.addEventListener('submit',async event=>{
    event.preventDefault();clearOutput();message.className='';byId('generate').disabled=true;
    let text='',credential=null;
    try{
      const file=byId('key-file').files[0];
      if(!file||file.size>16384)throw new Error('Select an issued key file smaller than 16 KiB.');
      text=await file.text();credential=parseCredential(text);
      output.value=await proofFor(credential,byId('challenge').value);
      byId('copy').disabled=false;message.textContent='Proof ready for this server. Copy the complete line into game chat.';
    }catch(error){message.className='error';message.textContent=error.message;}
    finally{if(credential)credential.secret='';credential=null;text='';byId('generate').disabled=false;}
  });
  byId('copy').addEventListener('click',async()=>{
    try{await navigator.clipboard.writeText(output.value);message.textContent='Proof copied.';}
    catch(_){output.focus();output.select();message.textContent='Select and copy the highlighted proof with your normal keyboard shortcut.';}
  });
  byId('clear').addEventListener('click',()=>{form.reset();clearOutput();message.className='';message.textContent='Cleared. No key is retained by this page.';});
})();

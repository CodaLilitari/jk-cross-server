'use strict';
(async function(){
  const canvas=document.getElementById('geometry'),result=document.getElementById('result');
  try{
    const [data,metadata]=await Promise.all([fetch('spectator_geometry.jksg').then(r=>r.arrayBuffer()),fetch('spectator_geometry.json').then(r=>r.json())]);
    const frame=JKSGGeometry.decodeGeometry(data,{world_epoch:7,control_epoch:3},0);
    const renderer=JKSGGeometry.createRenderer(canvas,{onContextLost(){
      window.fixtureResult={passed:false,contextLost:true};result.className='fail';result.textContent='WebGL context lost. Production UI must return to image view; reload this isolated fixture to restore its context.';
    }});
    window.fixtureRenderer=renderer;window.fixtureFrame=frame;
    function draw(){
      renderer.draw(frame);
      const gl=canvas.getContext('webgl2'),checks=metadata.checks.map(check=>{
        const pixel=new Uint8Array(4);gl.readPixels(check.x,frame.height-1-check.y,1,1,gl.RGBA,gl.UNSIGNED_BYTE,pixel);
        return {...check,actual:[...pixel],passed:check.rgba.every((v,i)=>Math.abs(pixel[i]-v)<=1)};
      });
      const error=gl.getError(),passed=checks.every(c=>c.passed)&&error===gl.NO_ERROR;
      window.fixtureResult={passed,error,checks,width:frame.width,height:frame.height,sequence:frame.sequence,vertices:frame.vertices.byteLength/20,indices:frame.indices.length};
      result.className=passed?'pass':'fail';
      result.textContent=(passed?'PASS':'FAIL')+' — actual WebGL 2 GPU readback, '+frame.indices.length+' indices / '+frame.vertices.byteLength/20+' vertices\n'+
        checks.map(c=>(c.passed?'PASS ':'FAIL ')+c.label+' at '+c.x+','+c.y+': '+c.actual.join(',')).join('\n')+'\nWebGL error: '+error;
    }
    document.getElementById('redraw').addEventListener('click',draw);
    document.getElementById('lose').addEventListener('click',()=>{
      const extension=canvas.getContext('webgl2').getExtension('WEBGL_lose_context');
      if(extension)extension.loseContext();else result.textContent='WEBGL_lose_context extension is unavailable.';
    });
    draw();
  }catch(error){window.fixtureResult={passed:false,error:error.message};result.className='fail';result.textContent='FAIL — '+error.message;}
})();

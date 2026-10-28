(function(root,factory){
  'use strict';
  const geometry=factory();
  if(typeof module==='object'&&module.exports)module.exports=geometry;
  else root.JKSGGeometry=geometry;
})(typeof window==='undefined'?globalThis:window,function(){
  'use strict';
  const HEADER_BYTES=64,MAX_PAYLOAD=2097152,MAX_AGE_MS=2000;
  // Validate the complete fixed JKSG v1 envelope before allocating index storage
  // or exposing any attributes to WebGL. Clip coordinates are already projected.
  function decodeGeometry(buffer,epoch,after,elapsedMs=0){
    if(!(buffer instanceof ArrayBuffer)||buffer.byteLength<HEADER_BYTES||buffer.byteLength>HEADER_BYTES+MAX_PAYLOAD)
      throw new Error('Invalid geometry envelope size.');
    if(!Number.isInteger(after)||after<0||after>0xffffffff)throw new Error('Invalid geometry sequence cursor.');
    if(!Number.isFinite(elapsedMs)||elapsedMs<0)throw new Error('Invalid geometry transfer age.');
    const view=new DataView(buffer),word=offset=>view.getUint32(offset,true);
    if(word(0)!==0x47534b4a||word(4)!==1)throw new Error('Unsupported geometry envelope.');
    const width=word(8),height=word(12),world=word(16),control=word(20),sequence=word(24);
    const length=word(28),flags=word(32),age_ms=word(36)+elapsedMs,vertexCount=word(40),indexCount=word(44);
    if(!width||width>640||!height||height>360||!world||!control||!sequence||
       flags||word(48)||word(52)||word(56)||word(60))throw new Error('Invalid geometry header.');
    if(!epoch||world!==epoch.world_epoch||control!==epoch.control_epoch||sequence<=after||age_ms>MAX_AGE_MS)
      throw new Error('Expired geometry frame.');
    if(vertexCount>65536||indexCount>196608||indexCount%3||
       (!vertexCount)!==(!indexCount)||length!==20*vertexCount+4*indexCount||
       length>MAX_PAYLOAD||buffer.byteLength!==HEADER_BYTES+length)throw new Error('Invalid geometry counts or payload length.');
    for(let vertex=0;vertex<vertexCount;vertex++){
      const offset=HEADER_BYTES+vertex*20;
      for(let component=0;component<4;component++){
        if(!Number.isFinite(view.getFloat32(offset+component*4,true)))throw new Error('Nonfinite geometry coordinate.');
      }
      if(view.getUint8(offset+19)!==255)throw new Error('Unsupported geometry alpha.');
    }
    const indexOffset=HEADER_BYTES+vertexCount*20;
    // Validate every index before creating the typed array. Decode explicitly as
    // little endian rather than assuming the incoming buffer's alignment.
    for(let index=0;index<indexCount;index++){
      if(word(indexOffset+index*4)>=vertexCount)throw new Error('Geometry index is out of bounds.');
    }
    const indices=new Uint32Array(indexCount);
    for(let index=0;index<indexCount;index++)indices[index]=word(indexOffset+index*4);
    return {width,height,world_epoch:world,control_epoch:control,sequence,age_ms,
      vertices:new Uint8Array(buffer,HEADER_BYTES,vertexCount*20),indices};
  }

  // createRenderer(canvas,{onContextLost}) -> {draw(decodedFrame),clear(),dispose()}.
  // Owns one WebGL 2 context's program, VAO and two bounded frame buffers.
  function createRenderer(canvas,{onContextLost=()=>{}}={}){
    const gl=canvas.getContext('webgl2',{alpha:false,antialias:false,depth:true,preserveDrawingBuffer:false});
    if(!gl||gl.isContextLost())throw new Error('WebGL 2 is unavailable. Showing the image view.');
    let program=null,vao=null,vertexBuffer=null,indexBuffer=null,lost=false,disposed=false;
    const shaders=[];
    function compile(type,source){
      const shader=gl.createShader(type);
      if(!shader)throw new Error('WebGL shader allocation failed.');
      shaders.push(shader);gl.shaderSource(shader,source);gl.compileShader(shader);
      if(!gl.getShaderParameter(shader,gl.COMPILE_STATUS))throw new Error('WebGL geometry shader compilation failed.');
      return shader;
    }
    function dispose(){
      if(disposed)return;
      disposed=true;canvas.removeEventListener('webglcontextlost',contextLost);
      if(vertexBuffer)gl.deleteBuffer(vertexBuffer);
      if(indexBuffer)gl.deleteBuffer(indexBuffer);
      if(vao)gl.deleteVertexArray(vao);
      if(program)gl.deleteProgram(program);
      for(const shader of shaders)gl.deleteShader(shader);
    }
    function contextLost(event){event.preventDefault();lost=true;onContextLost();}
    function clear(){
      if(lost||disposed)return;
      gl.viewport(0,0,canvas.width,canvas.height);
      gl.depthMask(true);gl.clearDepth(1);gl.clearColor(6/255,10/255,7/255,1);
      gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
    }
    try{
      const vertex=compile(gl.VERTEX_SHADER,'#version 300 es\nlayout(location=0) in vec4 clipPosition;\nlayout(location=1) in vec4 vertexColour;\nout vec4 colour;\nvoid main(){gl_Position=clipPosition;colour=vertexColour;}');
      const fragment=compile(gl.FRAGMENT_SHADER,'#version 300 es\nprecision mediump float;\nin vec4 colour;\nout vec4 outputColour;\nvoid main(){outputColour=vec4(colour.rgb,1.0);}');
      program=gl.createProgram();
      if(!program)throw new Error('WebGL geometry program allocation failed.');
      gl.attachShader(program,vertex);gl.attachShader(program,fragment);gl.linkProgram(program);
      if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw new Error('WebGL geometry shader linking failed.');
      vao=gl.createVertexArray();vertexBuffer=gl.createBuffer();indexBuffer=gl.createBuffer();
      if(!vao||!vertexBuffer||!indexBuffer)throw new Error('WebGL geometry buffer allocation failed.');
      gl.bindVertexArray(vao);gl.bindBuffer(gl.ARRAY_BUFFER,vertexBuffer);gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,indexBuffer);
      gl.enableVertexAttribArray(0);gl.vertexAttribPointer(0,4,gl.FLOAT,false,20,0);
      gl.enableVertexAttribArray(1);gl.vertexAttribPointer(1,4,gl.UNSIGNED_BYTE,true,20,16);
      canvas.addEventListener('webglcontextlost',contextLost);
      clear();
    }catch(error){dispose();throw error;}
    function draw(frame){
      if(disposed||lost||gl.isContextLost())throw new Error('WebGL geometry context is lost. Showing the image view.');
      if(canvas.width!==frame.width||canvas.height!==frame.height){canvas.width=frame.width;canvas.height=frame.height;}
      gl.useProgram(program);gl.bindVertexArray(vao);
      gl.bindBuffer(gl.ARRAY_BUFFER,vertexBuffer);gl.bufferData(gl.ARRAY_BUFFER,frame.vertices,gl.STREAM_DRAW);
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,indexBuffer);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,frame.indices,gl.STREAM_DRAW);
      gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LESS);gl.depthMask(true);gl.disable(gl.BLEND);gl.disable(gl.CULL_FACE);
      clear();
      if(frame.indices.length)gl.drawElements(gl.TRIANGLES,frame.indices.length,gl.UNSIGNED_INT,0);
    }
    return {draw,clear,dispose};
  }
  return {decodeGeometry,createRenderer};
});

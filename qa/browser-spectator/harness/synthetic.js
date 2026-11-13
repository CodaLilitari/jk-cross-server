const {chromium}=require('/opt/codex/runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const {spawn}=require('node:child_process');
const fs=require('node:fs');
const path=require('node:path');
(async()=>{
 const out=__dirname,repo='/workspace/scratch/55e850edc256/jk-browser-spectator',port=48173;
 const log=fs.openSync(path.join(out,'static-server.log'),'w');
 const server=spawn('python3',['-m','http.server',String(port),'--bind','127.0.0.1','--directory',repo],{stdio:['ignore',log,log]});
 let browser;const errors=[];const consoles=[];
 try{
  for(let n=0;n<50;n++){try{if((await fetch(`http://127.0.0.1:${port}/`)).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}
  browser=await chromium.launch({executablePath:'/tmp/jk-chrome/chrome-linux64/chrome',headless:true,args:['--no-sandbox','--enable-unsafe-swiftshader','--use-gl=angle','--use-angle=swiftshader']});
  const page=await browser.newPage({viewport:{width:1000,height:900}});
  page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')consoles.push(m.text());});
  await page.goto(`http://127.0.0.1:${port}/tests/fixtures/spectator_geometry.html`);
  await page.waitForFunction(()=>window.fixtureResult,{timeout:15000});
  const result=await page.evaluate(()=>{const gl=document.querySelector('canvas').getContext('webgl2');const ext=gl?.getExtension('WEBGL_debug_renderer_info');return {fixture:window.fixtureResult,webgl:gl?{version:gl.getParameter(gl.VERSION),renderer:gl.getParameter(ext?ext.UNMASKED_RENDERER_WEBGL:gl.RENDERER)}:null};});
  await page.screenshot({path:path.join(out,'synthetic-webgl.png'),fullPage:true});
  const before=result.fixture;await page.click('#lose');await page.waitForFunction(()=>window.fixtureResult.contextLost===true,{timeout:5000});
  const loss=await page.evaluate(()=>window.fixtureResult);
  const receipt={utc:new Date().toISOString(),browser:await browser.version(),...result,context_loss_observed:loss.contextLost===true,page_errors:errors,console_errors:consoles,passed:before.passed&&loss.contextLost===true&&errors.length===0};
  fs.writeFileSync(path.join(out,'synthetic-webgl.json'),JSON.stringify(receipt,null,2)+'\n');console.log(JSON.stringify(receipt));if(!receipt.passed)process.exitCode=1;
 }catch(e){console.error(e.stack);process.exitCode=1;}
 finally{if(browser)await browser.close();server.kill('SIGTERM');fs.closeSync(log);}
})();

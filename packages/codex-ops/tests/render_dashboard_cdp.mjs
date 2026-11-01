import {spawn} from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'codex-ops-v06-cdp-'));
const process = spawn('C:/Program Files/Google/Chrome/Application/chrome.exe',
  ['--headless', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--remote-debugging-port=0', '--user-data-dir=' + profile,
    pathToFileURL(path.join(root,'verification/dashboard-v06.html')).href],
  {windowsHide:true, stdio:'ignore'});
let socket;
try {
  const portFile = path.join(profile, 'DevToolsActivePort');
  for(let i=0; i<100 && !fs.existsSync(portFile); i++) await new Promise(r=>setTimeout(r,50));
  const port = fs.readFileSync(portFile,'utf8').split('\n')[0];
  const pages = await (await fetch('http://127.0.0.1:' + port + '/json')).json();
  const page=pages.find(value=>value.type==='page' && value.url.startsWith('file:'));
  if(!page)throw Error('Owned dashboard page is missing');
  socket = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
  let id=0; const pending=new Map();
  socket.addEventListener('message',event=>{const value=JSON.parse(event.data);const p=pending.get(value.id);if(p){pending.delete(value.id);value.error?p.reject(value.error):p.resolve(value.result);}});
  const call=(method,params={})=>new Promise((resolve,reject)=>{const key=++id;pending.set(key,{resolve,reject});socket.send(JSON.stringify({id:key,method,params}));});
  await call('Page.enable');
  const reports=[];
  for(const width of [1280,420]) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:1100,deviceScaleFactor:1,mobile:false});
    for(let i=0;i<50;i++) {
      const ready=await call('Runtime.evaluate',{expression:'document.readyState === "complete" && !!document.getElementById("installation")',returnByValue:true});
      if(ready.result.value===true)break;
      await new Promise(r=>setTimeout(r,100));
    }
    const result=await call('Runtime.evaluate',{expression:'JSON.stringify({width:innerWidth,scroll:document.documentElement.scrollWidth,installation:document.getElementById("installation").textContent,body:document.body.textContent.includes("当前观察进程桥接")})',returnByValue:true});
    if(!result.result.value){const context=await call('Runtime.evaluate',{expression:'JSON.stringify({url:location.href,title:document.title,body:document.body?.innerText.slice(0,300)})',returnByValue:true});throw Error(JSON.stringify(context));}
    const metrics=JSON.parse(result.result.value);
    if(metrics.width!==width || metrics.scroll>width || !metrics.body)throw Error(JSON.stringify(metrics));
    const png=await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});
    const target=path.join(root,'verification','dashboard-v06-cdp-'+width+'.png');
    fs.writeFileSync(target,Buffer.from(png.data,'base64'));
    reports.push({...metrics,screenshot:target});
  }
  const filter=await call('Runtime.evaluate',{expression:'(()=>{const e=document.getElementById("filter");e.value="nonexistent-verification-filter";e.dispatchEvent(new Event("input"));return document.querySelector("#outputs tbody").textContent;})()',returnByValue:true});
  if(!filter.result.value.includes('没有匹配的来源'))throw Error('Filter failed');
  fs.writeFileSync(path.join(root,'verification/dashboard-v06-browser.json'),JSON.stringify({reports,filterVerified:true,ownedProfile:profile,usedActualCdpViewport:true},null,2));
  console.log(JSON.stringify({widths:reports.map(x=>x.width),noHorizontalOverflow:true,filterVerified:true}));
  await call('Browser.close').catch(()=>{});
} finally {
  socket?.close();
  process.kill();
}

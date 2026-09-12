import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import '../web/status.js';

const app=readFileSync(new URL('../web/app.js',import.meta.url),'utf8');
function harness(){
 const timers=new Map(),notices=[];let timerId=0,draws=0,calls=0;
 const ctx=vm.createContext({
  BuiltWatchStatus, window:{}, document:{hidden:false,activeElement:{tagName:'BODY'}},
  BuiltWatchDemo:{get:()=>({demo:true,systems:[]})}, activeModal:null,
  session:{signed_in:true,admitted:true},state:{demo:false,job:{status:'running'}},view:'guide',
  forceDemo:false,globalImpact:null,pollTimer:null,
  setTimeout:(fn,delay)=>{const id=++timerId;timers.set(id,{fn,delay});return id;},
  clearTimeout:id=>timers.delete(id),render:()=>draws++,toast:s=>notices.push(s),connectionError:()=>{},
  api:async path=>{calls++;return path==='/api/session'?{signed_in:true}:path==='/api/workspace'?{demo:false,job:{status:'complete'}}:{};},
 });
 vm.runInContext(app.slice(app.indexOf('let refreshVersion=0;'),app.indexOf('let modalHistory=')),ctx);
 vm.runInContext(app.slice(app.indexOf('async function refresh(){'),app.indexOf('\nconst systemName')),ctx);
 return {ctx,timers,notices,get draws(){return draws;},get calls(){return calls;}};
}
test('returning from Docs schedules a refresh and switches from active-job to idle cadence',async()=>{
 const h=harness();
 h.ctx.scheduleRefresh();assert.equal(h.timers.size,0);
 h.ctx.view='systems';h.ctx.scheduleRefresh(true);
 const next=[...h.timers.values()][0];assert.equal(next.delay,12000);
 await next.fn();assert.equal(h.calls,3);
 assert.equal([...h.timers.values()].at(-1).delay,600000);
 assert.equal(h.draws,1);
});
test('periodic refresh leaves an open form untouched and retries later',async()=>{
 const h=harness();h.ctx.view='systems';h.ctx.scheduleRefresh(true);
 h.ctx.activeModal={title:'Edit app'};
 await [...h.timers.values()][0].fn();
 assert.equal(h.calls,0);assert.equal(h.draws,0);
});
test('search input and hidden tabs do not get overwritten by periodic refresh',async()=>{
 for(const mode of ['input','hidden']){
  const h=harness();h.ctx.view='findings';h.ctx.scheduleRefresh(true);
  if(mode==='input')h.ctx.document.activeElement.tagName='INPUT';else h.ctx.document.hidden=true;
  await [...h.timers.values()][0].fn();
  assert.equal(h.calls,0);assert.equal(h.draws,0);
 }
});
test('a temporary API failure preserves the private workspace rather than replacing it with demo data',async()=>{
 const h=harness();h.ctx.view='systems';const original=h.ctx.state;
 h.ctx.api=async path=>{if(path==='/api/workspace')throw Error('Unavailable');return path==='/api/session'?{signed_in:true}:{};};
 await h.ctx.refresh();assert.equal(h.ctx.state,original);assert.equal(h.draws,0);
 assert.equal(h.notices.length,1);assert.equal(h.timers.size,1);
});
test('a late response cannot overwrite a newer refresh',async()=>{
 const h=harness();let resolveOld,workspaces=0;
 h.ctx.api=async path=>{
  if(path==='/api/session')return {signed_in:true};
  if(path==='/api/workspace'){
   if(++workspaces===1)return new Promise(resolve=>{resolveOld=resolve;});
   return {demo:false,marker:'new'};
  }
  return {};
 };
 const old=h.ctx.refresh();
 await new Promise(resolve=>setImmediate(resolve));
 await h.ctx.refresh();
 resolveOld({demo:false,marker:'old'});await old;
 assert.equal(h.ctx.state.marker,'new');assert.equal(h.draws,1);
});

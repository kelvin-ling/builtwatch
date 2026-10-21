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
  clearTimeout:id=>timers.delete(id),render:()=>draws++,toast:s=>notices.push(s),connectionError:()=>{},considerReviewAlerts:()=>{},
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
 // Aggregate impact totals are fetched only on the Impact page, so a poll is two calls.
 await next.fn();assert.equal(h.calls,2);
 assert.equal([...h.timers.values()].at(-1).delay,1800000);
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

test('closing a dialog with Escape releases editing state and restarts refresh',()=>{
 const h=harness();
 vm.runInContext('var modalHistory=[{title:"Old form"}],lastFocus={focus(){}};',h.ctx);
 h.ctx.activeModal={title:'Form closed by browser'};
 h.ctx.view='systems';
 const start=app.indexOf('function resetModalState(){'),end=app.indexOf("\n$('#modal').addEventListener('close'",start);
 vm.runInContext(app.slice(start,end),h.ctx);
 h.ctx.resetModalState();
 assert.equal(h.ctx.activeModal,null);
 assert.equal(h.ctx.modalHistory.length,0);
 assert.equal(h.timers.size,1);
});

test('initial service outage still renders the already-loaded offline demo',async()=>{
 const h=harness();h.ctx.state={demo:true,systems:[]};h.ctx.api=async()=>{throw Error('Offline');};
 await h.ctx.refresh();assert.equal(h.draws,1);assert.equal(h.ctx.state.demo,true);
});

test('unreadable successful session or workspace responses preserve the last private view',async()=>{
 const transport=readFileSync(new URL('../web/client.js',import.meta.url),'utf8');
 for(const broken of ['/api/session','/api/workspace']){
  const h=harness(),original=h.ctx.state;h.ctx.view='systems';
  Object.assign(h.ctx,{AbortController,fetch:async path=>new Response(path===broken?'<html>Temporary upstream page</html>':JSON.stringify({signed_in:true}),{status:200})});
  vm.runInContext(transport,h.ctx);
  h.ctx.api=path=>h.ctx.BuiltWatchClient.request('','',path);
  await h.ctx.refresh();
  assert.equal(h.ctx.state,original);assert.equal(h.ctx.session.signed_in,true);assert.equal(h.draws,0);
  assert.equal(h.notices.length,1);assert.equal(h.timers.size,1);
 }
});

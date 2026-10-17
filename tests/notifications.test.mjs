import test from 'node:test';
import assert from 'node:assert/strict';
import '../web/status.js';
import '../web/notifications.js';
const f=(id,revision='one')=>({id,revision_hash:revision});
function harness(){
 let stamp=0,permission='default',requests=0;const sent=[],values=new Map();
 const alerts=BuiltWatchNotifications.create({storage:{getItem:k=>values.get(k),setItem:(k,v)=>values.set(k,v)},
  permission:()=>permission,requestPermission:async()=>{requests++;permission='granted';return permission;},send:n=>sent.push(n),now:()=>stamp});
 return {alerts,sent,values,get requests(){return requests;},advance:n=>stamp+=n};
}
test('alerts require opt-in, seed existing reviews and separate workspace identity',async()=>{
 const h=harness();assert.equal(h.alerts.consider('a',[f('old')]),false);assert.equal(h.requests,0);
 await h.alerts.enable('a',[f('old')]);assert.equal(h.requests,1);
 assert.equal(h.alerts.consider('a',[f('old')]),false);
 assert.equal(h.alerts.consider('other',[f('new')]),false);
 assert.equal(h.alerts.consider('a',[f('old'),f('new')]),true);assert.deepEqual(h.sent,[1]);
 assert.equal(h.alerts.consider('a',[f('old'),f('new')]),false);
});
test('daily bound queues still-open revisions and never re-notifies a closed item',async()=>{
 const h=harness();await h.alerts.enable('a',[]);
 h.alerts.consider('a',[f('one')]);
 assert.equal(h.alerts.consider('a',[f('one','two'),f('closed')]),false);
 h.advance(86400000);
 assert.equal(h.alerts.consider('a',[f('one','two')]),true);assert.deepEqual(h.sent,[1,1]);
 h.alerts.disable('a');h.advance(86400000);assert.equal(h.alerts.consider('a',[f('new')]),false);
});
test('notification denial and delivery failure do not consume a delivery receipt',async()=>{
 const values=new Map();let broken=true;
 const alerts=BuiltWatchNotifications.create({storage:{getItem:k=>values.get(k),setItem:(k,v)=>values.set(k,v)},permission:()=> 'granted',requestPermission:async()=> 'denied',send:()=>{if(broken)throw Error('blocked');}});
 await assert.rejects(alerts.enable('a',[]));assert.equal(values.size,0);
 values.set('bw-alerts-v1:a',JSON.stringify({enabled:true,seen:[]}));
 assert.equal(alerts.consider('a',[f('one')]),false);
 broken=false;assert.equal(alerts.consider('a',[f('one')]),true);
});
test('digest distinguishes historical replay and retains evidence, adoption and coverage',()=>{
 const data={demo:true,systems:[{id:'app',name:'Mail'}],sources:[],runs:[]};
 const text=BuiltWatchNotifications.digest(data,[{...f('one'),system_id:'app',title:'Review',adoption_status:'proposed',evidence:[{passage:'Exact source evidence.'}]}],new Date('2026-10-17T00:00:00Z'));
 assert.match(text,/HISTORICAL DEMO/);assert.match(text,/Exact source evidence/);assert.match(text,/Adoption status: proposed/);assert.match(text,/0\/0; 0 failed/);assert.match(text,/does not establish impact/);
});

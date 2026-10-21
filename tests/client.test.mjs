import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const source=readFileSync(new URL('../web/client.js',import.meta.url),'utf8');
function client(response){
 let calls=0;
 const ctx=vm.createContext({AbortController,setTimeout,clearTimeout,fetch:async()=>{calls++;return response();}});
 vm.runInContext(source,ctx);
 return {request:ctx.BuiltWatchClient.request,get calls(){return calls;}};
}
test('successful unreadable or non-object API responses reject without retrying a mutation',async()=>{
 for(const body of ['<html>Upstream unavailable</html>','{"saved":','null','[]','"ok"']){
  const c=client(()=>new Response(body,{status:200}));
  await assert.rejects(c.request('','', '/api/systems',{id:'test'}),/unreadable response.*Refresh to check/i);
  assert.equal(c.calls,1,'a response failure is an unknown mutation outcome, never an automatic retry');
 }
});
test('valid JSON objects retain explicit success, sign-out and HTTP error semantics',async()=>{
 for(const data of [{saved:true},{signed_in:false},{}]){
  const c=client(()=>Response.json(data));assert.deepEqual(JSON.parse(JSON.stringify(await c.request('','', '/api/session'))),data);
 }
 for(const [status,body,message] of [[401,'<html>Denied</html>',/sign in again/],[429,'null',/busy/],[503,'[]',/unavailable/],[400,'{"error":"Review the profile"}',/Review the profile/]]){
  const c=client(()=>new Response(body,{status}));
  await assert.rejects(c.request('','', '/api/session'),e=>e.status===status&&message.test(e.message));assert.equal(c.calls,1);
 }
});

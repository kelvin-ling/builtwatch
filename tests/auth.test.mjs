import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {Miniflare} from 'miniflare';
import {createHash} from 'node:crypto';
const origin='https://builtwatch.example';
test('Cognito authentication, bounded signup, secure sessions and scoped agent connections',async()=>{
 const calls=[];
 const mf=new Miniflare({modules:true,script:await readFile('server/worker.mjs','utf8')+'\nexport default createWorker({"/index.html":{content:"demo",type:"text/html"}});',compatibilityDate:'2024-09-23',d1Databases:['DB'],bindings:{BW_COGNITO_CLIENT_ID:'client',BW_COGNITO_CLIENT_SECRET:'testsecret',BW_API_URL:'https://backend.example',BW_PROXY_SECRET:'secret',BW_AWS_ACCESS_KEY_ID:'test',BW_AWS_SECRET_ACCESS_KEY:'secret'},outboundService:async req=>{
  const data=await req.json();const op=req.headers.get('X-Amz-Target')?.split('.').pop();calls.push({op,data});
  if(op==='InitiateAuth')return Response.json({AuthenticationResult:{AccessToken:'verified-by-upstream'}});
  if(op==='GetUser')return Response.json({UserAttributes:[{Name:'sub',Value:'alice'},{Name:'email',Value:'alice@example.com'},{Name:'email_verified',Value:'true'}]});
  if(op)return Response.json({});
  return Response.json(data);
 }});
 try{
  const db=await mf.getD1Database('DB');
  for(const sql of ['CREATE TABLE request_quota(key TEXT PRIMARY KEY,period TEXT,used INTEGER)','CREATE TABLE auth_session(hash TEXT PRIMARY KEY,account TEXT,email TEXT,expires INTEGER)','CREATE TABLE agent_connection(hash TEXT PRIMARY KEY,account TEXT,system_id TEXT,expires INTEGER,last_sync INTEGER)'])await db.exec(sql);
  const call=(path,body={},cookie='',method='POST')=>mf.dispatchFetch(origin+path,{method,headers:{Origin:origin,'X-BuiltWatch-Request':'1',Cookie:cookie,'Content-Type':'application/json'},...(method==='GET'?{}:{body:JSON.stringify(body)})});
  let r=await call('/api/auth/signup',{email:'alice@example.com',password:'StrongPassword12'});assert.equal(r.status,200);assert.ok(calls[0].data.SecretHash);
  await db.prepare("UPDATE request_quota SET used=100 WHERE key='registrations'").run();r=await call('/api/auth/signup',{email:'alice@example.com',password:'StrongPassword12'});assert.equal(r.status,429);assert.equal(calls.length,1);
  r=await call('/api/auth/signin',{email:'alice@example.com',password:'StrongPassword12'});assert.equal(r.status,200);const cookie=r.headers.get('Set-Cookie').split(';')[0];assert.match(r.headers.get('Set-Cookie'),/HttpOnly; Secure; SameSite=Lax/);
  r=await call('/api/session',{},cookie,'GET');assert.equal((await r.json()).signed_in,true);
  r=await call('/api/connections',{},cookie);const first=await r.json();assert.equal(first.token.length,64);
  r=await call('/api/connections',{},cookie);const c=await r.json();assert.equal(c.system_id,first.system_id);assert.notEqual(c.token,first.token);
  r=await mf.dispatchFetch(origin+'/api/agent/sync',{method:'POST',headers:{Authorization:'Bearer '+first.token},body:'{}'});assert.equal(r.status,401);
  const sync=body=>mf.dispatchFetch(origin+'/api/agent/sync',{method:'POST',headers:{Authorization:'Bearer '+c.token},body:JSON.stringify(body)});
  r=await sync({profile:{id:'other-user-id',name:'My app'}});assert.equal(r.status,200);assert.equal((await r.json()).profile.id,c.system_id);
  r=await sync({});assert.equal(r.status,429);
  r=await mf.dispatchFetch(origin+'/api/workspace',{headers:{Authorization:'Bearer '+c.token}});assert.equal(r.status,401);
  await call('/api/connections',{system_id:c.system_id},cookie,'DELETE');r=await sync({});assert.equal(r.status,401);
  await call('/api/auth/signout',{},cookie);r=await call('/api/session',{},cookie,'GET');assert.equal((await r.json()).signed_in,false);
  assert.equal((await mf.dispatchFetch(origin)).status,200);
 }finally{await mf.dispose();}
});

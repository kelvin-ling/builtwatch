import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {Miniflare} from 'miniflare';
import {createHash} from 'node:crypto';
const origin='https://builtwatch.example';
const sha=text=>createHash('sha256').update(text).digest('hex');

async function gateway(){
  const upstream=[];
  const mf=new Miniflare({modules:true,script:await readFile('server/worker.mjs','utf8')+'\nexport default createWorker({});',compatibilityDate:'2024-09-23',d1Databases:['DB'],bindings:{BW_COGNITO_CLIENT_ID:'client',BW_COGNITO_CLIENT_SECRET:'testsecret',BW_API_URL:'https://backend.example',BW_PROXY_SECRET:'secret',BW_AWS_ACCESS_KEY_ID:'test',BW_AWS_SECRET_ACCESS_KEY:'secret'},outboundService:async req=>{upstream.push(req.url);return Response.json({});}});
  const db=await mf.getD1Database('DB');
  for(const sql of ['CREATE TABLE request_quota(key TEXT PRIMARY KEY,period TEXT,used INTEGER)','CREATE TABLE auth_session(hash TEXT PRIMARY KEY,account TEXT,email TEXT,expires INTEGER)'])await db.exec(sql);
  const used=async key=>(await db.prepare('SELECT used FROM request_quota WHERE key=?').bind(key).first())?.used||0;
  return {mf,db,used,upstream};
}

test('a throttled account cannot spend the shared daily allowance of every other account',async()=>{
  const {mf,db,used}=await gateway();
  try{
    const token='b'.repeat(64),account=sha('mallory'),today=new Date().toISOString().slice(0,10);
    await db.prepare('INSERT INTO auth_session(hash,account,email,expires) VALUES(?,?,?,?)').bind(sha(token),account,'m@example.com',Date.now()+60000).run();
    await db.prepare('INSERT INTO request_quota(key,period,used) VALUES(?,?,300)').bind('account-'+account,today).run();
    for(let i=0;i<5;i++){
      const r=await mf.dispatchFetch(origin+'/api/workspace',{headers:{Cookie:'__Host-bw_session='+token}});
      assert.equal(r.status,429);
    }
    assert.equal(await used('global-day'),0);
    assert.equal(await used('global-minute'),0);
  }finally{await mf.dispose();}
});

test('an address over its sign-in limit cannot exhaust the site-wide sign-in allowance',async()=>{
  const {mf,db,used}=await gateway();
  try{
    const hour=new Date().toISOString().slice(0,13);
    await db.prepare('INSERT INTO request_quota(key,period,used) VALUES(?,?,20)').bind('auth-ip-'+sha('198.51.100.7'),hour).run();
    for(let i=0;i<5;i++){
      const r=await mf.dispatchFetch(origin+'/api/auth/signin',{method:'POST',headers:{Origin:origin,'X-BuiltWatch-Request':'1','CF-Connecting-IP':'198.51.100.7'},body:JSON.stringify({email:'x@example.com',password:'whatever'})});
      assert.equal(r.status,429);
    }
    assert.equal(await used('auth-global'),0);
  }finally{await mf.dispose();}
});

test('rejected sign-ups do not spend the daily verification email allowance',async()=>{
  const {mf,used,upstream}=await gateway();
  try{
    const signup=body=>mf.dispatchFetch(origin+'/api/auth/signup',{method:'POST',headers:{Origin:origin,'X-BuiltWatch-Request':'1'},body:JSON.stringify(body)});
    for(let i=0;i<3;i++)assert.equal((await signup({email:`weak${i}@example.com`,password:'short'})).status,400);
    assert.equal(await used('auth-email-sends'),0);
    assert.equal(await used('registrations'),0);
    assert.equal(upstream.length,0);
    assert.equal((await signup({email:'ok@example.com',password:'StrongPassword12'})).status,200);
    assert.equal(await used('auth-email-sends'),1);
  }finally{await mf.dispose();}
});

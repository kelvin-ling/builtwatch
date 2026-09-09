import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {Miniflare} from 'miniflare';
import {readFile} from 'node:fs/promises';

test('hosting runtime can proxy signed requests and does not follow redirects',async()=>{
  let redirect=false;
  const server=createServer((req,res)=>{
    assert.match(req.headers['x-bw-signature'],/^[a-f0-9]{64}$/);
    if(redirect){res.writeHead(302,{Location:'/elsewhere'});res.end();return;}
    res.writeHead(200,{'Content-Type':'application/json'});res.end('{"systems":[]}');
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const script=await readFile(new URL('../server/worker.mjs',import.meta.url),'utf8');
  const mf=new Miniflare({modules:true,script:script+'\nexport default createWorker({});',compatibilityDate:'2024-09-23',d1Databases:['DB'],
    bindings:{BW_API_URL:`http://127.0.0.1:${server.address().port}`,BW_PROXY_SECRET:'offline-test-secret',BW_AWS_ACCESS_KEY_ID:'TEST',BW_AWS_SECRET_ACCESS_KEY:'test'}});
  try{
    const db=await mf.getD1Database("DB");await db.exec("CREATE TABLE request_quota (key TEXT PRIMARY KEY, period TEXT NOT NULL, used INTEGER NOT NULL)");
    const call=()=>mf.dispatchFetch('https://builtwatch.example/api/workspace',{headers:{'oai-authenticated-user-id':'test-user'}});
    let r=await call();assert.equal(r.status,200);assert.deepEqual(await r.json(),{systems:[]});
    redirect=true;r=await call();assert.equal(r.status,502);
    await db.prepare("UPDATE request_quota SET used=180 WHERE key='global-minute'").run();
    r=await call();assert.equal(r.status,429);
  }finally{await mf.dispose();await new Promise(resolve=>server.close(resolve));}
});

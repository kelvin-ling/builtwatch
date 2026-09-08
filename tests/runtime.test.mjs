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
  const mf=new Miniflare({modules:true,script:script+'\nexport default createWorker({});',compatibilityDate:'2024-09-23',
    bindings:{BW_API_URL:`http://127.0.0.1:${server.address().port}`,BW_PROXY_SECRET:'offline-test-secret'}});
  try{
    const call=()=>mf.dispatchFetch('https://builtwatch.example/api/workspace',{headers:{'oai-authenticated-user-id':'test-user'}});
    let r=await call();assert.equal(r.status,200);assert.deepEqual(await r.json(),{systems:[]});
    redirect=true;r=await call();assert.equal(r.status,502);
  }finally{await mf.dispose();await new Promise(resolve=>server.close(resolve));}
});

import test from 'node:test';
import assert from 'node:assert/strict';
import {createHmac,createHash} from 'node:crypto';
import {createWorker} from '../server/worker.mjs';
const worker=createWorker({'/index.html':{content:'BuiltWatch',type:'text/html'},'/robots.txt':{content:'User-agent: *\nAllow: /\nDisallow: /api/',type:'text/plain'}});
const origin='https://builtwatch.example';
const env={BW_API_URL:'https://backend.example/',BW_PROXY_SECRET:'secret-for-tests',BW_AWS_ACCESS_KEY_ID:'TEST',BW_AWS_SECRET_ACCESS_KEY:'test',DB:{prepare:(sql)=>({bind:()=>({first:async()=>sql.startsWith('SELECT account,email')?{account:createHash('sha256').update('alice').digest('hex'),email:'alice@example.com'}:{used:1}})})}};
test('anonymous visitors see sample but cannot read or mutate workspaces',async()=>{
  assert.equal((await worker.fetch(new Request(origin),env)).status,200);
  assert.equal((await worker.fetch(new Request(origin+'/api/workspace'),env)).status,401);
  const session=await (await worker.fetch(new Request(origin+'/api/session'),env)).json();
  assert.equal(session.signed_in,false);
});
test('the generated Sites host redirects to the canonical custom domain',async()=>{
  const r=await worker.fetch(new Request('https://builtwatch.kelvinlingac.chatgpt.site/systems?fresh=1'),env);
  assert.equal(r.status,301);
  assert.equal(r.headers.get('Location'),'https://builtwatch.org/systems?fresh=1');
});
test('robots policy is available from the static worker',async()=>{
  const r=await worker.fetch(new Request(origin+'/robots.txt'),env);
  assert.equal(r.status,200);
  assert.match(await r.text(),/Disallow: \/api\//);
});
test('public impact totals do not require a session or expose a tenant header',async()=>{
  const original=globalThis.fetch;
  try{
    globalThis.fetch=async(url,opts)=>{
      assert.equal(new URL(url).pathname,'/api/public-impact');
      assert.equal(opts.headers['x-bw-account'],undefined);
      return new Response('{"systems_monitored":2}',{headers:{'Cache-Control':'public, max-age=60'}});
    };
    const r=await worker.fetch(new Request(origin+'/api/public-impact'),env);
    assert.equal(r.status,200);assert.equal((await r.json()).systems_monitored,2);
  assert.ok(r.headers.get('Cache-Control').includes('public, max-age=60'));
  }finally{globalThis.fetch=original;}
});
test('cross-origin writes are rejected even for a signed-in user',async()=>{
  const r=await worker.fetch(new Request(origin+'/api/systems',{method:'POST',headers:{Cookie:'__Host-bw_session='+('a'.repeat(64)),'Origin':'https://evil.example','X-BuiltWatch-Request':'1'},body:'{}'}),env);
  assert.equal(r.status,403);
});
test('proxy signs server-derived identity and ignores client account and authorization headers',async()=>{
  const original=globalThis.fetch;
  try {
    globalThis.fetch=async(url,opts)=>{
      const h=opts.headers;
      assert.equal(h['x-bw-account'],createHash('sha256').update('alice').digest('hex'));
      assert.equal(h.authorization,undefined);
      const message=['POST','/api/systems',h['x-bw-account'],h['x-bw-time'],h['x-bw-nonce'],createHash('sha256').update('{}').digest('hex')].join('\n');
      assert.equal(h['x-bw-signature'],createHmac('sha256',env.BW_PROXY_SECRET).update(message).digest('hex'));
      return new Response('{"saved":true}');
    };
    const r=await worker.fetch(new Request(origin+'/api/systems',{method:'POST',headers:{Cookie:'__Host-bw_session='+('a'.repeat(64)),'oai-authenticated-user-id':'forged','x-bw-account':'bob','Authorization':'Bearer client','Origin':origin,'X-BuiltWatch-Request':'1'},body:'{}'}),env);
    assert.equal(r.status,200);
    assert.equal(r.headers.get('Cache-Control'),'no-store');
  } finally {globalThis.fetch=original;}
});
test('backend failure is visible and secrets are never returned',async()=>{
  const original=globalThis.fetch;
  try{
    globalThis.fetch=async()=>{throw Error('secret upstream failure');};
    const r=await worker.fetch(new Request(origin+'/api/workspace',{headers:{Cookie:'__Host-bw_session='+('a'.repeat(64))}}),env);
    assert.equal(r.status,503);
    assert.ok(!(await r.text()).includes('secret'));
  }finally{globalThis.fetch=original;}
});
test('AWS signing agrees with the AWS SDK reference vector',async()=>{
 const {awsHeaders}=await import('../server/worker.mjs');
 const headers=await awsHeaders(new URL('https://example.lambda-url.us-east-1.on.aws/api/intake'),'POST','{}',{BW_AWS_ACCESS_KEY_ID:'TESTKEY',BW_AWS_SECRET_ACCESS_KEY:'test-secret'},new Date('2026-09-08T12:00:00Z'));
 assert.ok(headers.Authorization.endsWith('Signature=93483cb65117fc5c286ef46d003e882e6d8b038db350ceb89e0ceb79de0cbffd'));
});

test('ChatGPT and forged identity headers no longer grant access',async()=>{
 const r=await worker.fetch(new Request(origin+'/api/workspace',{headers:{'oai-authenticated-user-id':'alice'}}),env);assert.equal(r.status,401);
});
test('static demo survives a missing or exhausted database',async()=>{
  const r=await worker.fetch(new Request(origin),{});assert.equal(r.status,200);
});

test('visitors can send bounded feedback and it is stored without app details',async()=>{
  const feedback=[];
  const feedbackDB={prepare(sql){
    const statement={
      run:async()=>({}),
      bind:(...args)=>({
        first:async()=>sql.startsWith('INSERT INTO request_quota')?{used:1}:null,
        run:async()=>{if(sql.startsWith('INSERT INTO feedback'))feedback.push({kind:args[3],message:args[4],page:args[5],created_at:args[6]});return{};},
        all:async()=>({results:feedback}),
      }),
      all:async()=>({results:feedback}),
    };
    return statement;
  }};
  const headers={Origin:origin,'X-BuiltWatch-Request':'1','CF-Connecting-IP':'203.0.113.9','Content-Type':'application/json'};
  const bad=await worker.fetch(new Request(origin+'/api/feedback',{method:'POST',headers,body:JSON.stringify({kind:'unknown',message:'nope'})}),{...env,DB:feedbackDB});
  assert.equal(bad.status,400);
  const good=await worker.fetch(new Request(origin+'/api/feedback',{method:'POST',headers,body:JSON.stringify({kind:'suggestion',message:'Make the import result easier to scan.',page:'systems'})}),{...env,DB:feedbackDB});
  assert.equal(good.status,200);assert.equal((await good.json()).saved,true);assert.equal(feedback.length,1);assert.equal(feedback[0].page,'systems');
});

test('admin requires the configured owner and remains available during live pause',async()=>{
 const cookie={Cookie:'__Host-bw_session='+('a'.repeat(64))};
 const original=globalThis.fetch;
 let calls=0;
 try{
  globalThis.fetch=async()=>{calls++;return new Response('{"actual_usd":1.5}');};
  const nonowner=await worker.fetch(new Request(origin+'/api/admin',{headers:cookie}),{...env,BW_OWNER_ACCOUNT:'other',BW_OWNER_EMAIL:'owner@example.com'});
  assert.equal(nonowner.status,403);assert.equal(calls,0);
  const adminEnv={...env,BW_LIVE_ENABLED:'false',BW_OWNER_ACCOUNT:createHash('sha256').update('alice').digest('hex'),BW_OWNER_EMAIL:'alice@example.com',DB:{prepare:sql=>({...env.DB.prepare(sql),all:async()=>({results:[]})})}};
  const session=await (await worker.fetch(new Request(origin+'/api/session',{headers:cookie}),adminEnv)).json();assert.equal(session.is_admin,true);
  const allowed=await worker.fetch(new Request(origin+'/api/admin',{headers:cookie}),adminEnv);
  assert.equal(allowed.status,200);assert.equal((await allowed.json()).actual_usd,1.5);assert.equal(calls,1);
  assert.equal((await worker.fetch(new Request(origin+'/api/admin',{headers:{Authorization:'Bearer '+'a'.repeat(64)}}),adminEnv)).status,401);
 }finally{globalThis.fetch=original;}
});

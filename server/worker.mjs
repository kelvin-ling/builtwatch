// Sites dispatch verifies identity before forwarding these headers to this Worker.
const encoder = new TextEncoder();
const hex = bytes => Array.from(new Uint8Array(bytes), b => b.toString(16).padStart(2, '0')).join('');
const digest = text => crypto.subtle.digest('SHA-256', encoder.encode(text)).then(hex);
const security = {'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'same-origin'};
const json = (data, status=200) => new Response(JSON.stringify(data), {status, headers:{...security,'Content-Type':'application/json'}});
async function claimRequest(db,key,period,limit){
  return !!await db.prepare(`INSERT INTO request_quota (key,period,used) VALUES (?,?,1)
    ON CONFLICT(key) DO UPDATE SET period=excluded.period,
    used=CASE WHEN request_quota.period=excluded.period THEN request_quota.used+1 ELSE 1 END
    WHERE request_quota.period<excluded.period OR (request_quota.period=excluded.period AND request_quota.used<?) RETURNING used`)
    .bind(key,period,limit).first();
}
async function withinEdgeAllowance(db,account){
  const now=new Date();
  return await claimRequest(db,'global-day',now.toISOString().slice(0,10),10000)
    && await claimRequest(db,'global-minute',now.toISOString().slice(0,16),180)
    && await claimRequest(db,'account-'+account,now.toISOString().slice(0,10),300);
}
async function boundedBody(request){
  if(Number(request.headers.get('Content-Length'))>24000) throw Error('too_large');
  if(!request.body)return '';
  const reader=request.body.getReader();const chunks=[];let total=0;
  try{while(true){const {value,done}=await reader.read();if(done)break;total+=value.byteLength;
    if(total>24000){await reader.cancel();throw Error('too_large');}chunks.push(value);}
  }finally{reader.releaseLock();}
  const bytes=new Uint8Array(total);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.length;}
  return new TextDecoder('utf-8',{fatal:true}).decode(bytes);
}
async function hmacBytes(key,text){
  const imported=await crypto.subtle.importKey('raw',typeof key==='string'?encoder.encode(key):key,{name:'HMAC',hash:'SHA-256'},false,['sign']);
  return crypto.subtle.sign('HMAC',imported,encoder.encode(text));
}
export async function awsHeaders(url,method,body,env,now=new Date()){
  const stamp=now.toISOString().replace(/[:-]|\.\d{3}/g,'');const day=stamp.slice(0,8);
  const hash=await digest(body);const signed='host;x-amz-content-sha256;x-amz-date';
  const headers=`host:${url.host}\nx-amz-content-sha256:${hash}\nx-amz-date:${stamp}\n`;
  const canonicalPath=url.pathname.split('/').map(part=>encodeURIComponent(part).replace(/[!'()*]/g,c=>'%'+c.charCodeAt(0).toString(16).toUpperCase())).join('/');
  const canonical=[method,canonicalPath,'',headers,signed,hash].join('\n');
  const scope=day+'/us-east-1/lambda/aws4_request';
  let key=await hmacBytes('AWS4'+env.BW_AWS_SECRET_ACCESS_KEY,day);
  for(const part of ['us-east-1','lambda','aws4_request'])key=await hmacBytes(key,part);
  const signature=hex(await hmacBytes(key,['AWS4-HMAC-SHA256',stamp,scope,await digest(canonical)].join('\n')));
  return {'x-amz-date':stamp,'x-amz-content-sha256':hash,
    Authorization:`AWS4-HMAC-SHA256 Credential=${env.BW_AWS_ACCESS_KEY_ID}/${scope}, SignedHeaders=${signed}, Signature=${signature}`};
}
export function createWorker(assets) {
  return {async fetch(request, env) {
    const url = new URL(request.url);
    if (!url.pathname.startsWith('/api/')) {
      if (!['GET','HEAD'].includes(request.method)) return json({error:'Method not allowed'},405);
      const asset = assets[url.pathname === '/' ? '/index.html' : url.pathname];
      if (!asset) return json({error:'Page not found'},404);
      return new Response(request.method === 'HEAD' ? null : asset.content, {headers:{...security,
        'Content-Type':asset.type,'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; base-uri 'self'; form-action 'self'; object-src 'none'"}});
    }
    const identity = request.headers.get('oai-authenticated-user-id');
    if (url.pathname === '/api/session' && request.method === 'GET') {
      return json({signed_in:!!identity, workspace_reference:identity ? await digest(identity) : null, email:identity ? request.headers.get('oai-authenticated-user-email') || '' : '',
        sign_in:'/signin-with-chatgpt?return_to=%2F',sign_out:'/signout-with-chatgpt?return_to=%2F'});
    }
    if (!identity) return json({error:'Sign in with ChatGPT to open your own workspace.'},401);
    if (!['GET','POST','DELETE'].includes(request.method)) return json({error:'Method not allowed'},405);
    if (request.method !== 'GET' && (request.headers.get('Origin') !== url.origin || request.headers.get('X-BuiltWatch-Request') !== '1')) {
      return json({error:'Please make changes from the BuiltWatch website.'},403);
    }
    if (url.search) return json({error:'Query parameters are not supported.'},400);
    if (!env.BW_API_URL || !env.BW_PROXY_SECRET) return json({error:'Workspace setup is not complete. Please try again later.'},503);
    let body;try{body=request.method==='GET'?'':await boundedBody(request);}catch{return json({error:'Use valid text under 24 KB.'},413);}
    const account = await digest(identity);
    if(!env.DB)return json({error:'The request limiter is not ready. Please return later.'},503);
    try{if(!await withinEdgeAllowance(env.DB,account))return json({error:'The pilot request allowance is reached. Try later; your data is saved.'},429);}catch{return json({error:'The request limiter is temporarily unavailable. Please return later.'},503);}
    const stamp = Math.floor(Date.now()/1000).toString();
    const nonce = crypto.randomUUID();
    const message = [request.method,url.pathname,account,stamp,nonce,await digest(body)].join('\n');
    const key = await crypto.subtle.importKey('raw',encoder.encode(env.BW_PROXY_SECRET),{name:'HMAC',hash:'SHA-256'},false,['sign']);
    const signature = hex(await crypto.subtle.sign('HMAC',key,encoder.encode(message)));
    if(!env.BW_AWS_ACCESS_KEY_ID||!env.BW_AWS_SECRET_ACCESS_KEY)return json({error:'The secure gateway is not configured.'},503);
    try {
      const target=new URL(url.pathname,env.BW_API_URL);
      const authorization=await awsHeaders(target,request.method,body,env);
      const upstream = await fetch(new URL(url.pathname, env.BW_API_URL), {method:request.method,
        headers:{...authorization,'Content-Type':'application/json','x-bw-account':account,'x-bw-time':stamp,'x-bw-nonce':nonce,'x-bw-signature':signature},
        ...(request.method === 'GET' ? {} : {body}),signal:AbortSignal.timeout(25000), redirect:'manual'});
      if (upstream.status >= 300 && upstream.status < 400) return json({error:'The workspace service returned an unexpected redirect.'},502);
      return new Response(await upstream.text(), {status:upstream.status,headers:{...security,'Content-Type':'application/json'}});
    } catch (error) {
      console.error("workspace_proxy_failed", error.name, error.message);
      return json({error:'The workspace service is temporarily unavailable. Please try again.'},503);
    }
  }};
}

// Sites dispatch verifies identity before forwarding these headers to this Worker.
const encoder = new TextEncoder();
const hex = bytes => Array.from(new Uint8Array(bytes), b => b.toString(16).padStart(2, '0')).join('');
const digest = text => crypto.subtle.digest('SHA-256', encoder.encode(text)).then(hex);
const security = {'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'same-origin'};
const json = (data, status=200) => new Response(JSON.stringify(data), {status, headers:{...security,'Content-Type':'application/json'}});
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
    const body = request.method === 'GET' ? '' : await request.text();
    if (encoder.encode(body).length > 24000) return json({error:'Please keep the profile under 24 KB.'},413);
    const account = await digest(identity);
    const stamp = Math.floor(Date.now()/1000).toString();
    const nonce = crypto.randomUUID();
    const message = [request.method,url.pathname,account,stamp,nonce,await digest(body)].join('\n');
    const key = await crypto.subtle.importKey('raw',encoder.encode(env.BW_PROXY_SECRET),{name:'HMAC',hash:'SHA-256'},false,['sign']);
    const signature = hex(await crypto.subtle.sign('HMAC',key,encoder.encode(message)));
    try {
      const upstream = await fetch(new URL(url.pathname, env.BW_API_URL), {method:request.method,
        headers:{'Content-Type':'application/json','x-bw-account':account,'x-bw-time':stamp,'x-bw-nonce':nonce,'x-bw-signature':signature},
        ...(request.method === 'GET' ? {} : {body}),signal:AbortSignal.timeout(25000), redirect:'manual'});
      if (upstream.status >= 300 && upstream.status < 400) return json({error:'The workspace service returned an unexpected redirect.'},502);
      return new Response(await upstream.text(), {status:upstream.status,headers:{...security,'Content-Type':'application/json'}});
    } catch (error) {
      console.error("workspace_proxy_failed", error.name, error.message);
      return json({error:'The workspace service is temporarily unavailable. Please try again.'},503);
    }
  }};
}

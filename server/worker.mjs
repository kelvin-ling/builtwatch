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
const SESSION_COOKIE='__Host-bw_session';
const sessionToken=request=>(request.headers.get('Cookie')||'').split(';').map(x=>x.trim()).find(x=>x.startsWith(SESSION_COOKIE+'='))?.slice(SESSION_COOKIE.length+1)||'';
const sessionCookie=(token,age=604800)=>`${SESSION_COOKIE}=${token}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${age}`;
const randomToken=()=>hex(crypto.getRandomValues(new Uint8Array(32)));
async function signedUser(request,env){
  const token=sessionToken(request);
  if(!/^[a-f0-9]{64}$/.test(token))return null;
  return await env.DB.prepare('SELECT account,email FROM auth_session WHERE hash=? AND expires>?').bind(await digest(token),Date.now()).first();
}
async function cognito(env,operation,payload){
  const r=await fetch('https://cognito-idp.us-east-1.amazonaws.com/',{method:'POST',headers:{'Content-Type':'application/x-amz-json-1.1','X-Amz-Target':'AWSCognitoIdentityProviderService.'+operation},body:JSON.stringify(payload),redirect:'manual',signal:AbortSignal.timeout(15000)});
  const data=await r.json();if(!r.ok){const error=Error('Authentication could not be completed.');error.code=String(data.__type||'').split('#').pop();throw error;}return data;
}
async function authRoute(request,env,url){
  if(request.method!=='POST')return json({error:'Method not allowed'},405);
  if(request.headers.get('Origin')!==url.origin||request.headers.get('X-BuiltWatch-Request')!=='1')return json({error:'Use the BuiltWatch sign-in form.'},403);
  if(!env.DB||!env.BW_COGNITO_CLIENT_ID||!env.BW_COGNITO_CLIENT_SECRET)return json({error:'Sign-in is temporarily unavailable. The demo still works.'},503);
  const action=url.pathname.split('/').pop();
  if(!['signup','confirm','signin','signout','forgot','reset','resend'].includes(action))return json({error:'Route not found'},404);
  try{
    if(action==='signout'){
      await env.DB.prepare('DELETE FROM auth_session WHERE hash=?').bind(await digest(sessionToken(request))).run();
      return new Response('{"signed_out":true}',{headers:{...security,'Content-Type':'application/json','Set-Cookie':sessionCookie('',0)}});
    }
    const body=JSON.parse(await boundedBody(request));
    const email=String(body.email||'').trim().toLowerCase();
    if(email.length>254||!/^\S+@\S+\.\S+$/.test(email))return json({error:'Enter a valid email address.'},400);
    const day=new Date().toISOString().slice(0,10),hour=new Date().toISOString().slice(0,13);
    const ip=await digest(request.headers.get('CF-Connecting-IP')||'unknown');
    if(!await claimRequest(env.DB,'auth-global',day,200)||!await claimRequest(env.DB,'auth-ip-'+ip,hour,20)||!await claimRequest(env.DB,'auth-email-'+await digest(email),hour,10))return json({error:'Sign-in attempts are temporarily limited. Please try later; the demo remains available.'},429);
    const secretHash=btoa(String.fromCharCode(...new Uint8Array(await hmacBytes(env.BW_COGNITO_CLIENT_SECRET,email+env.BW_COGNITO_CLIENT_ID))));
    const common={ClientId:env.BW_COGNITO_CLIENT_ID,Username:email,SecretHash:secretHash};
    if(['signup','forgot','resend'].includes(action)&&!await claimRequest(env.DB,'auth-email-sends',day,20))return json({error:'Today’s verification email allowance is reached. Please return tomorrow or use the demo.'},429);
    if(['signup','reset'].includes(action)&&(!/^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{12,128}$/.test(body.password||'')))return json({error:'Use 12–128 characters with uppercase, lowercase and a number.'},400);
    if(action==='signup'){
      if(env.BW_REGISTRATION_ENABLED==='false')return json({error:'Registration is paused. Please use the demo.'},429);
      // A lifetime ceiling, never reset by retries or deleted accounts, bounds Cognito MAUs.
      if(!await claimRequest(env.DB,'registrations','lifetime',100))return json({error:'Registration capacity is reached. The demo is still open.'},429);
      await cognito(env,'SignUp',{...common,Password:body.password,UserAttributes:[{Name:'email',Value:email}]});
      return json({next:'confirm',message:'Check your email for a verification code.'});
    }
    if(action==='confirm'){
      await cognito(env,'ConfirmSignUp',{...common,ConfirmationCode:String(body.code||'')});return json({next:'signin',message:'Email verified. You can now sign in.'});
    }
    if(action==='resend'){
      try{await cognito(env,'ResendConfirmationCode',common);}catch(e){if(!['UserNotFoundException','InvalidParameterException'].includes(e.code))throw e;}
      return json({next:'confirm',message:'If verification is pending, a new code has been sent.'});
    }
    if(action==='forgot'){
      try{await cognito(env,'ForgotPassword',common);}catch(e){if(!['UserNotFoundException','InvalidParameterException'].includes(e.code))throw e;}
      return json({next:'reset',message:'If the account can be recovered, a code has been sent.'});
    }
    if(action==='reset'){
      await cognito(env,'ConfirmForgotPassword',{...common,ConfirmationCode:String(body.code||''),Password:body.password});
      await env.DB.prepare('DELETE FROM auth_session WHERE email=?').bind(email).run();
      return json({next:'signin',message:'Password updated. Sign in again.'});
    }
    if(typeof body.password!=='string'||body.password.length>128)return json({error:'Enter your password.'},400);
    const result=await cognito(env,'InitiateAuth',{ClientId:env.BW_COGNITO_CLIENT_ID,AuthFlow:'USER_PASSWORD_AUTH',AuthParameters:{USERNAME:email,PASSWORD:body.password,SECRET_HASH:secretHash}});
    if(!result.AuthenticationResult?.AccessToken)return json({error:'Sign-in needs an additional step. Please contact the owner.'},403);
    // Cognito verifies the returned token; no unverified JWT claims enter the account boundary.
    const user=await cognito(env,'GetUser',{AccessToken:result.AuthenticationResult.AccessToken});
    const attrs=Object.fromEntries(user.UserAttributes.map(x=>[x.Name,x.Value]));
    if(attrs.email_verified!=='true'||attrs.email?.toLowerCase()!==email||!attrs.sub)return json({error:'Verify your email before signing in.'},403);
    let account=await digest('cognito:'+attrs.sub);
    // Only the operator-configured, previously verified owner record may bridge identities.
    if(env.BW_OWNER_EMAIL?.toLowerCase()===email&&/^[a-f0-9]{64}$/.test(env.BW_OWNER_ACCOUNT||''))account=env.BW_OWNER_ACCOUNT;
    const token=randomToken();
    await env.DB.batch([
      env.DB.prepare('DELETE FROM auth_session WHERE expires<? OR account=?').bind(Date.now(),account),
      env.DB.prepare('INSERT INTO auth_session(hash,account,email,expires) VALUES(?,?,?,?)').bind(await digest(token),account,email,Date.now()+604800000)
    ]);
    return new Response(JSON.stringify({signed_in:true}),{headers:{...security,'Content-Type':'application/json','Set-Cookie':sessionCookie(token)}});
  }catch(e){
    const known={UserNotConfirmedException:'Verify your email first. Choose Verify email below.',CodeMismatchException:'That code is incorrect. Please check the email.',ExpiredCodeException:'The code expired. Request a new one.',InvalidPasswordException:'Use a stronger password with 12 characters, upper/lowercase and a number.',LimitExceededException:'The email allowance is reached. Try again later.',TooManyRequestsException:'Too many attempts. Please try later.'};
    if(e instanceof SyntaxError)return json({error:'Please complete the form.'},400);
    return json({error:known[e.code]||'Unable to complete this request. Check your details, verify your email, or try password recovery.'},400);
  }
}
async function connectionRoute(request,env,user,url){
  if(request.method==='GET'){
    const rows=await env.DB.prepare('SELECT system_id,expires,last_sync FROM agent_connection WHERE account=? AND expires>?').bind(user.account,Date.now()).all();return json({connections:rows.results});
  }
  const body=JSON.parse(await boundedBody(request));
  if(request.method==='DELETE'){
    await env.DB.prepare('DELETE FROM agent_connection WHERE account=? AND system_id=?').bind(user.account,String(body.system_id||'')).run();return json({revoked:true});
  }
  if(request.method!=='POST')return json({error:'Method not allowed'},405);
  if(!await claimRequest(env.DB,'connect-'+user.account,new Date().toISOString().slice(0,10),10))return json({error:'Connection creation is limited to ten per day.'},429);
  // One active connection per workspace keeps pilot scope and data exposure small.
  const previous=await env.DB.prepare('SELECT system_id FROM agent_connection WHERE account=?').bind(user.account).first();
  const systemId=previous?.system_id||'agent-'+crypto.randomUUID().slice(0,12),token=randomToken();
  await env.DB.batch([
    env.DB.prepare('DELETE FROM agent_connection WHERE account=?').bind(user.account),
    env.DB.prepare('INSERT INTO agent_connection(hash,account,system_id,expires,last_sync) VALUES(?,?,?,?,0)').bind(await digest(token),user.account,systemId,Date.now()+7776000000)
  ]);
  return json({token,system_id:systemId,endpoint:url.origin+'/api/agent/sync',expires_days:90});
}

export function createWorker(assets) {
  return {async fetch(request, env) {
    const url = new URL(request.url);
    if (!url.pathname.startsWith('/api/')) {
      if (!['GET','HEAD'].includes(request.method)) return json({error:'Method not allowed'},405);
      const asset = assets[url.pathname === '/' ? '/index.html' : url.pathname];
      if (!asset) return json({error:'Page not found'},404);
      return new Response(request.method === 'HEAD' ? null : asset.content, {headers:{...security,
        'Content-Type':asset.type,...(url.pathname==='/offline-demo.html'?{'Content-Disposition':'attachment; filename=BuiltWatch-offline-demo.html'}:{}),'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; base-uri 'self'; form-action 'self'; object-src 'none'"}});
    }
    if(url.pathname.startsWith('/api/auth/'))return authRoute(request,env,url);
    let user;
    try{user=await signedUser(request,env);}catch{return json({error:'Sign-in is temporarily unavailable. The demo still works.'},503);}
    if(url.pathname==='/api/session'&&request.method==='GET')return json({signed_in:!!user,email:user?.email||'',workspace_reference:user?.account||null,is_admin:!!user&&user.account===env.BW_OWNER_ACCOUNT&&user.email.toLowerCase()===env.BW_OWNER_EMAIL?.toLowerCase()});
    const agentRequest=url.pathname==='/api/agent/sync'&&request.method==='POST';
    let agent;
    if(agentRequest){
      const token=(request.headers.get('Authorization')||'').replace(/^Bearer /,'');
      if(!/^[a-f0-9]{64}$/.test(token))return json({error:'A valid agent connection is required.'},401);
      try{agent=await env.DB.prepare('SELECT account,system_id FROM agent_connection WHERE hash=? AND expires>?').bind(await digest(token),Date.now()).first();}catch{return json({error:'Connection unavailable.'},503);}
      if(!agent)return json({error:'Connection expired or revoked.'},401);
      user={account:agent.account};
    }
    if(!user)return json({error:'Sign in with your email to open your workspace.'},401);
    if(!['GET','POST','DELETE'].includes(request.method))return json({error:'Method not allowed'},405);
    if(!agentRequest&&request.method!=='GET'&&(request.headers.get('Origin')!==url.origin||request.headers.get('X-BuiltWatch-Request')!=='1'))return json({error:'Make changes from the BuiltWatch website.'},403);
    if(url.search)return json({error:'Query parameters are not supported.'},400);
    const account=user.account;
    const adminRequest=url.pathname==='/api/admin';
    if(adminRequest&&(agentRequest||account!==env.BW_OWNER_ACCOUNT||user.email?.toLowerCase()!==env.BW_OWNER_EMAIL?.toLowerCase()))return json({error:'Owner access required.'},403);
    try{if(!(adminRequest?await claimRequest(env.DB,'admin-requests',new Date().toISOString().slice(0,10),100):await withinEdgeAllowance(env.DB,account)))return json({error:'The pilot request allowance is reached. The demo still works; your data is saved.'},429);}catch{return json({error:'The workspace limiter is temporarily unavailable. The demo still works.'},503);}
    if(url.pathname==='/api/connections'){
      try{return await connectionRoute(request,env,user,url);}catch{return json({error:'Connection could not be updated.'},400);}
    }
    if(env.BW_LIVE_ENABLED==='false'&&!adminRequest)return json({error:'Live service is paused. The interactive demo remains available.'},503);
    if(!env.BW_API_URL||!env.BW_PROXY_SECRET)return json({error:'Workspace setup is incomplete.'},503);
    let body;try{body=request.method==='GET'?'':await boundedBody(request);}catch{return json({error:'Use valid text under 24 KB.'},413);}
    if(agentRequest){
      try{
        const input=JSON.parse(body);
        if(!input||typeof input!=='object'||Array.isArray(input))throw Error();
        body=JSON.stringify({system_id:agent.system_id,...(input.profile?{profile:{...input.profile,id:agent.system_id}}:{})});
        if(!await claimRequest(env.DB,'agent-daily-'+account,new Date().toISOString().slice(0,10),1))return json({error:'This connection syncs once per UTC day. Return tomorrow.'},429);
      }catch{return json({error:'Send a JSON object with an optional profile.'},400);}
    }
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
      if(adminRequest&&upstream.ok){
        const data=await upstream.json();
        const rows=await env.DB.prepare("SELECT key,period,used FROM request_quota WHERE key IN ('global-day','auth-global','registrations')").all();
        const today=new Date().toISOString().slice(0,10);
        const used=key=>rows.results.find(x=>x.key===key&&(key==='registrations'||x.period===today))?.used||0;
        data.gateway={requests_today:used('global-day'),request_limit:10000,auth_attempts_today:used('auth-global'),registration_attempts:used('registrations')};
        return json(data);
      }
      if(agentRequest&&upstream.ok)await env.DB.prepare('UPDATE agent_connection SET last_sync=? WHERE account=?').bind(Date.now(),account).run();
      return new Response(await upstream.text(), {status:upstream.status,headers:{...security,'Content-Type':'application/json'}});
    } catch (error) {
      console.error("workspace_proxy_failed", error.name);
      return json({error:'The workspace service is temporarily unavailable. Please try again.'},503);
    }
  }};
}

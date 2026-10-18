'use strict';
// Device-local opt-in. Only generic counts reach the operating-system notification.
globalThis.BuiltWatchNotifications = (() => {
 const DAY=24*60*60*1000;
 const keys=findings=>findings.map(f=>`${f.id}:${f.revision_hash||f.created_at||'original'}`);
 function create({storage,permission,requestPermission,send,now=Date.now}){
  const memory=new Map();
  const key=scope=>`bw-alerts-v1:${scope}`;
  function read(scope){try{const saved=JSON.parse(storage.getItem(key(scope)));if(saved?.enabled===false)return saved;const cached=memory.get(scope);return cached&&(!saved||cached.lastSent>saved.lastSent)?cached:saved||cached||{enabled:false,seen:[]};}catch{return memory.get(scope)||{enabled:false,seen:[]};}}
  function write(scope,value){storage.setItem(key(scope),JSON.stringify(value));memory.set(scope,value);}
  async function enable(scope,findings){
   if(!scope)throw Error('Open a private workspace first.');
   if(await requestPermission()!=='granted')throw Error('Browser alerts were not enabled. You can still download a digest.');
   write(scope,{enabled:true,seen:keys(findings),lastSent:null});
  }
  function disable(scope){write(scope,{enabled:false,seen:[]});}
  function consider(scope,findings){
   if(!scope)return false;
   const saved=read(scope),stamp=now();
   if(!saved.enabled||permission()!=='granted')return false;
   const unseen=keys(findings).filter(k=>!saved.seen.includes(k));
   if(!unseen.length||(saved.lastSent!=null&&stamp-saved.lastSent<DAY))return false;
   try{
    send(unseen.length);
    const receipt={enabled:true,lastSent:stamp,seen:[...new Set([...saved.seen,...keys(findings)])].slice(-600)};
    memory.set(scope,receipt);
    try{write(scope,receipt);}catch{/* Retain this tab’s receipt if browser storage is full. */}
    return true;
   }catch{return false;}
  }
  return {enable,disable,consider,settings:read};
 }
 function digest(data,findings,date=new Date()){
  const clean=value=>String(value||'').replace(/[\r\n]/g,' ').replace(/[<>]/g,'');
  const summary=BuiltWatchStatus.workspace(data,findings.length),health=BuiltWatchStatus.health(data,date.getTime());
  let text=`# BuiltWatch review digest\n\n${data.demo?'HISTORICAL DEMO — saved examples.\n\n':''}Generated: ${date.toISOString()}\nOpen reviews: ${findings.length}\nLast successful check: ${health.lastSuccess||'Not recorded'}\nLatest source fetches: ${summary.coverage.checked}/${summary.coverage.total}; ${summary.coverage.failed} failed; ${summary.coverage.unchecked} not covered.\n\n`;
  for(const f of findings){
   const app=data.systems.find(s=>s.id===f.system_id),source=data.sources.find(s=>s.id===f.source_id);
   text+=`## ${clean(app?.name||f.system_id)}\n\n${clean(f.title)}\nSource: ${clean(source?.name||f.source_id)}\n${source?.url&&/^https:\/\//.test(source.url)?source.url+'\n':''}Method: ${clean(f.assessment_method||'Historical assessment')}\nAdoption status: ${clean(f.adoption_status||'unknown')}\n`;
   for(const e of f.evidence||[])text+=`\n> ${String(e.passage||'').replaceAll('\n','\n> ')}\n`;
   const where=app&&globalThis.BuiltWatchArchMap?.landing(app,f);
   text+=`\nRecorded dependency: ${(f.system_facts||[]).map(x=>clean(x.value)).join(', ')||'Not recorded'}\n${where?`Lands on: ${where.whole?'whole app':clean(where.parts.map(c=>c.name).join(', '))}${where.near.length?`; check next: ${clean(where.near.map(c=>c.name).join(', '))}`:''}\n`:''}Next step: ${clean(f.app_impact?.review_question||'Verify the evidence against the app before making changes.')}\n\n`;
  }
  return text+'A review candidate does not establish impact, safety, or compliance. First observations establish baselines; a quiet inbox is not proof of complete coverage.\n';
 }
 return {create,digest};
})();

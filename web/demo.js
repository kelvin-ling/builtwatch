/* Explicit local simulation. Never calls a model, network service, or account API. */
(function(root){
 let seed,desk;
 const clone=x=>structuredClone(x);
 const serviceNames=[['Gmail API',['gmail']],['HubSpot',['hubspot']],['Stripe API',['stripe']],['Amazon Bedrock',['amazon bedrock','bedrock']],['Slack',['slack']],['GitHub',['github']],['Cloudflare Workers',['cloudflare workers']],['Twilio',['twilio']],['SendGrid',['sendgrid']],['OpenAI API',['openai']]];
 const technologyNames=[['Python',['python']],['JavaScript',['javascript']],['TypeScript',['typescript']],['Node.js',['node.js','nodejs']],['React',['react']]];
 const cleanText=(value,label,max)=>{if(typeof value!=='string'||!value.trim())throw Error(`${label} is required.`);const result=value.trim();if(result.length>max)throw Error(`${label} is too long.`);return result;};
 const cleanList=(value,label)=>{if(value==null)return [];if(!Array.isArray(value)||value.some(x=>typeof x!=='string'))throw Error(`${label} must be a list of text values.`);return value.map(x=>x.trim()).filter(Boolean);};
 function normalizeSystem(item){
  if(!item||typeof item!=='object'||Array.isArray(item))throw Error('A profile must be a JSON object.');
  const id=cleanText(item.id,'System ID',160);if(!/^[\p{L}\p{N}_-]+$/u.test(id))throw Error('System ID must use letters, numbers, dashes, or underscores.');
  const normalized={...clone(item),schema_version:1,id,name:cleanText(item.name,'System name',120),purpose:cleanText(item.purpose,'Purpose',12000)};
  for(const key of ['services','technologies','data_categories','assumptions','constraints','jurisdictions','unknowns'])normalized[key]=cleanList(item[key],key);
  if(item.consequential_actions!=null&&!Array.isArray(item.consequential_actions))throw Error('consequential_actions must be a list.');
  normalized.consequential_actions=(item.consequential_actions||[]).map(action=>{if(!action||typeof action!=='object'||typeof action.description!=='string'||!action.description.trim())throw Error('Each important action needs a description.');return {...clone(action),description:action.description.trim()};});
  normalized.provenance=item.provenance&&typeof item.provenance==='object'&&!Array.isArray(item.provenance)?clone(item.provenance):{};
  normalized.source_agent=typeof item.source_agent==='string'&&item.source_agent.trim()?item.source_agent.trim().slice(0,120):null;
  return normalized;
 }
 function init(data){seed=clone(data);desk=clone(seed);return desk;}
 function reset(){desk=clone(seed);return desk;}
 function profile(text,id,sourceAgent){const description=cleanText(text,'Summary',12000);if(description.length<20)throw Error('Use an agent summary with at least 20 characters.');const lower=description.toLowerCase(),matches=items=>items.filter(([,aliases])=>aliases.some(alias=>lower.includes(alias))).map(([name])=>name),stamp=new Date().toISOString(),name=description.split(/[.!\n]/)[0].trim().slice(0,80)||'My demo app';return {schema_version:1,id:id||'demo-'+crypto.randomUUID().slice(0,8),name,purpose:description.slice(0,600),services:matches(serviceNames),technologies:matches(technologyNames),consequential_actions:[],data_categories:[],assumptions:[],constraints:/\b(approve|approval|human review|person (?:must |to )?reviews?|person (?:must |to )?approve)\b/.test(lower)?['A person reviews or approves the system output']:[],jurisdictions:['Canada','United States','United Kingdom','European Union'].filter(place=>lower.includes(place.toLowerCase())),unknowns:['Review the optional details before relying on this demo profile.'],provenance:{},source_agent:sourceAgent||'Agent summary',created_at:stamp,updated_at:stamp};}
 async function request(path,body,method){
  if(path==='/api/intake'){
   if(method==='DELETE'){delete desk.draft;return {};}
   desk.draft={profile:profile(body?.description,body?.system_id,body?.source_agent)};desk.job={status:'complete',message:'Local demo draft ready. No AI call was made.'};return {};
  }
  if(path==='/api/systems/bulk'){
   const items=body?.systems;if(!Array.isArray(items)||!items.length||items.length>10)throw Error('Import between one and ten apps.');
   const normalized=items.map(normalizeSystem);if(new Set(normalized.map(x=>x.id)).size!==normalized.length)throw Error('Each app needs a different ID.');
   if(new Set([...desk.systems.map(x=>x.id),...normalized.map(x=>x.id)]).size>10)throw Error('Import up to ten apps in total.');
   const ids=new Set(normalized.map(x=>x.id)),existing=new Set(desk.systems.map(x=>x.id));desk.systems=desk.systems.filter(x=>!ids.has(x.id)).concat(normalized);return {imported:normalized.length,updated:[...ids].filter(id=>existing.has(id)).length};
  }
  if(path==='/api/systems'){
   const normalized=normalizeSystem(body);
   if(desk.systems.length>=10&&!desk.systems.some(x=>x.id===normalized.id))throw Error('Try up to ten systems, or reset the demo.');
   desk.systems=desk.systems.filter(x=>x.id!==normalized.id);desk.systems.push(normalized);return {};
  }
  if(path.startsWith('/api/systems/')&&method==='DELETE'){const id=decodeURIComponent(path.split('/').pop());desk.systems=desk.systems.filter(x=>x.id!==id);desk.findings=desk.findings.filter(x=>x.system_id!==id);return {};}
  if(path==='/api/dispositions'){const f=desk.findings.find(x=>x.id===body.finding_id);if(f)f.disposition=body.action;return {};}
  if(path==='/api/preferences'){desk.account={automatic_checks:false};return {};}
  if(path==='/api/feedback'&&method==='POST'){
   const kind=String(body?.kind||'').trim(),message=String(body?.message||'').trim();
   if(!['helpful','confusing','suggestion','issue'].includes(kind))throw Error('Choose a feedback category.');
   if(message.length<2||message.length>2000)throw Error('Keep feedback between 2 and 2,000 characters.');
   desk.feedback=[...(desk.feedback||[]),{id:'demo-feedback-'+crypto.randomUUID().slice(0,8),kind,message,page:body?.page||'overview',created_at:Date.now()}];return {saved:true};
  }
  if(path==='/api/scan'){
   // Replays only the actual saved example assessments; custom apps are never falsely assessed.
   const ids=new Set(desk.systems.map(x=>x.id));desk.findings=clone(seed.findings).filter(x=>ids.has(x.system_id));
   desk.job={status:'complete',message:'Historical example findings replayed. Custom demo apps were not assessed. No live fetch or AI call.'};return {};
  }
  throw Error('This action is only available in a signed-in workspace.');
 }
 root.BuiltWatchDemo={init,reset,request,get:()=>desk};
})(typeof window!=='undefined'?window:globalThis);

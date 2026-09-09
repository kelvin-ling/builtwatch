/* Explicit local simulation. Never calls a model, network service, or account API. */
(function(root){
 let seed,desk;
 const clone=x=>structuredClone(x);
 function init(data){seed=clone(data);desk=clone(seed);return desk;}
 function reset(){desk=clone(seed);return desk;}
 function profile(text,id){const stamp=new Date().toISOString();return {schema_version:1,id:id||'demo-'+crypto.randomUUID().slice(0,8),name:text.split(/[.!\n]/)[0].slice(0,80)||'My demo app',purpose:text.slice(0,600),services:['Gmail','HubSpot','Stripe','Amazon Bedrock','Slack','OpenAI'].filter(x=>text.toLowerCase().includes(x.toLowerCase())),technologies:['Python','JavaScript'].filter(x=>text.toLowerCase().includes(x.toLowerCase())),consequential_actions:[],data_categories:[],assumptions:[],constraints:[],jurisdictions:[],unknowns:['Local demo uses simple text matching, not AI. Review details in the optional editor.'],provenance:{},created_at:stamp,updated_at:stamp};}
 async function request(path,body,method){
  if(path==='/api/intake'){
   if(method==='DELETE'){delete desk.draft;return {};}
   desk.draft={profile:profile(body.description,body.system_id)};desk.job={status:'complete',message:'Local demo draft ready. No AI call was made.'};return {};
  }
  if(path==='/api/systems'){
   if(!body?.id||!body.name||!body.purpose)throw Error('A profile needs an ID, name and purpose.');
   if(desk.systems.length>=10&&!desk.systems.some(x=>x.id===body.id))throw Error('Try up to ten systems, or reset the demo.');
   desk.systems=desk.systems.filter(x=>x.id!==body.id);desk.systems.push({...profile(body.purpose,body.id),...clone(body)});return {};
  }
  if(path.startsWith('/api/systems/')&&method==='DELETE'){const id=decodeURIComponent(path.split('/').pop());desk.systems=desk.systems.filter(x=>x.id!==id);desk.findings=desk.findings.filter(x=>x.system_id!==id);return {};}
  if(path==='/api/dispositions'){const f=desk.findings.find(x=>x.id===body.finding_id);if(f)f.disposition=body.action;return {};}
  if(path==='/api/preferences'){desk.account={automatic_checks:false};return {};}
  if(path==='/api/scan'){
   // Replays only the actual saved example assessments; custom apps are never falsely assessed.
   const ids=new Set(desk.systems.map(x=>x.id));desk.findings=clone(seed.findings).filter(x=>ids.has(x.system_id));
   desk.job={status:'complete',message:'Historical example findings replayed. Custom demo apps were not assessed. No live fetch or AI call.'};return {};
  }
  throw Error('This action is only available in a signed-in workspace.');
 }
 root.BuiltWatchDemo={init,reset,request,get:()=>desk};
})(typeof window!=='undefined'?window:globalThis);

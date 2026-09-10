/* Presentation preferences only. Never changes permissions, evidence or scan scope. */
(function(root){
 const views={
  business:{name:'Business',description:'Customer impact, responsibilities and the assumptions behind your automations.',order:['business_news','communications','regulation','privacy_ai','vendor_policy','standards','api_change','security']},
  operations:{name:'Operations',description:'Continuity, handoffs, service limits and work that needs a person.',order:['vendor_policy','communications','api_change','business_news','standards','privacy_ai','regulation','security']},
  technical:{name:'Technical',description:'Integrations, platform changes, security and the underlying evidence.',order:['api_change','security','vendor_policy','standards','privacy_ai','regulation','communications','business_news']}
 };
 const topics={business_news:'Business developments',communications:'Reaching customers',regulation:'Rules & responsibilities',privacy_ai:'Data, consent & AI',vendor_policy:'Service rules & limits',api_change:'Connected services',security:'Security & continuity',standards:'Good practice & oversight'};
 const normalize=value=>Object.hasOwn(views,value)?value:'business';
 function ordered(items,sources,lens){const order=views[normalize(lens)].order;const categories=new Map(sources.map(x=>[x.id,x.category]));return [...items].sort((a,b)=>{const rank=x=>{const index=order.indexOf(categories.get(x.source_id));return index<0?99:index;};return rank(a)-rank(b);});}
 function topic(f,sources){return topics[sources.find(x=>x.id===f.source_id)?.category]||'Other developments';}
 function context(system){return {actions:(system.consequential_actions||[]).map(x=>x.description),assumptions:system.assumptions||[],limits:system.constraints||[],regions:system.jurisdictions||[]};}
 const shorten=(value,max=112)=>{const text=String(value||'').trim().replace(/\s+/g,' ');if(text.length<=max)return text;const cut=text.slice(0,max-1),word=cut.slice(0,cut.lastIndexOf(' '));return (word||cut)+'…';};
 const plainChange=value=>String(value||'')
  .replace(/^Assessing relevance of (.+?) to ['"][^'"]+['"]$/i,'$1')
  .replace(/^Insufficient information to determine relevance of (.+?) to .+$/i,'$1')
  .replace(/^Assessment of ['"][^'"]+['"] against /i,'')
  .replace(/\s+Relevance Assessment$/i,'')
  .trim();
 const plainGap=value=>String(value||'').replace(/(?:the\s+)?['"][^'"]+['"]\s+system/gi,'this app').replace(/\bthe this app\b/gi,'this app').trim();

 function factIndex(system){const out={purpose:system?.purpose};for(const key of ['technologies','services','data_categories','assumptions','constraints','jurisdictions'])for(const [i,value] of (system?.[key]||[]).entries())out[`${key}[${i}]`]=value;for(const [i,value] of (system?.consequential_actions||[]).entries())out[`consequential_actions[${i}]`]=value.description;return out;}
 function brief(f,system){
  const norm=x=>String(x??'').trim().replace(/\s+/g,' ').toLowerCase(),index=factIndex(system);
  const refs=f.system_facts||[],valid=refs.filter(x=>Object.hasOwn(index,x.key)&&norm(index[x.key])===norm(x.value));
  const preferred=['consequential_actions','assumptions','constraints','services','data_categories','jurisdictions','technologies','purpose'];
  const rank=x=>{const n=preferred.indexOf(x.key.split('[')[0]);return n<0?99:n;};
  const ref=valid.find(x=>x.key===f.app_impact?.fact_key)||[...valid].sort((a,b)=>rank(a)-rank(b))[0];
  const stale=refs.some(x=>!valid.includes(x));
  const fieldLabels={purpose:'Purpose',consequential_actions:'Action',assumptions:'Assumption',constraints:'Boundary',services:'Service',data_categories:'Data',jurisdictions:'Region',technologies:'Technology'};
  return {app:system?.name||f.system_id,purpose:system?.purpose||'Purpose not recorded',
   connection:ref?ref.value:'No matching recorded detail establishes the connection yet.',
   connectionLabel:ref?fieldLabels[ref.key.split('[')[0]]||'Recorded detail':'Connection not established',
   change:shorten(f.facts?.[0]||plainChange(f.title),150),
   consequence:stale?'The app profile changed after this assessment. Recheck the connection before acting.':f.relevance==='not_relevant'?(f.inferences?.[0]||'No applicable connection was established.'):f.relevance==='insufficient_information'?(f.unknowns?.[0]||'The effect on this app is not established.'):(f.app_impact?.consequence||f.inferences?.[0]||'A specific consequence was not established in this assessment.'),
   review:stale?'Does the finding still apply to the app’s current behavior?':f.relevance==='not_relevant'?'No action requested for this assessment.':f.app_impact?.review_question||f.review_suggestions?.[0]||'Which recorded activity or condition would make this development apply?',
   stale,anchored:!!ref,structured:!!f.app_impact};
 }
 function isEvidenceFailure(f){return (f.relevance!=='not_relevant'&&Array.isArray(f.evidence)&&f.evidence.length===0)||!!f.validation_issues?.length||(f.unknowns||[]).some(x=>/downgraded automatically|could not verify the suggested connection|not grounded|not found verbatim|cited snapshot|snap_[a-f0-9]+/i.test(x));}
 function readableGap(f){
  const gap=(f.unknowns||[]).find(x=>!/downgraded automatically|could not verify the suggested connection|not grounded|not found verbatim|cited snapshot|snap_[a-f0-9]+/i.test(x));
  if(!gap)return 'BuiltWatch is missing a fact needed to connect this development to the app.';
  const readable=plainGap(gap);
  if(/^whether\b/i.test(readable))return `Confirm ${readable.slice(8).replace(/[.]$/, '')}.`;
  return `Confirm this detail: ${readable.replace(/[.]$/, '')}.`;
 }
 function diagnosis(f,system){
  const b=brief(f,system);
  if(b.stale)return {status:'App details changed',problemLabel:"What's wrong",problem:'This result refers to an older version of the app profile.',actionLabel:'What to do next',action:'Update the app profile if needed, then run the check again before changing the app.',owner:'You'};
  if(isEvidenceFailure(f))return {status:'BuiltWatch could not verify this',problemLabel:"What's wrong",problem:'The suggested connection is missing a source passage that proves it. BuiltWatch blocked it so it cannot be mistaken for a real alert.',actionLabel:'What to do next',action:'Do not change the app based on this item. BuiltWatch must check the source again; only act on a later result that includes quoted evidence.',owner:'BuiltWatch'};
  if(f.relevance==='insufficient_information')return {status:'Your input is needed',problemLabel:'Question to answer',problem:readableGap(f),actionLabel:'Next step',action:'Verify this detail, update the app profile, then run the check again.',owner:'You'};
  if(f.relevance==='not_relevant')return {status:'No app change needed',problemLabel:'Why it does not apply',problem:b.consequence,actionLabel:'What to do next',action:'Nothing needs fixing for this item. Revisit it only if the app or its dependencies change.',owner:'No action'};
  return {status:'Review this app',problemLabel:'Possible problem',problem:b.consequence,actionLabel:'What to do next',action:b.review,owner:'You'};
 }
 function requiresAttention(f,system){
  if((f.disposition||'open')!=='open')return false;
  if(f.relevance==='relevant')return true;
  return f.relevance==='insufficient_information'&&diagnosis(f,system).owner!=='BuiltWatch';
 }
 function automation(system,finding){
  const first=(items,fallback)=>items?.[0]||fallback;
  const map={
   input:{label:system?.services?.length?'Connected service':system?.data_categories?.length?'Information used':'Starting point',value:first(system?.services,first(system?.data_categories,'Not recorded yet'))},
   work:{label:'What it does',value:shorten(first((system?.consequential_actions||[]).map(x=>x.description),system?.purpose||'Purpose not recorded'))},
   checkpoint:{label:'Human approval or limit',value:shorten(first(system?.constraints,'None recorded'))},
   condition:{label:'Important condition',value:shorten(first(system?.assumptions,first(system?.jurisdictions,'None recorded')))}
  };
  if(!finding)return {...map,event:null,anchor:'condition'};
  const b=brief(finding,system),anchors={Service:'input',Data:'input',Technology:'input',Action:'work',Purpose:'work',Boundary:'checkpoint',Assumption:'condition',Region:'condition'};
  return {...map,event:{change:b.change,connection:b.connection,review:b.review,stale:b.stale},anchor:anchors[b.connectionLabel]||'condition'};
 }
 function grouped(items,systems){const groups=new Map();for(const f of items){if(!groups.has(f.system_id))groups.set(f.system_id,{system:systems.find(x=>x.id===f.system_id)||{id:f.system_id,name:f.system_id,purpose:'App profile unavailable'},findings:[]});groups.get(f.system_id).findings.push(f);}return [...groups.values()];}
 root.BuiltWatchPerspectives={views,topics,normalize,ordered,topic,context,brief,diagnosis,requiresAttention,automation,grouped};
})(typeof window!=='undefined'?window:globalThis);

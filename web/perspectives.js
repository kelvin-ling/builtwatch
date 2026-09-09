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
   change:f.facts?.[0]||f.title,
   consequence:stale?'The app profile changed after this assessment. Recheck the connection before acting.':f.relevance==='not_relevant'?(f.inferences?.[0]||'No applicable connection was established.'):f.relevance==='insufficient_information'?(f.unknowns?.[0]||'The effect on this app is not established.'):(f.app_impact?.consequence||f.inferences?.[0]||'A specific consequence was not established in this assessment.'),
   review:stale?'Does the finding still apply to the app’s current behavior?':f.relevance==='not_relevant'?'No action requested for this assessment.':f.app_impact?.review_question||f.review_suggestions?.[0]||'Which recorded activity or condition would make this development apply?',
   stale,anchored:!!ref,structured:!!f.app_impact};
 }
 function automation(system,finding){
  const first=(items,fallback)=>items?.[0]||fallback;
  const map={
   input:{label:system?.services?.length?'Connected service':system?.data_categories?.length?'Information used':'Starting point',value:first(system?.services,first(system?.data_categories,'Not recorded yet'))},
   work:{label:'Automated work',value:first((system?.consequential_actions||[]).map(x=>x.description),system?.purpose||'Purpose not recorded')},
   checkpoint:{label:'Human or system checkpoint',value:first(system?.constraints,'Checkpoint not recorded yet')},
   condition:{label:'Real-world condition',value:first(system?.assumptions,first(system?.jurisdictions,'Outside condition not recorded yet'))}
  };
  if(!finding)return {...map,event:null,anchor:'condition'};
  const b=brief(finding,system),anchors={Service:'input',Data:'input',Technology:'input',Action:'work',Purpose:'work',Boundary:'checkpoint',Assumption:'condition',Region:'condition'};
  return {...map,event:{change:b.change,connection:b.connection,review:b.review,stale:b.stale},anchor:anchors[b.connectionLabel]||'condition'};
 }
 function grouped(items,systems){const groups=new Map();for(const f of items){if(!groups.has(f.system_id))groups.set(f.system_id,{system:systems.find(x=>x.id===f.system_id)||{id:f.system_id,name:f.system_id,purpose:'App profile unavailable'},findings:[]});groups.get(f.system_id).findings.push(f);}return [...groups.values()];}
 root.BuiltWatchPerspectives={views,topics,normalize,ordered,topic,context,brief,automation,grouped};
})(typeof window!=='undefined'?window:globalThis);

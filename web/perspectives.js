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
 root.BuiltWatchPerspectives={views,topics,normalize,ordered,topic,context};
})(typeof window!=='undefined'?window:globalThis);

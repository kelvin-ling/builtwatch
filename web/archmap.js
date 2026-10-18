/* Backend map: the app's components, supplied by the user's project agent (or drawn from
   the profile when none was supplied), with every open review pinned on the component whose
   recorded dependency, data or action it matched. BuiltWatch never reads the app's code. */
(function(root){
 const COLUMNS=[
  {key:'entry',label:'Entry points',kinds:['entry'],count:['entry point','entry points']},
  {key:'service',label:'Your services',kinds:['service'],count:['service','services']},
  {key:'data',label:'Data & AI models',kinds:['data','model'],count:['data store or model','data stores or models']},
  {key:'external',label:'Outside services',kinds:['external'],count:['outside service','outside services']}];
 const KINDS=['entry','service','data','model','external'];
 const ICONS={entry:'import',service:'apps',data:'database',model:'spark',external:'globe'};
 const KIND_LABEL={entry:'Entry point',service:'Service',data:'Data store',model:'AI model',external:'Outside service'};
 const SLUG=/^[a-z0-9][a-z0-9_-]{0,39}$/;
 const LIMITS={components:24,flows:48,uses:12,data:8,actions:6};
 const MODEL_HINT=/\b(bedrock|openai|anthropic|claude|gemini|llm|nova|mistral|llama|cohere|model)\b/i;
 const fold=x=>String(x??'').trim().replace(/\s+/g,' ').toLowerCase();
 const esc=x=>root.BuiltWatchVisuals.escape(x);
 const short=(x,n)=>root.BuiltWatchVisuals.short(x,n);
 const icon=n=>root.BuiltWatchVisuals.icon(n);
 const factKind=key=>/^(services|technologies)\[/.test(key)?'uses':/^data_categories\[/.test(key)?'data':/^consequential_actions\[/.test(key)?'actions':null;
 const list=x=>Array.isArray(x)?x.filter(v=>typeof v==='string'&&v.trim()).map(v=>v.trim()):[];

 // Without a supplied map, draw what the profile already states: the app, the outside
 // services it records, and its data. Labelled as derived so it is not mistaken for analysis.
 function derive(system){
  const services=list(system?.services),technologies=list(system?.technologies);
  const app={id:'app',name:system?.name||'This app',kind:'service',purpose:short(system?.purpose||'',140),uses:technologies,
   data:list(system?.data_categories),actions:(system?.consequential_actions||[]).map(a=>a?.description).filter(Boolean)};
  const outside=services.map((name,i)=>({id:'svc-'+i,name,kind:MODEL_HINT.test(name)?'model':'external',purpose:'',uses:[name],data:[],actions:[]}));
  return {derived:true,components:[app,...outside],flows:outside.map(c=>({source:'app',target:c.id,label:''}))};
 }

 function architecture(system){return system?.architecture?.components?.length?{...system.architecture,derived:false}:derive(system);}

 // Same rules as the server's SystemPassport validator, plus the profile additions a save
 // would need so every component dependency is also watched.
 function validate(system,input){
  const errors=[],raw=input&&typeof input==='object'&&!Array.isArray(input)?(input.architecture&&typeof input.architecture==='object'?input.architecture:input):null;
  if(!raw)return {ok:false,errors:['Paste a JSON object with an "architecture" or a "components" list.']};
  if(!Array.isArray(raw.components)||!raw.components.length)return {ok:false,errors:['The map needs at least one component.']};
  if(raw.components.length>LIMITS.components)errors.push(`Use at most ${LIMITS.components} components.`);
  const flowsIn=raw.flows==null?[]:raw.flows;
  if(!Array.isArray(flowsIn))errors.push('"flows" must be a list.');
  else if(flowsIn.length>LIMITS.flows)errors.push(`Use at most ${LIMITS.flows} flows.`);
  const ids=new Set(),components=[];
  raw.components.forEach((c,i)=>{
   const at=`Component ${i+1}`;
   if(!c||typeof c!=='object'){errors.push(`${at} must be an object.`);return;}
   const id=String(c.id??'').trim();
   if(!SLUG.test(id))errors.push(`${at}: id "${id}" must be a short lowercase slug (letters, numbers, - or _).`);
   else if(ids.has(id))errors.push(`${at}: id "${id}" is used twice.`);
   ids.add(id);
   const name=String(c.name??'').trim();
   if(!name||name.length>80)errors.push(`${at}: name is required (80 characters max).`);
   if(!KINDS.includes(c.kind))errors.push(`${at}: kind must be one of ${KINDS.join(', ')}.`);
   const purpose=typeof c.purpose==='string'?c.purpose.trim():'';
   if(purpose.length>200)errors.push(`${at}: purpose must be 200 characters or fewer.`);
   const item={id,name,kind:c.kind,purpose};
   for(const key of ['uses','data','actions']){
    if(c[key]!=null&&!Array.isArray(c[key]))errors.push(`${at}: ${key} must be a list.`);
    item[key]=list(c[key]);
    if(item[key].length>LIMITS[key])errors.push(`${at}: use at most ${LIMITS[key]} ${key} entries.`);
    if(item[key].some(v=>v.length>200))errors.push(`${at}: ${key} entries must be 200 characters or fewer.`);
   }
   components.push(item);
  });
  const flows=[];
  if(Array.isArray(flowsIn))flowsIn.forEach((f,i)=>{
   const source=String(f?.source??'').trim(),target=String(f?.target??'').trim(),label=typeof f?.label==='string'?f.label.trim():'';
   if(!ids.has(source)||!ids.has(target))errors.push(`Flow ${i+1}: "${source}" → "${target}" names an unknown component.`);
   else if(source===target)errors.push(`Flow ${i+1} must connect two different components.`);
   if(label.length>80)errors.push(`Flow ${i+1}: label must be 80 characters or fewer.`);
   flows.push({source,target,label});
  });
  const analyzedBy=typeof raw.analyzed_by==='string'&&raw.analyzed_by.trim()?raw.analyzed_by.trim().slice(0,120):null;
  const analyzedAt=typeof raw.analyzed_at==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(raw.analyzed_at)?raw.analyzed_at:null;
  if(errors.length)return {ok:false,errors};
  const known={deps:new Set([...list(system?.services),...list(system?.technologies)].map(fold)),data:new Set(list(system?.data_categories).map(fold)),
   actions:new Set((system?.consequential_actions||[]).map(a=>fold(a?.description)))};
  const additions={services:[],technologies:[],data_categories:[],consequential_actions:[]},seen=new Set();
  const add=(bucket,value)=>{const k=bucket+':'+fold(value);if(!seen.has(k)){seen.add(k);additions[bucket].push(value);}};
  for(const c of components){
   for(const v of c.uses)if(!known.deps.has(fold(v)))add(['external','model'].includes(c.kind)?'services':'technologies',v);
   for(const v of c.data)if(!known.data.has(fold(v)))add('data_categories',v);
   for(const v of c.actions)if(!known.actions.has(fold(v)))add('consequential_actions',v);
  }
  return {ok:true,errors:[],architecture:{analyzed_by:analyzedBy,analyzed_at:analyzedAt,components,flows},additions};
 }

 // Apply a validated map to a profile: record the new facts it introduces (so checks watch
 // them) and say so in provenance.
 function apply(system,result){
  const a=result.additions,next={...system,architecture:result.architecture};
  next.services=[...list(system.services),...a.services];
  next.technologies=[...list(system.technologies),...a.technologies];
  next.data_categories=[...list(system.data_categories),...a.data_categories];
  next.consequential_actions=[...(system.consequential_actions||[]),...a.consequential_actions.map(description=>({description}))];
  next.provenance={...(system.provenance||{}),architecture:'agent_extracted'};
  return next;
 }

 // Before any profile save: keep an existing map when an update omits it, and drop map
 // entries whose fact the person just removed from the profile, so the save stays valid.
 function reconcile(next,previous){
  if(!next||typeof next!=='object')return next;
  if(next.remove_architecture===true)return {...next,architecture:null};
  // Missing and null both mean "not resent"; the server keeps the saved map the same way.
  const arch=next.architecture??previous?.architecture;
  if(!arch?.components?.length)return {...next,architecture:arch??null};
  const deps=new Set([...list(next.services),...list(next.technologies)].map(fold)),data=new Set(list(next.data_categories).map(fold)),
   actions=new Set((next.consequential_actions||[]).map(a=>fold(a?.description)));
  const components=arch.components.map(c=>({...c,uses:list(c.uses).filter(v=>deps.has(fold(v))),data:list(c.data).filter(v=>data.has(fold(v))),actions:list(c.actions).filter(v=>actions.has(fold(v)))}));
  return {...next,architecture:{...arch,components}};
 }

 // A map dated well before the profile's last change may miss new parts. Same-day edits
 // (saving the map itself updates the profile) do not count.
 function stale(system){
  const at=system?.architecture?.analyzed_at,updated=Date.parse(system?.updated_at||'');
  if(!at||!Number.isFinite(updated))return false;
  return updated-Date.parse(at+'T23:59:59Z')>24*3600*1000;
 }

 function neighbours(arch,ids){
  const near=new Set();
  for(const f of arch.flows||[]){if(ids.has(f.source)&&!ids.has(f.target))near.add(f.target);if(ids.has(f.target)&&!ids.has(f.source))near.add(f.source);}
  return near;
 }

 // Where each review lands. A review that cites only whole-app facts (purpose, rules,
 // regions) is listed as whole-app rather than forced onto a component.
 function place(system,findings=[],sources=[]){
  const arch=architecture(system),P=root.BuiltWatchPerspectives;
  const sets=arch.components.map(c=>({id:c.id,uses:new Set(list(c.uses).map(fold)),data:new Set(list(c.data).map(fold)),actions:new Set(list(c.actions).map(fold))}));
  const pins=findings.map((f,i)=>{
   const hits=new Map();
   for(const fact of f.system_facts||[]){
    const kind=factKind(fact.key||'');if(!kind)continue;
    for(const s of sets)if(s[kind].has(fold(fact.value))){if(!hits.has(s.id))hits.set(s.id,new Set());hits.get(s.id).add(fact.value);}
   }
   const b=P?.brief?P.brief(f,system):{change:f.title||''},d=P?.diagnosis?P.diagnosis(f,system):{action:''};
   return {n:i+1,id:f.id,components:[...hits.keys()],matched:Object.fromEntries([...hits].map(([k,v])=>[k,[...v]])),
    change:short(b.change||f.title||'',130),question:short(d.action||'',150),topic:P?.topic?P.topic(f,sources):'',stale:!!b.stale};
  });
  const direct=new Set(pins.flatMap(p=>p.components));
  return {arch,pins,direct,near:neighbours(arch,direct)};
 }

 // One review's placement in words, for cards, handoffs and digests. Only a supplied map
 // is quoted; a derived map would just repeat the matched detail.
 function landing(system,finding){
  const {arch,pins}=place(system,[finding]),pin=pins[0];
  if(arch.derived)return null;
  const byId=Object.fromEntries(arch.components.map(c=>[c.id,c])),hit=new Set(pin.components);
  return {parts:pin.components.map(id=>byId[id]),near:[...neighbours(arch,hit)].map(id=>byId[id]),whole:!pin.components.length};
 }

 function nodeHtml(c,{pins,lit,near,dim,compact,matched}){
  const chips=list(c.uses).concat(list(c.data));
  const hitValues=new Set((matched||[]).map(fold));
  const shown=compact?chips.filter(v=>hitValues.has(fold(v))).slice(0,2):chips.slice(0,4);
  const more=compact?0:chips.length-shown.length;
  const pinHtml=pins.map(p=>`<button class="flow-pin ${p.dim?'dim':''} ${p.stale?'stale':''}" data-finding="${esc(p.id)}" aria-label="Open review ${p.n}: ${esc(p.change)}">${p.n}</button>`).join('');
  const state=lit?'Direct impact. ':near?'Connected to an impacted component. ':'';
  return `<div class="arch-node kind-${esc(c.kind)} ${lit?'hit':''} ${near?'near':''} ${dim?'dim':''}" data-node="${esc(c.id)}" role="group" aria-label="${esc(state+KIND_LABEL[c.kind]+': '+c.name)}"><div class="arch-node-head"><span class="arch-icon">${icon(ICONS[c.kind]||'apps')}</span><strong>${esc(c.name)}</strong>${pinHtml?`<span class="arch-pins">${pinHtml}</span>`:''}</div>${!compact&&c.purpose?`<p>${esc(short(c.purpose,110))}</p>`:''}${shown.length?`<div class="arch-chips">${shown.map(v=>`<span class="${hitValues.has(fold(v))?'hit':''}">${esc(v)}</span>`).join('')}${more>0?`<span class="more">+${more}</span>`:''}</div>`:''}</div>`;
 }

 // `focus` highlights one review (inside its own dialog); `compact` trims node detail for
 // cards; `mapAction` adds the "Map backend with agent" control for that system id.
 function render(system,findings=[],{focus=null,compact=false,sources=[],mapAction=true}={}){
  const {arch,pins,direct,near}=place(system,findings,sources);
  const focused=focus?pins.find(p=>p.id===focus):null;
  const lit=focused?new Set(focused.components):direct,around=focused?neighbours(arch,lit):near;
  const byComponent=new Map(arch.components.map(c=>[c.id,[]]));
  for(const p of pins)for(const id of p.components)byComponent.get(id)?.push({...p,dim:!!focused&&p.id!==focused.id});
  // Cards are too narrow for every column: show only the hit parts and their neighbours,
  // stacked, and leave the whole map to the profile dialog.
  const subset=compact&&!focus?new Set([...lit,...around]):null;
  if(subset&&!subset.size){const kinds=COLUMNS.map(col=>{const n=arch.components.filter(c=>col.kinds.includes(c.kind)).length;return [col.count[n===1?0:1],n];}).filter(x=>x[1]);
   return `<section class="arch-map compact quiet" aria-label="Backend map of ${esc(system.name)}"><p class="arch-source">${arch.derived?'Drawn from the profile only.':`Mapped by ${esc(arch.analyzed_by||'your project agent')}.`} ${kinds.map(([l,n])=>`${n} ${esc(l)}`).join(' · ')}. No open review lands on this app.</p><div class="arch-card-actions"><button class="text-button" data-system="${esc(system.id)}">Open backend map →</button>${mapAction?`<button class="text-button" data-arch-map="${esc(system.id)}">${arch.derived?'Map backend with agent':'Update map'}</button>`:''}</div></section>`;}
  const shownComponents=subset?arch.components.filter(c=>subset.has(c.id)):arch.components;
  const cols=COLUMNS.map(col=>({...col,items:shownComponents.filter(c=>col.kinds.includes(c.kind))})).filter(col=>col.items.length);
  const links=(arch.flows||[]).filter(f=>!subset||(subset.has(f.source)&&subset.has(f.target))).map(f=>`${f.source}>${f.target}${lit.has(f.source)||lit.has(f.target)?'>hot':''}`).join(' ');
  const names=Object.fromEntries(arch.components.map(c=>[c.id,c.name]));
  const placed=pins.filter(p=>p.components.length),whole=pins.filter(p=>!p.components.length);
  const count=focused?0:pins.length;
  const source=arch.derived?'Drawn from the profile only. Map the backend with your agent to see components and data flows.'
   :`Mapped by ${esc(arch.analyzed_by||'your project agent')}${arch.analyzed_at?` · ${esc(arch.analyzed_at)}`:''}. BuiltWatch never reads your code.${stale(system)?' <strong class="arch-stale">The profile changed after this map was made; update the map so new parts are placed.</strong>':''}`;
  const hidden=subset?arch.components.length-shownComponents.length:0;
  const action=subset?`<button class="text-button" data-system="${esc(system.id)}">${hidden?`Full map · ${hidden} more ${hidden===1?'part':'parts'}`:'Open full map'} →</button>`:mapAction&&!focus?`<button class="text-button" data-arch-map="${esc(system.id)}">${arch.derived?'Map backend with agent':'Update map'} →</button>`:'';
  const canvas=`<div class="arch-canvas ${subset?'stacked':''}" style="--cols:${cols.length}" data-arch-links="${esc(links)}"><svg class="arch-lines" aria-hidden="true" focusable="false"></svg>${cols.map(col=>`<div class="arch-col"><span class="arch-col-label">${esc(col.label)}</span>${col.items.map(c=>nodeHtml(c,{pins:byComponent.get(c.id)||[],lit:lit.has(c.id),near:around.has(c.id),dim:!!focused&&!lit.has(c.id)&&!around.has(c.id),compact,matched:(focused?[focused]:pins).flatMap(p=>p.matched[c.id]||[])})).join('')}</div>`).join('')}</div>`;
  const legend=`<div class="arch-legend"><span><i class="direct"></i>Direct: a watched dependency, data or action changed</span><span><i class="near"></i>Connected: check next</span>${arch.flows?.length?'<span><i class="line"></i>Data flow</span>':''}</div>`;
  const landings=!focus&&placed.length?`<ol class="arch-landings">${placed.map(p=>`<li><button data-finding="${esc(p.id)}"><span class="flow-pin static" aria-hidden="true">${p.n}</span><span><small>${esc(p.topic)} → ${esc(p.components.map(id=>names[id]).join(', '))}</small><strong>${esc(p.change)}</strong>${p.question?`<em>Check: ${esc(p.question)}</em>`:''}</span></button></li>`).join('')}</ol>`:'';
  const wholeNote=whole.length&&(!focused||!focused.components.length)?`<p class="arch-whole">${focused?'This review cites whole-app facts (purpose, rules or regions), so it is not tied to one component.':`Whole app, not one component: ${whole.filter(p=>!focused||p.id===focused.id).map(p=>`<button class="flow-pin static-link" data-finding="${esc(p.id)}" aria-label="Open review ${p.n}">${p.n}</button>`).join(' ')}`}</p>`:'';
  const flowList=!compact&&!focus&&arch.flows?.length?`<details class="arch-flows"><summary>Data flows (${arch.flows.length})</summary><ul>${arch.flows.map(f=>`<li>${esc(names[f.source])} → ${esc(names[f.target])}${f.label?` · ${esc(f.label)}`:''}</li>`).join('')}</ul></details>`:'';
  const status=focused?`${focused.components.length} ${focused.components.length===1?'component':'components'} hit`:count?`${count} ${count===1?'change lands':'changes land'} here`:'No open review';
  return `<section class="arch-map ${compact?'compact':''} ${focus?'focused':''}" aria-label="Backend map of ${esc(system.name)}"><div class="arch-head"><div><span class="eyebrow">BACKEND MAP</span><h3>${focus?'Where this change lands':'Where outside changes land'}</h3><p class="arch-source">${source}</p></div><div class="arch-head-side"><span class="map-status ${focused||count?'hot':''}">${status}</span>${action}</div></div>${canvas}${legend}${wholeNote}${landings}${!count&&!focus?'<p class="arch-quiet">No open review lands on this app. Check coverage before treating that as an all-clear.</p>':''}${flowList}</section>`;
 }

 // Edges are measured from the laid-out nodes so they survive any column count. Nodes in
 // the same column connect with a bow on the right instead of crossing the cards between them.
 function drawEdges(rootEl){
  if(!rootEl?.querySelectorAll)return;
  for(const canvas of rootEl.querySelectorAll('.arch-canvas')){
   const svg=canvas.querySelector('.arch-lines');if(!svg)continue;
   const box=canvas.getBoundingClientRect();if(!box.width){svg.innerHTML='';continue;}
   const rect=id=>canvas.querySelector(`[data-node="${CSS.escape(id)}"]`)?.getBoundingClientRect();
   const f=n=>n.toFixed(1);
   const paths=(canvas.dataset.archLinks||'').split(' ').filter(Boolean).map(edge=>{
    const [from,to,hot]=edge.split('>'),a=rect(from),b=rect(to);if(!a||!b)return '';
    const ay=a.top+a.height/2-box.top,by=b.top+b.height/2-box.top;let d,ex,ey;
    if(b.left>=a.right-2){const x1=a.right-box.left,x2=b.left-box.left,m=(x2-x1)/2;d=`M${f(x1)} ${f(ay)} C${f(x1+m)} ${f(ay)} ${f(x2-m)} ${f(by)} ${f(x2)} ${f(by)}`;ex=x2;ey=by;}
    else if(a.left>=b.right-2){const x1=a.left-box.left,x2=b.right-box.left,m=(x1-x2)/2;d=`M${f(x1)} ${f(ay)} C${f(x1-m)} ${f(ay)} ${f(x2+m)} ${f(by)} ${f(x2)} ${f(by)}`;ex=x2;ey=by;}
    else{const x1=a.right-box.left,x2=b.right-box.left,bow=Math.max(x1,x2)+18;d=`M${f(x1)} ${f(ay)} C${f(bow)} ${f(ay)} ${f(bow)} ${f(by)} ${f(x2)} ${f(by)}`;ex=x2;ey=by;}
    return `<path class="${hot?'hot':''}" d="${d}"/><circle class="${hot?'hot':''}" cx="${f(ex)}" cy="${f(ey)}" r="3"/>`;
   }).join('');
   svg.setAttribute('viewBox',`0 0 ${box.width.toFixed(0)} ${box.height.toFixed(0)}`);svg.innerHTML=paths;
  }
 }

 function prompt(system){
  const names=x=>JSON.stringify(x||[]);
  return `Map the backend of my app "${system.name}" (BuiltWatch id: ${system.id}) from the code and configuration you can access. Read it locally. Do not send code anywhere, call outside services, or include source code, secrets, keys, tokens, internal URLs or customer records. Return only JSON in this shape: {"architecture":{"analyzed_by":"<your agent or workspace name>","analyzed_at":"YYYY-MM-DD","components":[{"id":"short-slug","name":"Readable name","kind":"entry|service|data|model|external","purpose":"One sentence","uses":["vendors, APIs, runtimes or frameworks this component depends on"],"data":["data categories it handles"],"actions":["consequential actions it performs"]}],"flows":[{"source":"component-id","target":"component-id","label":"what moves"}]}}. Kinds: entry = UI, webhook, schedule, inbox or other trigger; service = my own API, worker, function or job; data = database, storage, queue or cache; model = AI model; external = third-party API or vendor. Use at most 24 components and 48 flows; ids are lowercase slugs. Reuse these exact names so outside changes are matched to components. Services: ${names(system.services)}. Technologies: ${names(system.technologies)}. Data: ${names(system.data_categories)}. Actions: ${names((system.consequential_actions||[]).map(a=>a.description))}. Add a new dependency name only if the code really uses it. Keep the JSON under 12 KB.`;
 }

 root.BuiltWatchArchMap={COLUMNS,KINDS,derive,architecture,validate,apply,reconcile,place,landing,stale,render,drawEdges,prompt};
})(typeof window!=='undefined'?window:globalThis);

/* Small, data-driven visuals. No network calls, external assets or invented metrics. */
(function(root){
 const escape=(value='')=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const paths={
  apps:'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
  radar:'M12 3a9 9 0 1 0 9 9 M12 7a5 5 0 1 0 5 5 M12 12l8-8 M17 3h4v4',
  review:'M12 3l10 18H2z M12 9v5 M12 17h.01',
  check:'M5 12l4 4L19 6',
  arrow:'M5 12h14 M13 6l6 6-6 6',
  link:'M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-2 2 M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l2-2',
  source:'M5 3h10l4 4v14H5z M14 3v5h5 M8 12h8 M8 16h5',
  clock:'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0 M12 7v5l3 2',
  import:'M12 3v12 M7 10l5 5 5-5 M4 15v6h16v-6',
  database:'M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3z M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6 M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3',
  spark:'M12 3v4 M12 17v4 M3 12h4 M17 12h4 M6 6l2.5 2.5 M15.5 15.5L18 18 M6 18l2.5-2.5 M15.5 8.5L18 6',
  globe:'M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18 M3 12h18 M12 3c3 3.5 3 14.5 0 18 M12 3c-3 3.5-3 14.5 0 18',
  shield:'M12 2l9 4v6c0 5-9 10-9 10S3 17 3 12V6z M8 12l3 3 5-6',
 };
 const icon=(name)=>`<svg class="bw-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[name]||paths.apps}"/></svg>`;
 const short=(value,max=110)=>{const s=String(value||'').trim().replace(/\s+/g,' ');return s.length<=max?s:s.slice(0,max-1).replace(/\s+\S*$/,'')+'…';};
 function metrics(state,findings){
  const summary=root.BuiltWatchStatus.workspace(state,findings.length);
  const health=summary.latest?.source_health||[];
  const failed=health.filter(x=>x.fetch_status!=='ok').length;
  const covered=health.filter(x=>x.fetch_status==='ok').length;
  const categories=new Set((state.sources||[]).map(x=>x.category));
  const items=[
   ['apps',state.systems.length,'Saved systems',state.demo?'Examples + local profiles':'Your monitored inventory','systems'],
   ['radar',state.sources.length,'Curated sources',`${categories.size} source categories`,'sources'],
   ['review',findings.length,'Need review','Possible matches, not confirmed impact','findings'],
   ['check',`${covered}/${state.sources.length}`,state.demo?'Replay coverage':'Latest source coverage',failed?`${failed} source${failed===1?'':'s'} could not be checked`:health.length?'Successful source fetches':'Waiting for a first check','history'],
  ];
  return `<section class="desk-metrics" aria-label="Workspace at a glance">${items.map(([i,n,title,note,view])=>`<button class="desk-metric ${view==='findings'&&findings.length?'has-reviews':''}" data-view="${view}"><span class="metric-icon">${icon(i)}</span><strong>${escape(n)}</strong><span>${title}</span><small>${escape(note)}</small><b aria-hidden="true">↗</b></button>`).join('')}</section>`;
 }
 // Source categories → saved apps → reviews. Lines are drawn after layout from the real
 // open reviews; the same links are also written as text ("via …") so nothing depends on
 // seeing the lines. No link is drawn for a category that produced no open review.
 function map(state,findings){
  const P=root.BuiltWatchPerspectives,systems=state.systems.slice(0,4),counts=new Map(),via=new Map(),links=new Set();
  const topicKey=new Map(Object.entries(P.topics).map(([k,v])=>[v,k]));
  for(const f of findings){
   counts.set(f.system_id,(counts.get(f.system_id)||0)+1);
   const t=P.topic(f,state.sources||[]),key=topicKey.get(t)||'other';
   // With a supplied backend map, say which part the change reaches, not just the topic.
   const app=systems.find(s=>s.id===f.system_id),l=app&&root.BuiltWatchArchMap?.landing(app,f);
   const label=l&&!l.whole?`${t} → ${l.parts.map(c=>c.name).join(', ')}`:t;
   if(!via.has(f.system_id))via.set(f.system_id,new Set());via.get(f.system_id).add(label);
   if(systems.some(s=>s.id===f.system_id))links.add(key+'|'+f.system_id);
  }
  const cats=new Map();for(const s of state.sources||[])cats.set(s.category,(cats.get(s.category)||0)+1);
  const hot=new Set([...links].map(x=>x.split('|')[0]));
  const catNodes=[...cats].sort((a,b)=>Number(hot.has(b[0]))-Number(hot.has(a[0]))).map(([key,n])=>`<button class="net-cat ${hot.has(key)?'hot':''}" data-node="cat:${escape(key)}" data-view="sources"><span>${escape(P.topics[key]||key)}</span><small>${n}</small></button>`).join('');
  const appNodes=systems.length?systems.map(s=>{const count=counts.get(s.id)||0,v=[...(via.get(s.id)||[])];return `<button class="net-app ${count?'hot':''}" data-node="app:${escape(s.id)}" data-system="${escape(s.id)}"><span class="app-node-icon">${icon('apps')}</span><span class="net-app-copy"><strong>${escape(s.name)}</strong><small title="${count?escape('via '+v.join(' · ')):''}">${count?'via '+escape(v.join(' · ')):escape([...(s.services||[]),...(s.technologies||[])].slice(0,2).join(' · ')||'Dependencies not recorded')}</small></span><b class="node-count ${count?'attention':''}" aria-label="${count} open ${count===1?'review':'reviews'}">${count||'—'}</b></button>`;}).join('')+(state.systems.length>4?`<button class="text-button network-more" data-view="systems">View all ${state.systems.length} systems →</button>`:''):`<button class="net-app network-empty" data-action="bulk-import">${icon('import')}<span class="net-app-copy"><strong>Bring your first system</strong><small>Import a profile from your project agent</small></span></button>`;
  const result=`<button class="net-result ${findings.length?'hot':''}" data-node="result" data-view="findings"><span>${icon(findings.length?'review':'check')}</span><strong>${findings.length}</strong><b>${findings.length===1?'possible match':'possible matches'}</b><small>${state.demo?'Saved review examples':'You or your agent verify impact'}</small></button>`;
  const edges=[...links].map(x=>{const [c,a]=x.split('|');return `cat:${c}>app:${a}`;}).concat(systems.filter(s=>counts.get(s.id)).map(s=>`app:${s.id}>result`));
  return `<section class="watch-network panel" aria-labelledby="network-title"><div class="network-heading"><div><span class="eyebrow">YOUR WATCH DESK</span><h2 id="network-title">See the connection.</h2><p>Outside sources → recorded dependencies → your next review.</p></div><span class="network-mode">${icon(state.demo?'clock':'shield')}${state.demo?'Historical examples':state.monitoring?.ai_briefs?'Rules + capped AI briefs':'No AI inference'}</span></div><div class="network-canvas" data-links="${escape(edges.join(' '))}"><svg class="network-lines" aria-hidden="true" focusable="false"></svg><div class="net-col net-cats"><span class="net-col-label">${state.sources.length} watched sources</span>${catNodes}${cats.size>hot.size?`<button class="net-cat net-cat-more" data-view="sources">+${cats.size-hot.size} more ${cats.size-hot.size===1?'category':'categories'}</button>`:''}</div><div class="net-col net-apps"><span class="net-col-label">Your systems</span>${appNodes}</div><div class="net-col net-out"><span class="net-col-label">Needs a look</span>${result}</div></div><div class="network-foot"><span><i></i>${state.demo?'Replay only. Custom demo profiles are not evaluated.':'Matches use recorded dependencies. Legal applicability is not assessed.'}</span><span class="network-key"><i class="hot"></i>Open review path</span><button class="text-button" data-view="guide">How it works ↗</button></div></section>`;
 }
 // Draws the curved links for every .network-canvas under root. Purely decorative: the
 // same relationships are stated as text in each node. Safe to call repeatedly.
 function drawLinks(rootEl){
  if(!rootEl?.querySelectorAll)return;
  for(const canvas of rootEl.querySelectorAll('.network-canvas')){
   const svg=canvas.querySelector('.network-lines');if(!svg)continue;
   const box=canvas.getBoundingClientRect();
   if(!box.width||getComputedStyle(svg).display==='none'){svg.innerHTML='';continue;}
   const node=id=>canvas.querySelector(`[data-node="${CSS.escape(id)}"]`)?.getBoundingClientRect();
   const paths=(canvas.dataset.links||'').split(' ').filter(Boolean).map(edge=>{
    const [from,to]=edge.split('>'),a=node(from),b=node(to);if(!a||!b)return '';
    const x1=a.right-box.left,y1=a.top+a.height/2-box.top,x2=b.left-box.left,y2=b.top+b.height/2-box.top,mid=(x2-x1)/2;
    return `<path d="M${x1.toFixed(1)} ${y1.toFixed(1)} C${(x1+mid).toFixed(1)} ${y1.toFixed(1)} ${(x2-mid).toFixed(1)} ${y2.toFixed(1)} ${x2.toFixed(1)} ${y2.toFixed(1)}"/><circle cx="${x2.toFixed(1)}" cy="${y2.toFixed(1)}" r="3"/>`;
   }).join('');
   svg.setAttribute('viewBox',`0 0 ${box.width.toFixed(0)} ${box.height.toFixed(0)}`);svg.innerHTML=paths;
  }
 }
 function categories(state,selected='all',openFindings=[]){
  const groups=new Map();for(const s of state.sources){if(!groups.has(s.category))groups.set(s.category,[]);groups.get(s.category).push(s);}
  const health=new Map((root.BuiltWatchStatus.workspace(state,0).latest?.source_health||[]).map(x=>[x.source_id,x]));
  const category=new Map(state.sources.map(s=>[s.id,s.category])),reach=new Map();
  for(const f of openFindings||[]){const c=category.get(f.source_id);if(c)reach.set(c,(reach.get(c)||0)+1);}
  return `<section class="source-atlas" aria-label="Source coverage by category">${[...groups].map(([key,sources])=>{const ok=sources.filter(s=>health.get(s.id)?.fetch_status==='ok').length,failed=sources.filter(s=>health.has(s.id)&&health.get(s.id).fetch_status!=='ok').length;return `<button class="atlas-card ${selected===key?'selected':''}" data-source-filter="${escape(key)}" aria-pressed="${selected===key}"><span class="atlas-icon">${icon(key==='security'?'shield':'source')}</span><strong>${escape(root.BuiltWatchPerspectives.topics[key]||key)}</strong><span class="atlas-count">${sources.length}<small>${sources.length===1?'source':'sources'}</small></span><span class="atlas-track" aria-hidden="true"><i style="width:${Math.round(ok/sources.length*100)}%"></i></span><small>${state.demo?'Replay': 'Latest check'} · ${ok}/${sources.length} fetched${failed?` · ${failed} failed`:''}</small>${reach.get(key)?`<b class="atlas-reach">→ ${reach.get(key)} open ${reach.get(key)===1?'review':'reviews'}</b>`:''}</button>`;}).join('')}</section>`;
 }
 function runHealth(run){
  const health=run.source_health||[],ok=health.filter(x=>x.fetch_status==='ok').length,failed=health.length-ok;
  return `<div class="run-health"><div class="run-segments" role="img" aria-label="${ok} sources fetched, ${failed} failed">${health.map(h=>`<span class="${h.fetch_status==='ok'?'ok':'failed'}" title="${escape(h.source_id)}: ${escape(h.fetch_status)}"></span>`).join('')}</div><span>${icon(failed?'review':'check')}${ok} fetched${failed?` · ${failed} failed`:''}</span></div>`;
 }
 // One bar for one run: fetched, failed, and listed-but-not-covered sources. Replaces a
 // paragraph of counts; the exact numbers stay in the legend for screen readers.
 function coverageBar(c,demo=false){
  const total=Math.max(1,c.checked+c.failed+c.unchecked),pct=n=>(n/total*100).toFixed(1);
  if(!c.checked&&!c.failed&&!c.unchecked)return `<p class="coverage-bar-empty">${demo?'Saved example coverage is shown in Check history.':'No check has run yet, so no source is covered.'}</p>`;
  return `<div class="coverage-bar"><div class="coverage-bar-track" role="img" aria-label="${c.checked} sources fetched, ${c.failed} failed, ${c.unchecked} not covered"><span class="ok" style="width:${pct(c.checked)}%"></span><span class="failed" style="width:${pct(c.failed)}%"></span><span class="missing" style="width:${pct(c.unchecked)}%"></span></div><div class="coverage-bar-legend"><span><i class="ok"></i>${c.checked} fetched</span><span><i class="failed"></i>${c.failed} failed</span><span><i class="missing"></i>${c.unchecked} not covered</span></div></div>`;
 }
 function health(data, now=Date.now(), {collapsible=false}={}){
  const h=root.BuiltWatchStatus.health(data,now),fmt=value=>value?new Date(value).toLocaleString(undefined,{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}):'Not recorded';
  const method=h.method==='rules'?'Rules · no AI inference':data.demo?'Historical replay':'Method not confirmed';
  const panel=`<section class="monitor-health panel" aria-label="Monitoring health"><div class="health-heading"><div><span class="eyebrow">MONITORING HEALTH</span><h2>${data.demo?'Saved example status':h.overdue?'Monitoring needs attention':'Your monitoring status'}</h2></div><span class="pill ${h.overdue?'amber':''}">${escape(method)}</span></div><dl class="health-grid"><div><dt>${data.demo?'Saved completed replay':'Last successful check'}</dt><dd>${h.lastSuccess||!h.lastComplete?escape(fmt(h.lastSuccess)):`${escape(fmt(h.lastComplete))}<small>Completed · ${escape(h.lastCompleteNote)}</small>`}</dd></div><div><dt>Next scheduled check</dt><dd>${data.demo?'Demo · no live schedule':!h.enabled?'Daily checks paused':h.next?escape(fmt(h.next)):'7 a.m. Toronto · exact time unavailable'}</dd></div><div><dt>Profiles needing a fresh check</dt><dd>${h.staleProfiles}</dd></div><div><dt>Latest source fetch failures</dt><dd>${h.failedSources}<small>${h.unobservedSources} sources not covered</small></dd></div></dl>${h.overdue?'<p class="notice">No fully successful check is recorded in the last 36 hours. Inspect check history and source failures.</p>':''}${coverageBar(root.BuiltWatchStatus.workspace(data,0).coverage,data.demo)}<ul class="health-facts"><li>${icon('source')}Fetching a source does not establish impact.</li><li>${icon('clock')}${h.baselines?`${h.baselines} first observations established baselines.`:'A first observation is a baseline, not an alert.'}</li><li>${icon('shield')}${data.demo?'These are historical examples.':'Schedule: America/Toronto. Start time may vary.'}</li></ul><div class="button-group"><button class="text-button" data-view="history">Inspect check history →</button><button class="text-button" data-view="sources">Inspect source coverage →</button></div></section>`;
  if(!collapsible)return panel;
  // On the overview the panel is plumbing: one status line, expanded only when something needs attention.
  const c=root.BuiltWatchStatus.workspace(data,0).coverage,trouble=h.overdue||h.failedSources>0||h.staleProfiles>0;
  const line=`${trouble?'Monitoring needs attention':'Monitoring healthy'} · ${c.checked}/${c.total} sources fetched${h.failedSources?` · ${h.failedSources} failed`:''}${h.lastSuccess||h.lastComplete?` · last check ${escape(fmt(h.lastSuccess||h.lastComplete))}`:''}`;
  return `<details class="health-fold ${trouble?'trouble':''}" ${trouble?'open':''}><summary>${icon(trouble?'review':'check')}<span>${line}</span><b aria-hidden="true">Details ⌄</b></summary>${panel}</details>`;
 }
 root.BuiltWatchVisuals={icon,escape,short,metrics,map,drawLinks,categories,runHealth,health,coverageBar};
})(typeof window!=='undefined'?window:globalThis);

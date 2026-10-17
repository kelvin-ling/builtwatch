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
 function map(state,findings){
  const systems=state.systems.slice(0,4),counts=new Map();
  for(const f of findings)counts.set(f.system_id,(counts.get(f.system_id)||0)+1);
  return `<section class="watch-network panel" aria-labelledby="network-title"><div class="network-heading"><div><span class="eyebrow">YOUR WATCH DESK</span><h2 id="network-title">See the connection.</h2><p>Outside sources → recorded dependencies → your next review.</p></div><span class="network-mode">${icon(state.demo?'clock':'shield')}${state.demo?'Historical examples':'No AI inference'}</span></div><div class="network-grid"><div class="network-input"><div class="orbit-icon">${icon('radar')}<span></span></div><strong>${state.sources.length} curated sources</strong><p>APIs, security, policies<br>and published guidance</p><button class="text-button" data-view="sources">Explore sources →</button></div><div class="network-connector" aria-hidden="true"><span></span>${icon('arrow')}</div><div class="network-apps">${systems.length?systems.map(s=>{const count=counts.get(s.id)||0,services=[...s.services,...s.technologies].slice(0,2);return `<button class="network-app" data-system="${escape(s.id)}"><span class="app-node-icon">${icon('apps')}</span><span><strong>${escape(s.name)}</strong><small>${escape(services.join(' · ')||'Dependencies not recorded')}</small></span><b class="node-count ${count?'attention':''}" aria-label="${count} open ${count===1?'review':'reviews'}">${count||'—'}</b></button>`;}).join('')+(state.systems.length>4?`<button class="text-button network-more" data-view="systems">View all ${state.systems.length} systems →</button>`:''):`<button class="network-app network-empty" data-action="bulk-import">${icon('import')}<span><strong>Bring your first system</strong><small>Import a profile from your project agent</small></span></button>`}</div><div class="network-connector" aria-hidden="true"><span></span>${icon('arrow')}</div><button class="network-result" data-view="findings"><span>${icon(findings.length?'review':'check')}</span><strong>${findings.length}</strong><b>${findings.length===1?'possible match':'possible matches'}</b><small>${state.demo?'Saved review examples':'You or your agent verify impact'}</small></button></div><div class="network-foot"><span><i></i>${state.demo?'Replay only. Custom demo profiles are not evaluated.':'Matches use recorded dependencies. Legal applicability is not assessed.'}</span><button class="text-button" data-view="guide">How it works ↗</button></div></section>`;
 }
 function categories(state,selected='all'){
  const groups=new Map();for(const s of state.sources){if(!groups.has(s.category))groups.set(s.category,[]);groups.get(s.category).push(s);}
  const health=new Map((root.BuiltWatchStatus.workspace(state,0).latest?.source_health||[]).map(x=>[x.source_id,x]));
  return `<section class="source-atlas" aria-label="Source coverage by category">${[...groups].map(([key,sources])=>{const ok=sources.filter(s=>health.get(s.id)?.fetch_status==='ok').length,failed=sources.filter(s=>health.has(s.id)&&health.get(s.id).fetch_status!=='ok').length;return `<button class="atlas-card ${selected===key?'selected':''}" data-source-filter="${escape(key)}" aria-pressed="${selected===key}"><span class="atlas-icon">${icon(key==='security'?'shield':'source')}</span><strong>${escape(root.BuiltWatchPerspectives.topics[key]||key)}</strong><span class="atlas-count">${sources.length}<small>${sources.length===1?'source':'sources'}</small></span><span class="atlas-track" aria-hidden="true"><i style="width:${Math.round(ok/sources.length*100)}%"></i></span><small>${state.demo?'Replay': 'Latest check'} · ${ok}/${sources.length} fetched${failed?` · ${failed} failed`:''}</small></button>`;}).join('')}</section>`;
 }
 function runHealth(run){
  const health=run.source_health||[],ok=health.filter(x=>x.fetch_status==='ok').length,failed=health.length-ok;
  return `<div class="run-health"><div class="run-segments" role="img" aria-label="${ok} sources fetched, ${failed} failed">${health.map(h=>`<span class="${h.fetch_status==='ok'?'ok':'failed'}" title="${escape(h.source_id)}: ${escape(h.fetch_status)}"></span>`).join('')}</div><span>${icon(failed?'review':'check')}${ok} fetched${failed?` · ${failed} failed`:''}</span></div>`;
 }
 function health(data, now=Date.now()){
  const h=root.BuiltWatchStatus.health(data,now),fmt=value=>value?new Date(value).toLocaleString(undefined,{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}):'Not recorded';
  const method=h.method==='rules'?'Rules · no AI inference':data.demo?'Historical replay':'Method not confirmed';
  return `<section class="monitor-health panel" aria-label="Monitoring health"><div class="health-heading"><div><span class="eyebrow">MONITORING HEALTH</span><h2>${data.demo?'Saved example status':h.overdue?'Monitoring needs attention':'Your monitoring status'}</h2></div><span class="pill ${h.overdue?'amber':''}">${escape(method)}</span></div><dl class="health-grid"><div><dt>${data.demo?'Saved completed replay':'Last successful check'}</dt><dd>${escape(fmt(h.lastSuccess))}</dd></div><div><dt>Next scheduled check</dt><dd>${data.demo?'Demo · no live schedule':!h.enabled?'Daily checks paused':h.next?escape(fmt(h.next)):'7 a.m. Toronto · exact time unavailable'}</dd></div><div><dt>Profiles needing a fresh check</dt><dd>${h.staleProfiles}</dd></div><div><dt>Latest source fetch failures</dt><dd>${h.failedSources}<small>${h.unobservedSources} sources not covered</small></dd></div></dl>${h.overdue?'<p class="notice">No fully successful check is recorded in the last 36 hours. Inspect check history and source failures.</p>':''}<p class="section-note">${h.baselines?`${h.baselines} first observations established baselines. `:''}Fetching a source does not establish whether a change affects your app. First observations establish a baseline; existing changes do not become retroactive alerts.${data.demo?' These are historical examples.':' Schedule: America/Toronto. Start time may vary.'}</p><div class="button-group"><button class="text-button" data-view="history">Inspect check history →</button><button class="text-button" data-view="sources">Inspect source coverage →</button></div></section>`;
 }
 root.BuiltWatchVisuals={icon,escape,short,metrics,map,categories,runHealth,health};
})(typeof window!=='undefined'?window:globalThis);

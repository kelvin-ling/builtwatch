import test from 'node:test';
import assert from 'node:assert/strict';
import '../web/status.js';
import '../web/perspectives.js';
import '../web/visuals.js';
const v=globalThis.BuiltWatchVisuals;
const state={demo:true,systems:[{id:'mail',name:'Mail <helper>',services:['Gmail API'],technologies:[]}],sources:[{id:'gmail',category:'communications'}],runs:[{id:'run',status:'complete',started_at:'2026-10-14T12:00:00Z',finished_at:'2026-10-14T12:01:00Z',systems_evaluated:['mail'],source_health:[{source_id:'gmail',fetch_status:'ok'}]}]};
test('visual metrics and app map use real counts and escape imported content',()=>{
 const findings=[{system_id:'mail'}];
 const metrics=v.metrics(state,findings),map=v.map(state,findings);
 assert.match(metrics,/1\/1/);
 assert.match(map,/Mail &lt;helper&gt;/);
 assert.doesNotMatch(map,/<helper>/);
 assert.match(map,/1 open review/);
 assert.match(map,/Historical examples/);
 assert.match(map,/Custom demo profiles are not evaluated/);
 assert.doesNotMatch(map,/incident prevented|compliant/i);
});
test('source visuals distinguish failed and unobserved sources from fetched evidence',()=>{
 const data={...state,demo:false,sources:[...state.sources,{id:'other',category:'security'}],runs:[{...state.runs[0],source_health:[{source_id:'gmail',fetch_status:'network_error'}]}]};
 const html=v.categories(data,'communications');
 assert.match(html,/0\/1 fetched · 1 failed/);
 assert.match(html,/aria-pressed="true"/);
 assert.match(html,/0\/1 fetched/);
 const receipt=v.runHealth(data.runs[0]);
 assert.match(receipt,/0 sources fetched, 1 failed/);
 assert.match(receipt,/class="failed"/);
});
test('app map shows how to reach systems beyond its four-row preview',()=>{
 const data={...state,systems:Array.from({length:7},(_,i)=>({...state.systems[0],id:'app-'+i}))};
 assert.match(v.map(data,[]),/View all 7 systems/);
});

test('reviewed cards and groups identify recorded outcomes instead of new review work',async()=>{
 const {readFileSync}=await import('node:fs');const vm=await import('node:vm');
 const app=readFileSync(new URL('../web/app.js',import.meta.url),'utf8');
 const ctx=vm.createContext({BuiltWatchVisuals:v,BuiltWatchPerspectives,esc:v.escape,
  state:{...state,findings:[]}});
 vm.runInContext(app.slice(app.indexOf('function findingRow('),app.indexOf('\nfunction monitoredSystemIds')),ctx);
 const finding={id:'one',system_id:'mail',relevance:'relevant',disposition:'acknowledged',
  title:'Sender update',facts:['Sender guidelines changed.'],system_facts:[],evidence:[{passage:'Exact source passage'}]};
 const html=ctx.groupedFindings([finding]);
 assert.match(html,/1 item reviewed/);assert.match(html,/Outcome recorded/);assert.match(html,/>Reviewed</);
 assert.doesNotMatch(html,/1 item to review/);
 // The group heading already names the app, so the card leads with the change.
 assert.match(html,/<h3>Sender update<span/);
});

test('monitoring panel surfaces failures and baselines without claiming applicability',()=>{
 const data={...state,demo:false,account:{automatic_checks:true},monitoring:{method:'rules'},
  runs:[{...state.runs[0],baseline_sources:['gmail'],source_health:[{source_id:'gmail',fetch_status:'network_error'}]}]};
 const html=v.health(data,Date.parse('2026-10-17T00:00:00Z'));
 assert.match(html,/Monitoring needs attention/);assert.match(html,/Latest source fetch failures/);
 assert.match(html,/1 first observations established baselines/);assert.match(html,/Fetching a source does not establish/);
 assert.doesNotMatch(html,/Your app is safe|fully assessed/);
});

test('watch desk map links a source category to the app it affects, and says so in text',()=>{
 const data={...state,sources:[{id:'gmail',category:'communications'},{id:'nvd',category:'security'}],systems:[...state.systems,{id:'site',name:'Site',services:[],technologies:['Hugo']}]};
 const html=v.map(data,[{system_id:'mail',source_id:'gmail'}]);
 assert.match(html,/data-links="cat:communications&gt;app:mail app:mail&gt;result"/);
 assert.match(html,/via Platform policies/);
 assert.match(html,/net-cat hot" data-node="cat:communications"/);
 assert.doesNotMatch(html,/cat:security&gt;/);
 assert.match(html,/\+1 more category/);
});

test('coverage bar reports every bucket in text and never draws an empty run as coverage',()=>{
 const bar=v.coverageBar({checked:7,failed:2,unchecked:1});
 assert.match(bar,/7 sources fetched, 2 failed, 1 not covered/);
 assert.match(bar,/width:70\.0%/);
 assert.match(v.coverageBar({checked:0,failed:0,unchecked:0}),/no source is covered/);
});

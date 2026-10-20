import test from 'node:test';
import assert from 'node:assert/strict';
import '../web/status.js';
import '../web/perspectives.js';
import '../web/visuals.js';
import '../web/briefs.js';
const B=globalThis.BuiltWatchBriefs,P=globalThis.BuiltWatchPerspectives;
const app={id:'m',name:'Mailer',architecture:{components:[{id:'out',name:'Outbound <email>',kind:'external'}]}};
const brief={verdict:'likely_affects',component_id:'out',what_changes:'Senders must use TLS.',why_it_matters:'The bot sends via <SendGrid>.',check_first:'Check TLS.',support_quote:'Use a TLS connection',model_id:'us.amazon.nova-lite-v1:0',created_at:'2026-10-20T05:00:00Z'};

test('a brief is labelled as AI, names its component, shows its quote and escapes model text',()=>{
 const f={id:'a',ai_brief:brief};
 const line=B.line(f,app);
 assert.match(line,/ai-tag/);assert.match(line,/Likely affects this app · Outbound &lt;email&gt;/);assert.doesNotMatch(line,/<SendGrid>/);
 const section=B.section(f,app);
 assert.match(section,/AI IMPACT BRIEF/);assert.match(section,/Use a TLS connection/);
 assert.match(section,/Amazon Nova Lite/);assert.match(section,/Advisory/);
 assert.equal(B.line({id:'b'},app),'');assert.equal(B.section({id:'b'},app),'');
});

test('briefs reorder reviews without hiding any',()=>{
 const sources=[{id:'s',category:'security'}];
 const items=[{id:'u',source_id:'s',ai_brief:{verdict:'unlikely'}},{id:'n',source_id:'s'},{id:'l',source_id:'s',ai_brief:{verdict:'likely_affects'}}];
 assert.deepEqual(P.ordered(items,sources,'technical').map(x=>x.id),['l','n','u']);
});

test('handoff text marks the brief as advisory',()=>{
 assert.match(B.text({ai_brief:brief},app),/AI impact brief \(Amazon Nova Lite, advisory\): Likely affects this app, most affected: Outbound <email>/);
});

test('the dialog says when the brief points at a different part than the rules match',()=>{
 const two={...app,architecture:{components:[...app.architecture.components,{id:'api',name:'API',kind:'service'}]}};
 assert.match(B.section({ai_brief:brief},two,['api']),/rules match is on API; the brief reads Outbound &lt;email&gt;/);
 assert.doesNotMatch(B.section({ai_brief:brief},two,['out']),/rules match is on/);
});

test('overview health folds to one line and opens itself when something is wrong',()=>{
 const ok={demo:false,sources:[{id:'a'}],runs:[{status:'complete',started_at:'2026-10-19T11:00:00Z',finished_at:'2026-10-19T11:01:00Z',sources_at_start:['a'],source_health:[{source_id:'a',fetch_status:'ok'}]}],systems:[],account:{automatic_checks:true}};
 const html=globalThis.BuiltWatchVisuals.health(ok,Date.parse('2026-10-19T12:00:00Z'),{collapsible:true});
 assert.match(html,/<details class="health-fold "/);assert.match(html,/Monitoring healthy · 1\/1 sources fetched/);
 const bad={...ok,runs:[{...ok.runs[0],source_health:[{source_id:'a',fetch_status:'network_error'}]}]};
 const trouble=globalThis.BuiltWatchVisuals.health(bad,Date.parse('2026-10-19T12:00:00Z'),{collapsible:true});
 assert.match(trouble,/health-fold trouble" open/);assert.match(trouble,/Monitoring needs attention/);
});

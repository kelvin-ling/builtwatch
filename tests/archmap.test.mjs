import test from 'node:test';
import assert from 'node:assert/strict';
import '../web/status.js';
import '../web/perspectives.js';
import '../web/visuals.js';
import '../web/archmap.js';
const A=globalThis.BuiltWatchArchMap;
const app={id:'mailer',name:'Mailer <x>',purpose:'Drafts replies',services:['Gmail API','Amazon Bedrock'],technologies:['AWS Lambda'],
 data_categories:['email address'],consequential_actions:[{description:'Sends approved replies'}],constraints:['Owner approves'],
 architecture:{analyzed_by:'Repo agent',components:[
  {id:'inbox',name:'Inbox',kind:'external',uses:['Gmail API'],data:['email address']},
  {id:'fn',name:'Triage function',kind:'service',uses:['AWS Lambda'],actions:['Sends approved replies']},
  {id:'llm',name:'Drafting model',kind:'model',uses:['Amazon Bedrock']},
  {id:'ui',name:'Approval page',kind:'entry'}],
  flows:[{source:'fn',target:'inbox'},{source:'fn',target:'llm'},{source:'ui',target:'fn'}]}};
const sources=[{id:'gmail',category:'communications'},{id:'eu',category:'regulation'}];
const gmail={id:'g',system_id:'mailer',source_id:'gmail',relevance:'relevant',facts:['Sender rules changed'],system_facts:[{key:'services[0]',value:'gmail api'}]};
const rule={id:'r',system_id:'mailer',source_id:'eu',relevance:'relevant',facts:['Approval duty'],system_facts:[{key:'constraints[0]',value:'Owner approves'}]};

test('a matched dependency lands on the component that uses it, and its neighbours are flagged',()=>{
 const p=A.place(app,[gmail,rule],sources);
 assert.deepEqual(p.pins[0].components,['inbox']);
 assert.deepEqual([...p.direct],['inbox']);
 assert.deepEqual([...p.near],['fn']);
 // A whole-app fact is reported as whole-app, never forced onto a component.
 assert.deepEqual(p.pins[1].components,[]);
});

test('the rendered map pins reviews, escapes names, and marks hot edges',()=>{
 const html=A.render(app,[gmail,rule],{sources});
 assert.match(html,/Mailer &lt;x&gt;/);assert.doesNotMatch(html,/<x>/);
 assert.match(html,/data-node="inbox"[^>]*>.*data-finding="g"/s);
 assert.match(html,/fn&gt;inbox&gt;hot/);
 assert.match(html,/Whole app, not one component/);
 assert.match(html,/Mapped by Repo agent/);
 assert.match(html,/data-arch-map="mailer"/);
 assert.match(html,/2 changes land here/);
});

test('focus highlights one review and dims the rest',()=>{
 const html=A.render(app,[gmail,rule],{sources,focus:'g'});
 assert.match(html,/Where this change lands/);
 assert.match(html,/1 component hit/);
 assert.match(html,/arch-node kind-model[^"]*dim/);
 assert.doesNotMatch(html,/data-arch-map/);
});

test('without a supplied map the profile is drawn and labelled as derived',()=>{
 const {architecture,...plain}=app;
 const d=A.architecture(plain);
 assert.equal(d.derived,true);
 assert.deepEqual(d.components.map(c=>c.kind),['service','external','model']);
 assert.deepEqual(A.place(plain,[gmail]).pins[0].components,['svc-0']);
 assert.match(A.render(plain,[],{}),/Drawn from the profile only/);
});

test('validation mirrors the server and reports facts a save would add',()=>{
 const bad=A.validate(app,{components:[{id:'A B',name:'',kind:'robot'}],flows:[{source:'x',target:'y'}]});
 assert.equal(bad.ok,false);assert.ok(bad.errors.length>=3);
 const ok=A.validate(app,{architecture:{components:[{id:'api',name:'API',kind:'service',uses:['aws lambda','FastAPI']},{id:'pay',name:'Stripe',kind:'external',uses:['Stripe API']}],flows:[{source:'api',target:'pay'}]}});
 assert.equal(ok.ok,true);
 assert.deepEqual(ok.additions.technologies,['FastAPI']);
 assert.deepEqual(ok.additions.services,['Stripe API']);
 const next=A.apply(app,ok);
 assert.ok(next.services.includes('Stripe API'));assert.equal(next.provenance.architecture,'agent_extracted');
});

test('saves send a map only when it is new; the server and demo keep the saved one',()=>{
 // An edit without a new map omits it, so the server keeps the map and its save time.
 assert.equal('architecture' in A.reconcile({...app,architecture:null}),false);
 assert.equal('architecture' in A.reconcile({id:'x'}),false);
 assert.equal(A.reconcile({...app,remove_architecture:true}).architecture,null);
 // A new map is trimmed to the profile it travels with.
 const trimmed=A.reconcile({...app,services:['Amazon Bedrock']});
 assert.deepEqual(trimmed.architecture.components.find(c=>c.id==='inbox').uses,[]);
 // keep() mirrors the server for the demo: omitted keeps, explicit null removes.
 const {architecture,...edit}=app;
 assert.equal(A.keep({...edit,services:['Amazon Bedrock']},app).architecture.components.find(c=>c.id==='llm').uses[0],'Amazon Bedrock');
 assert.equal(A.keep({...edit,architecture:null},app).architecture,null);
});

test('the agent request names the profile facts and forbids sending code or secrets',()=>{
 const text=A.prompt(app);
 assert.match(text,/"Gmail API","Amazon Bedrock"/);
 assert.match(text,/Do not send code anywhere/);
 assert.match(text,/secrets/);
});

test('card maps show only hit parts and neighbours, or a one-line summary when quiet',()=>{
 const html=A.render(app,[gmail],{sources,compact:true});
 assert.match(html,/data-node="inbox"/);assert.match(html,/data-node="fn"/);
 assert.doesNotMatch(html,/data-node="llm"/);assert.doesNotMatch(html,/data-node="ui"/);
 assert.match(html,/Full map · 2 more parts/);
 const quiet=A.render(app,[],{sources,compact:true});
 assert.match(quiet,/No open review lands on this app/);
 assert.match(quiet,/1 entry point · 1 service · 1 data store or model · 1 outside service/);
});

test('landing names the hit and connected parts for supplied maps only',()=>{
 const l=A.landing(app,gmail);
 assert.deepEqual(l.parts.map(c=>c.name),['Inbox']);
 assert.deepEqual(l.near.map(c=>c.name),['Triage function']);
 assert.equal(A.landing(app,rule).whole,true);
 const {architecture,...plain}=app;
 assert.equal(A.landing(plain,gmail),null);
});

test('the agent handoff and digest say where the change lands',async()=>{
 await import('../web/handoff.js');await import('../web/notifications.js');
 const f={...gmail,title:'Sender rules',inferences:[],unknowns:[],review_suggestions:[],evidence:[],adoption_status:'unknown'};
 const prompt=globalThis.BuiltWatchHandoff.findingPrompt(f,app,sources);
 assert.match(prompt,/Where it lands in the backend map:\n- Inbox \(external\)/);
 assert.match(prompt,/Connected components to check next:\n- Triage function/);
 const data={demo:false,systems:[app],sources:[{id:'gmail',name:'Gmail',category:'communications'}],runs:[],findings:[f]};
 assert.match(globalThis.BuiltWatchNotifications.digest(data,[f]),/Lands on: Inbox; check next: Triage function/);
});

test('pasting an older analysis is not stale; a later profile change is',()=>{
 const s={...app,architecture:undefined,updated_at:'2026-10-18T17:00:00Z'};
 const r=A.validate(s,{analyzed_at:'2026-10-15',components:[{id:'x',name:'X',kind:'external',uses:['Gmail API']}]});
 const saved={...A.apply(s,r),updated_at:new Date().toISOString()};
 assert.equal(A.stale(saved),false);
 const later={...saved,updated_at:new Date(Date.now()+3*86400000).toISOString()};
 assert.equal(A.stale(later),true);
});

test('a map dated well before the latest profile change is flagged, same-day saves are not',()=>{
 const dated={...app,architecture:{...app.architecture,analyzed_at:'2026-10-01'}};
 assert.equal(A.stale({...dated,updated_at:'2026-10-01T18:00:00Z'}),false);
 assert.equal(A.stale({...dated,updated_at:'2026-10-05T09:00:00Z'}),true);
 assert.match(A.render({...dated,updated_at:'2026-10-05T09:00:00Z'},[],{sources}),/profile changed after this map was made/);
 assert.equal(A.stale(app),false);
});

test('the overview placemat names the component a change reaches',()=>{
 const state={demo:false,systems:[app],sources,runs:[],findings:[gmail]};
 assert.match(globalThis.BuiltWatchVisuals.map(state,[gmail]),/via Platform policies → Inbox/);
});

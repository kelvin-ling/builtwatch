import test from 'node:test';
import assert from 'node:assert/strict';
import '../web/perspectives.js';
const p=globalThis.BuiltWatchPerspectives;
test('views reorder the same findings without changing evidence or dropping technical items',()=>{
 const sources=[{id:'news',category:'business_news'},{id:'api',category:'api_change'},{id:'sec',category:'security'}];
 const findings=[{id:'one',source_id:'api',evidence:['exact quote']},{id:'two',source_id:'news'},{id:'three',source_id:'sec'}];
 const before=structuredClone(findings);
 assert.equal(p.ordered(findings,sources,'business')[0].id,'two');
 assert.equal(p.ordered(findings,sources,'technical')[0].id,'one');
 for(const lens of Object.keys(p.views)){
  const result=p.ordered(findings,sources,lens);
  assert.deepEqual(result.map(x=>x.id).sort(),['one','three','two']);
  assert.deepEqual(result.find(x=>x.id==='one').evidence,['exact quote']);
 }
 assert.deepEqual(findings,before);
 assert.equal(p.normalize('admin'),'business');
});
test('business context uses recorded facts and never invents a condition',()=>{
 assert.deepEqual(p.context({purpose:'Send follow-up emails'}),{actions:[],assumptions:[],limits:[],regions:[]});
 const result=p.context({consequential_actions:[{description:'Draft customer quotes'}],assumptions:['Price list is current'],constraints:['A person approves quotes'],jurisdictions:['Canada']});
 assert.deepEqual(result.assumptions,['Price list is current']);
 assert.deepEqual(result.limits,['A person approves quotes']);
});

test('impact brief connects the correct app fact and flags a changed assumption',()=>{
 const app={id:'quotes',name:'Quote helper',purpose:'Draft customer quotes',assumptions:['The price list is current'],services:['Sheets']};
 const finding={system_id:'quotes',relevance:'relevant',title:'Price change',facts:['Supplier prices changed'],system_facts:[{key:'services[0]',value:'Sheets'},{key:'assumptions[0]',value:'The price list is current'}],inferences:['Quotes may use old prices'],review_suggestions:['Check the price list'],app_impact:{fact_key:'assumptions[0]',consequence:'Quote helper may draft outdated prices.',review_question:'Has the current price list been approved?'}};
 const b=p.brief(finding,app);assert.equal(b.app,'Quote helper');assert.equal(b.connection,'The price list is current');assert.equal(b.consequence,'Quote helper may draft outdated prices.');assert.equal(b.stale,false);
 const changed=p.brief(finding,{...app,assumptions:['Prices are entered by a person']});assert.equal(changed.stale,true);assert.match(changed.consequence,/profile changed/);
 const legacy=p.brief({...finding,app_impact:null},app);assert.equal(legacy.connection,'The price list is current');assert.equal(legacy.consequence,'Quotes may use old prices');
 const unrelated={id:'other',name:'Other app',purpose:'Read news'};assert.equal(p.brief(finding,unrelated).anchored,false);
});
test('grouping keeps findings attached to their own apps',()=>{
 const groups=p.grouped([{id:'one',system_id:'a'},{id:'two',system_id:'b'},{id:'three',system_id:'a'}],[{id:'a',name:'App A'},{id:'b',name:'App B'}]);
 assert.deepEqual(groups.map(g=>[g.system.name,g.findings.map(x=>x.id)]),[['App A',['one','three']],['App B',['two']]]);
});

test('automation map uses recorded profile facts and anchors an outside event to the matching step',()=>{
 const app={id:'mailer',name:'Mailer',purpose:'Drafts replies',services:['Gmail'],data_categories:['email'],consequential_actions:[{description:'Sends an approved reply'}],constraints:['A person approves every draft'],assumptions:['Recipients expect a reply'],jurisdictions:['Canada']};
 const finding={system_id:'mailer',title:'Email rule changed',facts:['A sender rule changed'],system_facts:[{key:'constraints[0]',value:'A person approves every draft'}],app_impact:{fact_key:'constraints[0]',consequence:'Approval may need another check.',review_question:'Is approval still enough?'},relevance:'relevant'};
 const flow=p.automation(app,finding);
 assert.equal(flow.input.value,'Gmail');
 assert.equal(flow.work.value,'Sends an approved reply');
 assert.equal(flow.checkpoint.value,'A person approves every draft');
 assert.equal(flow.condition.value,'Recipients expect a reply');
 assert.equal(flow.anchor,'checkpoint');
 assert.equal(flow.event.change,'A sender rule changed');
 assert.match(flow.event.review,/approval still enough/i);
});

test('automation map keeps missing workflow details explicit',()=>{
 const flow=p.automation({purpose:'Shows public information',services:[],data_categories:[],consequential_actions:[],constraints:[],assumptions:[],jurisdictions:[]});
 assert.equal(flow.input.value,'Not recorded yet');
 assert.equal(flow.work.value,'Shows public information');
 assert.match(flow.checkpoint.value,/none recorded/i);
 assert.match(flow.condition.value,/none recorded/i);
 assert.equal(flow.event,null);
});

test('diagnosis assigns a plain-language owner and action to every result type',()=>{
 const app={id:'mail',name:'Mailer',purpose:'Sends mail',services:['Gmail']};
 const blocked={system_id:'mail',relevance:'insufficient_information',title:'Possible rule',unknowns:['Downgraded automatically: the relevance claim was not grounded (relevant finding has no evidence passage).'],system_facts:[]};
 const missing={system_id:'mail',relevance:'insufficient_information',title:'Possible rule',unknowns:['Whether recipients opted in'],system_facts:[]};
 const clear={system_id:'mail',relevance:'not_relevant',title:'Other rule',unknowns:[],system_facts:[],inferences:['This rule does not cover the app.']};
 assert.equal(p.diagnosis(blocked,app).owner,'BuiltWatch');
 assert.match(p.diagnosis(blocked,app).action,/do not change the app/i);
 assert.equal(p.diagnosis(missing,app).owner,'You');
 assert.match(p.diagnosis(missing,app).problem,/confirm recipients opted in/i);
 assert.match(p.diagnosis(missing,app).action,/update the app profile/i);
 assert.equal(p.diagnosis(clear,app).owner,'No action');
 assert.match(p.diagnosis(clear,app).action,/nothing needs fixing/i);
});

test('presentation removes model-like assessment wording and app ids',()=>{
 const app={id:'support-widget',name:'Support widget',purpose:'Answers questions'};
 const finding={system_id:'support-widget',relevance:'insufficient_information',title:"Assessing relevance of Anthropic Usage Policy to 'support-widget'",unknowns:["Whether the 'support-widget' system accepts public input."],system_facts:[]};
 const brief=p.brief(finding,app),diagnosis=p.diagnosis(finding,app);
 assert.equal(brief.change,'Anthropic Usage Policy');
 assert.equal(diagnosis.problem,'Confirm this app accepts public input.');
 assert.equal(diagnosis.status,'Your input is needed');
});

test('unverified results without source evidence never ask the user to act',()=>{
 const app={id:'mailer',name:'Mailer',purpose:'Sends email'};
 const finding={system_id:'mailer',relevance:'insufficient_information',title:'Gmail Email Sender Guidelines Relevance Assessment',unknowns:['Whether the system sends email'],system_facts:[],evidence:[]};
 assert.equal(p.brief(finding,app).change,'Gmail Email Sender Guidelines');
 assert.equal(p.diagnosis(finding,app).owner,'BuiltWatch');
 assert.equal(p.requiresAttention(finding,app),false);
});

test('only results that need user action enter the attention list',()=>{
 const app={id:'mail',name:'Mailer',purpose:'Sends mail'};
 assert.equal(p.requiresAttention({relevance:'relevant',disposition:'open',system_facts:[]},app),true);
 assert.equal(p.requiresAttention({relevance:'insufficient_information',disposition:'open',unknowns:['Whether recipients opted in'],system_facts:[]},app),true);
 assert.equal(p.requiresAttention({relevance:'insufficient_information',disposition:'open',unknowns:['Downgraded automatically: not grounded'],system_facts:[]},app),false);
 assert.equal(p.requiresAttention({relevance:'not_relevant',disposition:'open',system_facts:[]},app),false);
 assert.equal(p.requiresAttention({relevance:'relevant',disposition:'acknowledged',system_facts:[]},app),false);
});

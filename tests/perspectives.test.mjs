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

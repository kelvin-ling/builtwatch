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

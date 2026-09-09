import test from 'node:test';
import assert from 'node:assert/strict';
import '../web/handoff.js';
test('copy handoff includes source, dates, evidence and a bounded review request',()=>{
 const f={title:'A policy changed',system_id:'mail',relevance:'relevant',adoption_status:'proposed',system_facts:[{key:'services[0]',value:'Gmail'}],inferences:['Might affect mail'],unknowns:['Volume unknown'],review_suggestions:['Check sender volume'],evidence:[{source_id:'s',published_at:'2026-09-01',effective_at:null,passage:'Exact quoted passage.'}]};
 const text=BuiltWatchHandoff.findingPrompt(f,{name:'Mail helper',purpose:'Draft mail'},[{id:'s',name:'Official policy',url:'https://example.com/policy'}]);
 for(const value of ['Mail helper','proposed','https://example.com/policy','2026-09-01','Exact quoted passage.','untrusted evidence','Do not assume','updated short BuiltWatch system summary'])assert.ok(text.includes(value));
 assert.ok(BuiltWatchHandoff.builderPrompt.includes('Do not include secrets'));
});

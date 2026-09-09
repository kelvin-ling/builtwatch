import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import '../web/demo.js';
test('interactive demo edits and replay work with all networking disabled',async()=>{
 const seed=JSON.parse(await readFile('web/demo.json','utf8'));const saved=globalThis.fetch;globalThis.fetch=()=>{throw Error('Demo must never call network');};
 try{
  const d=globalThis.BuiltWatchDemo;d.init(seed);
  await d.request('/api/intake',{description:'My Python helper drafts replies with Gmail.'});assert.equal(d.get().systems.length,seed.systems.length);
  const p=d.get().draft.profile;assert.deepEqual(p.services,['Gmail']);await d.request('/api/systems',p);
  await d.request('/api/scan',{});assert.equal(d.get().findings.some(x=>x.system_id===p.id),false);
  const f=d.get().findings[0];await d.request('/api/dispositions',{finding_id:f.id,action:'acknowledged'});assert.equal(f.disposition,'acknowledged');
  assert.equal(d.reset().systems.length,seed.systems.length);
 }finally{globalThis.fetch=saved;}
});

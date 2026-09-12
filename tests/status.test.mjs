import test from 'node:test';
import assert from 'node:assert/strict';
import '../web/status.js';

const S=BuiltWatchStatus;
const profile={id:'app',updated_at:'2026-09-10T10:00:00Z'};
const sources=[{id:'one'},{id:'two'}];
const run={id:'r',status:'complete',started_at:'2026-09-10T11:00:00Z',finished_at:'2026-09-10T12:00:00Z',
 systems_evaluated:['app'],source_health:sources.map(s=>({source_id:s.id,fetch_status:'ok'}))};
test('an empty inbox cannot make a never-checked app checked',()=>{
 assert.equal(S.system(profile,[],sources).key,'unchecked');
 assert.match(S.workspace({systems:[profile],runs:[],sources},0).title,/first check/);
});
test('editing during a scan invalidates that scan even before it finishes',()=>{
 assert.equal(S.system({...profile,updated_at:'2026-09-10T11:30:00Z'},[run],sources).key,'stale');
});
test('a subsequent completed check covers the edited profile',()=>{
 assert.equal(S.system({...profile,updated_at:'2026-09-10T11:30:00Z'},[{...run,started_at:'2026-09-10T12:30:00Z'}],sources).key,'checked');
});
test('fetch failure, missing source and grounding failure each prevent complete coverage',()=>{
 for(const partial of [
  {...run,source_health:[run.source_health[0],{source_id:'two',fetch_status:'error'}]},
  {...run,source_health:run.source_health.slice(0,1)},
  {...run,validation_failures:1}
 ])assert.equal(S.system(profile,[partial],sources).key,'partial');
});
test('adding a source changes coverage; disabled sources do not inflate it',()=>{
 assert.equal(S.coverage(run,[...sources,{id:'new'}]).unchecked,1);
 assert.equal(S.coverage(run,[...sources,{id:'disabled',enabled:false}]).complete,true);
});
test('coverage explains sources added after the run instead of calling them failures',()=>{
 const historical={...run,sources_at_start:['one','two']};
 const result=S.coverage(historical,[...sources,{id:'new'}]);
 assert.equal(result.checked,2);
 assert.equal(result.failed,0);
 assert.equal(result.added,1);
 assert.equal(result.unattempted,0);
 assert.equal(result.complete,false);
});
test('a source added after the run is explained as a refresh, not a failed check',()=>{
 const historical={...run,sources_at_start:['one','two']};
 const result=S.system(profile,[historical],[...sources,{id:'new'}]);
 assert.equal(result.key,'partial');
 assert.match(result.label,/new source.*check again/);
});
test('a later failed attempt is not hidden by a prior successful check',()=>{
 const failed={...run,status:'aborted',started_at:'2026-09-10T14:00:00Z'};
 const status=S.system(profile,[run,failed],sources);
 assert.equal(status.key,'incomplete');
 assert.equal(status.completed.id,'r');
});
test('runs are ordered by time and other apps do not confer coverage',()=>{
 assert.equal(S.system(profile,[{...run,systems_evaluated:['different']}],sources).key,'unchecked');
 assert.equal(S.system(profile,[run,{...run,status:'running',started_at:'2026-09-10T15:00:00Z'}],sources).key,'checking');
});
test('unknown dates and empty health records fail conservatively',()=>{
 assert.equal(S.system({id:'app'},[run],sources).key,'unknown');
 assert.equal(S.system({...profile,updated_at:'not a date'},[run],sources).key,'unknown');
 assert.equal(S.system(profile,[{...run,source_health:[]}],[]).key,'partial');
});
test('a resolved demo review changes the headline without claiming untested apps are checked',()=>{
 const data={demo:true,systems:[profile,{id:'new'}],runs:[run],sources};
 assert.match(S.workspace(data,3).title,/3 changes/);
 assert.match(S.workspace(data,2).title,/2 changes/);
 assert.match(S.workspace(data,0).title,/saved example/);
 assert.equal(S.workspace(data,0).counts.unchecked,1);
});
test('poll policy never calls the live service for public demo or Docs',()=>{
 for(const params of [{signedIn:false},{demo:true},{view:'guide'}])
 assert.equal(S.pollDelay({signedIn:true,demo:false,view:'overview',...params}),null);
 assert.equal(S.pollDelay({signedIn:true,demo:false,view:'systems',jobStatus:'running'}),12000);
 assert.equal(S.pollDelay({signedIn:true,demo:false,view:'systems'}),600000);
});

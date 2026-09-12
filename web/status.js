'use strict';
// A quiet inbox is not proof of coverage. Keep these states independent of findings.
globalThis.BuiltWatchStatus = (() => {
  const time = value => { const n = Date.parse(value); return Number.isFinite(n) ? n : null; };
  const ordered = runs => [...(runs || [])].sort((a,b) => (time(b.started_at) || 0) - (time(a.started_at) || 0));
  function coverage(run, sources = []) {
    const health = new Map((run?.source_health || []).map(h => [h.source_id,h]));
    const expected = [...new Set(sources.filter(s => s.enabled !== false).map(s => s.id))];
    const ids = expected.length ? expected : [...health.keys()];
    const checked = ids.filter(id => health.get(id)?.fetch_status === 'ok').length;
    const failed = ids.filter(id => health.has(id) && health.get(id).fetch_status !== 'ok').length;
    const unchecked = ids.length - checked - failed;
    return {checked,failed,unchecked,total:ids.length,
      complete:run?.status === 'complete' && ids.length > 0 && checked === ids.length && !run.validation_failures};
  }
  function system(profile, runs, sources) {
    const attempts = ordered(runs).filter(r => r.systems_evaluated?.includes(profile.id));
    const latest = attempts[0];
    const completed = attempts.find(r => r.status === 'complete');
    const result = {run:latest,completed,coverage:coverage(latest,sources)};
    if (!latest) return {...result,key:'unchecked',label:'Waiting for first check'};
    const updated = time(profile.updated_at || profile.created_at), started = time(latest.started_at);
    // Compare with the start, never the finish: a running check may hold an older profile.
    if (updated === null || started === null) return {...result,key:'unknown',label:'Profile freshness unconfirmed'};
    if (updated > started) return {...result,key:'stale',label:'Profile changed · check again'};
    if (latest.status === 'running') return {...result,key:'checking',label:'Check in progress'};
    if (latest.status !== 'complete') return {...result,key:'incomplete',label:'Last check did not finish'};
    if (!result.coverage.complete) return {...result,key:'partial',label:'Limited check coverage'};
    return {...result,key:'checked',label:'Checked against listed sources'};
  }
  function workspace(data, attentionCount = 0) {
    const systems = (data.systems || []).map(p => system(p,data.runs,data.sources));
    const counts = Object.fromEntries(['checked','unchecked','stale','unknown','checking','incomplete','partial'].map(k => [k,systems.filter(s => s.key === k).length]));
    const latest = ordered(data.runs)[0];
    const checking = !data.demo && ['queued','running'].includes(data.job?.status);
    const title = !systems.length ? 'Import the systems you already run.'
      : checking ? 'Your check is in progress.'
      : attentionCount ? `${attentionCount} ${attentionCount === 1 ? 'change needs' : 'changes need'} review.`
      : data.demo ? 'No open reviews in this saved example.'
      : counts.unchecked === systems.length ? 'Your systems are saved. Run their first check.'
      : counts.stale || counts.unknown ? 'Your saved profiles need a fresh check.'
      : counts.partial || counts.incomplete || counts.unchecked || counts.checking ? 'No open reviews. Coverage still needs attention.'
      : 'No open reviews from the checked sources.';
    return {systems,counts,latest,checking,title,coverage:coverage(latest,data.sources)};
  }
  function pollDelay({signedIn,demo,view,jobStatus,editing=false}) {
    if (!signedIn || demo || !['overview','impact','history','systems','findings','sources'].includes(view)) return null;
    return editing || ['queued','running'].includes(jobStatus) ? 12000 : 600000;
  }
  return {coverage,system,workspace,pollDelay};
})();

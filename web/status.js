'use strict';
// A quiet inbox is not proof of coverage. Keep these states independent of findings.
globalThis.BuiltWatchStatus = (() => {
  const time = value => { const n = Date.parse(value); return Number.isFinite(n) ? n : null; };
  const ordered = runs => [...(runs || [])].sort((a,b) => (time(b.started_at) || 0) - (time(a.started_at) || 0));
  function coverage(run, sources = []) {
    const health = new Map((run?.source_health || []).map(h => [h.source_id,h]));
    const listed = [...new Set(sources.filter(s => s.enabled !== false).map(s => s.id))];
    // Prefer the registry snapshot captured when the run began. Without it, a
    // later source addition looks like a failed check even though it did not exist
    // when that run was made.
    const ids = [...new Set(run?.sources_at_start?.length ? run.sources_at_start : [...health.keys()])];
    const checked = ids.filter(id => health.get(id)?.fetch_status === 'ok').length;
    const failed = ids.filter(id => health.has(id) && health.get(id).fetch_status !== 'ok').length;
    const unattempted = ids.filter(id => !health.has(id)).length;
    const added = listed.filter(id => !ids.includes(id));
    const unchecked = unattempted + added.length;
    return {checked,failed,unchecked,unattempted,added:added.length,total:ids.length,listed:listed.length,
      complete:run?.status === 'complete' && ids.length > 0 && checked === ids.length && added.length === 0 && !run.validation_failures};
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
    if (!result.coverage.complete) {
      // A newly registered source is not a failed check. Make that distinction
      // visible on each affected profile so users know exactly why a refresh is
      // needed instead of reading this as an unreliable result.
      const label = result.coverage.added
        ? `${result.coverage.added} new source${result.coverage.added === 1 ? '' : 's'} · check again`
        : 'Limited check coverage';
      return {...result,key:'partial',label};
    }
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

/* AI impact briefs: rendering only. A brief is advisory model text that the backend kept
   because its quote is in the evidence and its component is in the app's map. It is
   always labelled as AI, shows its quote, and never replaces the evidence or the review. */
(function(root){
 const VERDICT={likely_affects:['Likely affects this app','likely'],unclear:['Unclear for this app','unclear'],unlikely:['Probably not this app','unlikely']};
 const esc=x=>root.BuiltWatchVisuals.escape(x);
 const modelName=id=>/nova-lite/i.test(id||'')?'Amazon Nova Lite':/nova-micro/i.test(id||'')?'Amazon Nova Micro':/nova-pro/i.test(id||'')?'Amazon Nova Pro':(id||'an AI model');
 function component(system,brief){return (system?.architecture?.components||[]).find(c=>c.id===brief?.component_id)||null;}
 function verdict(brief){return VERDICT[brief?.verdict]||VERDICT.unclear;}

 // One line for review cards.
 function line(f,system){
  const b=f?.ai_brief;if(!b)return '';const [label,cls]=verdict(b),c=component(system,b);
  return `<div class="ai-brief-line ${cls}"><span class="ai-tag" title="${esc('Written by '+modelName(b.model_id)+'; advisory, verify before acting')}">AI</span><span><strong>${esc(label)}${c?` · ${esc(c.name)}`:''}</strong> ${esc(root.BuiltWatchVisuals.short(b.why_it_matters,150))}</span></div>`;
 }

 // The full brief for the review dialog.
 // `matched` = component ids the rules placement hit; say so when the brief points elsewhere.
 function section(f,system,matched=[]){
  const b=f?.ai_brief;if(!b)return '';const [label,cls]=verdict(b),c=component(system,b);
  const elsewhere=c&&matched.length&&!matched.includes(c.id)?`<p class="ai-brief-note">The rules match is on ${esc(matched.map(id=>component(system,{component_id:id})?.name||id).join(', '))}; the brief reads ${esc(c.name)} as the part most affected.</p>`:'';
  const when=b.created_at?new Date(b.created_at).toLocaleDateString(undefined,{day:'numeric',month:'short',year:'numeric'}):'';
  return `<section class="ai-brief ${cls}" aria-label="AI impact brief"><div class="ai-brief-head"><span class="ai-tag">AI</span><div><small>AI IMPACT BRIEF</small><strong>${esc(label)}${c?` · most affected: ${esc(c.name)}`:''}</strong></div></div>${elsewhere}<dl><div><dt>What changes</dt><dd>${esc(b.what_changes)}</dd></div><div><dt>Why it matters here</dt><dd>${esc(b.why_it_matters)}</dd></div><div><dt>Check first</dt><dd>${esc(b.check_first)}</dd></div></dl><blockquote>${esc(b.support_quote)}</blockquote><p class="ai-brief-foot">Written by ${esc(modelName(b.model_id))}${when?` on ${esc(when)}`:''} from the quoted source, this app's profile and backend map. Advisory: the quote was checked against the source, the conclusion was not. Verify before acting.</p></section>`;
 }

 // Plain text for the agent handoff and the digest.
 function text(f,system){
  const b=f?.ai_brief;if(!b)return '';const c=component(system,b);
  return `AI impact brief (${modelName(b.model_id)}, advisory): ${verdict(b)[0]}${c?`, most affected: ${c.name}`:''}. ${b.why_it_matters} Check first: ${b.check_first} Supporting quote: "${b.support_quote}"`;
 }

 root.BuiltWatchBriefs={line,section,text,verdict,modelName};
})(typeof window!=='undefined'?window:globalThis);

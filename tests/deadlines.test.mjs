import test from 'node:test';
import assert from 'node:assert/strict';
import '../web/status.js';
import '../web/perspectives.js';
import '../web/visuals.js';
import '../web/archmap.js';
import '../web/deadlines.js';
const D=globalThis.BuiltWatchDeadlines;
const dates=t=>D.inText(t).map(x=>[x.date.toISOString().slice(0,10),x.phrase]);

test('take-effect dates are read only from requirement phrasing and keep the quoted phrase',()=>{
 assert.deepEqual(dates('Starting February 1, 2024, all email senders must meet'),[['2024-02-01','Starting February 1, 2024']]);
 assert.deepEqual(dates('From 1 February 2026, bulk senders must authenticate'),[['2026-02-01','From 1 February 2026']]);
 assert.deepEqual(dates('Requests must use TLS 1.3 by March 1, 2027.'),[['2027-03-01','by March 1, 2027']]);
 assert.deepEqual(dates('It is deprecated and will stop working after 2025-12-31.'),[['2025-12-31','deprecated and will stop working after 2025-12-31']]);
 assert.deepEqual(dates('Published March 3, 2025. The v1 endpoint will be removed on June 30th, 2026.'),[['2026-06-30','removed on June 30th, 2026']]);
});

test('publication dates, labelled dates and impossible dates are not deadlines',()=>{
 assert.deepEqual(dates('Posted 2026-09-11 by the team'),[]);
 assert.deepEqual(dates('from the FTC’s Labor Task Force work Date June 16, 2026'),[]);
 assert.deepEqual(dates('On September 3, 2024 we announced new features'),[]);
 assert.deepEqual(dates('Effective February 30, 2026 the rule applies'),[]);
});

test('a review reports its soonest upcoming date, else its latest past one',()=>{
 const now=Date.parse('2026-10-19T12:00:00Z');
 const f={evidence:[{passage:'Effective January 15, 2027 keys rotate. Starting November 1, 2026, v1 is retired. Starting March 1, 2026, logs move.'}]};
 const w=D.of(f,now);
 assert.equal(w.date,'2026-11-01');assert.equal(w.days,13);assert.equal(w.urgency,'soon');assert.match(w.label,/in 13 days/);
 const past=D.of({facts:['Starting February 1, 2024, senders must comply']},now);
 assert.equal(past.passed,true);assert.equal(past.label,'took effect');
 assert.equal(D.of({evidence:[{passage:'No dates here.'}]},now),null);
});

test('the chip escapes the quoted phrase and names the urgency',()=>{
 const html=D.chip({date:'2026-11-01',phrase:'by <b>Nov</b> 1',days:13,passed:false,urgency:'soon'});
 assert.match(html,/deadline-chip soon/);assert.match(html,/in 13 days/);assert.doesNotMatch(html,/<b>Nov/);
});

test('handoff and digest carry the date with its quoted phrase',async()=>{
 await import('../web/handoff.js');await import('../web/notifications.js');
 const f={id:'g',system_id:'m',source_id:'gmail',relevance:'relevant',title:'Sender rules',facts:['x'],system_facts:[],inferences:[],unknowns:[],review_suggestions:[],adoption_status:'unknown',
  evidence:[{passage:'Starting November 1, 2099, senders must authenticate.'}]};
 const app={id:'m',name:'Mailer',purpose:'p'};
 assert.match(globalThis.BuiltWatchHandoff.findingPrompt(f,app,[]),/Takes effect: 2099-11-01 .*Quoted from the source: "Starting November 1, 2099"/);
 const data={demo:false,systems:[app],sources:[],runs:[],findings:[f]};
 assert.match(globalThis.BuiltWatchNotifications.digest(data,[f]),/Takes effect: 2099-11-01 \(takes effect in \d+ days\); quoted: "Starting November 1, 2099"/);
});

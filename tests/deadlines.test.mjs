import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import '../web/status.js';
import '../web/perspectives.js';
import '../web/visuals.js';
import '../web/archmap.js';
import '../web/deadlines.js';
const D=globalThis.BuiltWatchDeadlines;
const dates=t=>D.inText(t).map(x=>[x.date.toISOString().slice(0,10),x.phrase]);

// Shared with tests/test_review_titles.py so the browser and server read dates alike.
const cases=JSON.parse(readFileSync(new URL('./fixtures/take_effect_cases.json',import.meta.url),'utf8')).cases;
test('take-effect dates come only from requirement phrasing and keep the quoted phrase; publication, labelled and impossible dates do not count',()=>{
 for(const c of cases)assert.deepEqual(dates(c.text),c.dates,c.text);
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

test('calendar export holds only upcoming dates, quotes each phrase, and is valid iCalendar',()=>{
 const now=Date.parse('2026-10-19T12:00:00Z');
 const rows=[
  {id:'find_b',date:'2027-03-01',phrase:'by March 1, 2027',summary:'Billing API: TLS, keys; rotation',detail:'Source: vendor\nLands on: Payments'},
  {id:'find_a',date:'2026-11-01',phrase:'Starting November 1, 2026',summary:'Support widget: v1 retired',detail:''},
  {id:'find_old',date:'2026-03-01',phrase:'Starting March 1, 2026',summary:'Past change',detail:''},
 ];
 const out=D.ics(rows,{now,note:'HISTORICAL DEMO'});
 assert.ok(out.startsWith('BEGIN:VCALENDAR\r\nVERSION:2.0\r\n'));assert.ok(out.endsWith('END:VCALENDAR\r\n'));
 assert.ok(!/[^\r]\n/.test(out),'every line ends in CRLF');
 for(const line of out.split('\r\n'))assert.ok(new TextEncoder().encode(line).length<=75,`folded: ${line}`);
 const unfolded=out.replace(/\r\n /g,'');
 assert.equal((unfolded.match(/BEGIN:VEVENT/g)||[]).length,2);assert.doesNotMatch(unfolded,/Past change/);
 assert.ok(unfolded.indexOf('DTSTART;VALUE=DATE:20261101')<unfolded.indexOf('DTSTART;VALUE=DATE:20270301'),'soonest first');
 assert.match(unfolded,/DTSTART;VALUE=DATE:20270301\r\nDTEND;VALUE=DATE:20270302/);
 assert.match(unfolded,/UID:find_b-20270301@builtwatch/);
 assert.match(unfolded,/SUMMARY:Billing API: TLS\\, keys\\; rotation/);
 assert.match(unfolded,/DESCRIPTION:HISTORICAL DEMO\\nQuoted: “by March 1\\, 2027”\\nSource: vendor\\nLands on: Payments/);
 assert.equal((D.ics([],{now}).match(/VEVENT/g)||[]).length,0);
});

test('"today" is the viewer\'s own calendar day, not the UTC one',()=>{
 const tz=process.env.TZ;process.env.TZ='America/New_York';
 try{
  const now=Date.parse('2026-10-24T02:30:00Z'); // 22:30 on 23 October in New York
  const w=D.of({facts:['Starting October 24, 2026, v1 is retired']},now);
  assert.equal(w.days,1);assert.equal(w.label,'takes effect in 1 day');
  const today=D.of({facts:['Starting October 23, 2026, v1 is retired']},now);
  assert.equal(today.days,0);assert.equal(today.passed,false);
  assert.match(D.ics([{id:'x',date:'2026-10-23',phrase:'Starting October 23, 2026',summary:'s',detail:''}],{now}),/DTSTART;VALUE=DATE:20261023/);
 }finally{if(tz===undefined)delete process.env.TZ;else process.env.TZ=tz;}
});

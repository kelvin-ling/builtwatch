/* Take-effect dates found in a review's own quoted source text. A date is only reported
   with the exact phrase it came from, and only when a requirement word sits right before
   it ("starting", "effective", "by", "deprecated on"...). Publication dates are ignored.
   Nothing is inferred: no phrase, no deadline. */
(function(root){
 const MONTHS=['january','february','march','april','may','june','july','august','september','october','november','december'];
 const MON='(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\\.?';
 const DATE=new RegExp(`\\b(?:${MON}\\s+(\\d{1,2})(?:st|nd|rd|th)?,?\\s+(\\d{4})|(\\d{1,2})(?:st|nd|rd|th)?\\s+${MON},?\\s+(\\d{4})|(\\d{4})-(\\d{2})-(\\d{2}))\\b`,'gi');
 // Requirement or lifecycle words that make a nearby date a take-effect date.
 // Strong words may sit a few words before the date; short ones ("from", "by") must
 // immediately precede it, or "from the FTC's … Date June 16" would read as a deadline.
 const STRONG='starting|start(?:s|ing)? on|effective|takes? effect|beginning|begins?|no later than|deadline|deprecat\\w*|sunset\\w*|retir\\w*|remov\\w*|end[- ]of[- ]life|shut(?:s|ting)? down|discontinu\\w*|will (?:stop|end|no longer|require|apply)|must|required|enforce\\w*';
 const WEAK='from|by|before|until|as of|after|due';
 const TRIGGER=new RegExp(`(?:\\b(?:${STRONG})\\b[^.;:]{0,40}|\\b(?:${WEAK})\\s+(?:the\\s+)?)$`,'i');
 const PUBLISHED=/\b(published|posted|updated|last (?:modified|reviewed)|released|announced|written|copyright|dated?)\b[^.;:]{0,30}$/i;
 const monthIndex=m=>MONTHS.findIndex(x=>x.startsWith(m.toLowerCase().replace('.','').slice(0,3)));
 // The viewer's own calendar day, as a UTC midnight like the quoted dates: after 8pm in New
 // York the UTC day is already tomorrow, which would call tomorrow's date "today".
 const day=x=>new Date(Date.UTC(x.getFullYear(),x.getMonth(),x.getDate()));

 function inText(text){
  const found=[],s=String(text||'');
  for(const m of s.matchAll(DATE)){
   let y,mo,d;
   if(m[1]){mo=monthIndex(m[1]);d=+m[2];y=+m[3];}
   else if(m[5]){d=+m[4];mo=monthIndex(m[5]);y=+m[6];}
   else{y=+m[7];mo=+m[8]-1;d=+m[9];}
   if(mo<0||d<1||d>31||y<2000||y>2100)continue;
   const date=new Date(Date.UTC(y,mo,d));if(date.getUTCMonth()!==mo)continue;
   const before=s.slice(Math.max(0,m.index-60),m.index);
   if(PUBLISHED.test(before)||!TRIGGER.test(before))continue;
   // The quoted phrase: from the trigger word through the date.
   const lead=before.match(TRIGGER)[0];
   found.push({date,phrase:(lead+m[0]).replace(/\s+/g,' ').trim()});
  }
  return found;
 }

 // The deadline for one review: the soonest upcoming date in its evidence, else the most
 // recent past one. `now` is injectable for tests.
 function of(finding,now=Date.now()){
  const texts=[...(finding?.evidence||[]).map(e=>e?.passage),...(finding?.facts||[])];
  const all=texts.flatMap(inText);if(!all.length)return null;
  const today=day(new Date(now)).getTime();
  const upcoming=all.filter(x=>x.date.getTime()>=today).sort((a,b)=>a.date-b.date);
  const pick=upcoming[0]||all.sort((a,b)=>b.date-a.date)[0];
  const days=Math.round((pick.date.getTime()-today)/86400000);
  return {date:pick.date.toISOString().slice(0,10),phrase:pick.phrase,days,passed:days<0,
   label:days<0?'took effect':days===0?'takes effect today':`takes effect in ${days} ${days===1?'day':'days'}`,
   urgency:days<0?'passed':days<=30?'soon':days<=90?'upcoming':'later'};
 }

 const fmt=iso=>new Date(iso+'T12:00:00Z').toLocaleDateString(undefined,{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'});
 function chip(d){if(!d)return '';const esc=root.BuiltWatchVisuals.escape;return `<span class="deadline-chip ${d.urgency}" title="${esc('Quoted: “'+d.phrase+'”')}">${root.BuiltWatchVisuals.icon('clock')}${d.passed?`Took effect ${esc(fmt(d.date))}`:`${esc(fmt(d.date))} · ${d.days===0?'today':`in ${d.days} ${d.days===1?'day':'days'}`}`}</span>`;}

 // An iCalendar (RFC 5545) file of upcoming take-effect dates as all-day events. Each event
 // carries the exact quoted phrase; dates that already passed are left out. Rows are
 // {id,date,phrase,summary,detail}; `note` (e.g. demo replay) is prefixed to each description.
 const icsText=v=>String(v??'').replace(/\\/g,'\\\\').replace(/;/g,'\\;').replace(/,/g,'\\,').replace(/\r?\n/g,'\\n');
 const fold=line=>{const out=[];let cur='',n=0;for(const ch of line){const b=new TextEncoder().encode(ch).length;if(n+b>(out.length?74:75)){out.push(cur);cur='';n=0;}cur+=ch;n+=b;}out.push(cur);return out.join('\r\n ');};
 const compact=iso=>iso.replace(/-/g,'');
 function ics(rows,{now=Date.now(),note=''}={}){
  const today=day(new Date(now)).toISOString().slice(0,10),stamp=new Date(now).toISOString().replace(/[-:]/g,'').replace(/\.\d+/,'');
  const events=(rows||[]).filter(r=>r?.date&&r.date>=today).sort((a,b)=>a.date.localeCompare(b.date)).map(r=>{const end=new Date(Date.parse(r.date+'T00:00:00Z')+86400000).toISOString().slice(0,10);return ['BEGIN:VEVENT',`UID:${icsText(r.id)}-${compact(r.date)}@builtwatch`,`DTSTAMP:${stamp}`,`DTSTART;VALUE=DATE:${compact(r.date)}`,`DTEND;VALUE=DATE:${compact(end)}`,`SUMMARY:${icsText(r.summary)}`,`DESCRIPTION:${icsText([note,`Quoted: “${r.phrase}”`,r.detail].filter(Boolean).join('\n'))}`,'TRANSP:TRANSPARENT','END:VEVENT'];});
  return ['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//BuiltWatch//Take-effect dates//EN','CALSCALE:GREGORIAN','X-WR-CALNAME:BuiltWatch take-effect dates',...events.flat(),'END:VCALENDAR'].map(fold).join('\r\n')+'\r\n';
 }

 root.BuiltWatchDeadlines={inText,of,chip,fmt,ics};
})(typeof window!=='undefined'?window:globalThis);

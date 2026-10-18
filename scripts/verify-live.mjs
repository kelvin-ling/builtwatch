// Compare a deployed site with this checkout's build: every hash-stamped asset reference,
// each asset's bytes, and the cache policy. Exits non-zero on any mismatch so "deployed"
// means the release is actually being served.
//   node scripts/verify-live.mjs [origin]      (default https://builtwatch.org)
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';

const origin=(process.argv[2]||'https://builtwatch.org').replace(/\/$/,'');
const hash=text=>createHash('sha256').update(text).digest('hex').slice(0,12);
const fetchText=async path=>{const r=await fetch(origin+path,{cache:'no-store'});return {status:r.status,cache:r.headers.get('cache-control'),body:await r.text()};};

const page=await fetchText('/');
const refs=[...page.body.matchAll(/(?:href|src)="\/([\w.-]+\.(?:css|js|svg))(?:\?v=([^"]*))?"/g)].map(m=>({file:m[1],v:m[2]||''}));
const local=(await readFile('web/index.html','utf8')).match(/(?:href|src)="\/([\w.-]+\.(?:css|js|svg))"/g).map(x=>x.match(/\/([\w.-]+)"/)[1]);
const rows=[],problems=[];
for(const file of new Set([...local,...refs.map(r=>r.file)])){
 const expected=hash(await readFile('web/'+file,'utf8').catch(()=>'')),ref=refs.find(r=>r.file===file);
 if(!ref){problems.push(`${file}: not referenced by the live page`);rows.push([file,expected,'missing','—']);continue;}
 const asset=await fetchText(`/${file}?v=${ref.v}`),served=hash(asset.body);
 if(!local.includes(file))problems.push(`${file}: served but not in this build`);
 if(served!==expected)problems.push(`${file}: live bytes ${served} differ from build ${expected}`);
 if(ref.v!==served)problems.push(`${file}: page references ?v=${ref.v||'(none)'}, bytes hash to ${served}`);
 if(!/immutable/.test(asset.cache||''))problems.push(`${file}: cache-control "${asset.cache}" is not immutable`);
 rows.push([file,expected,served,asset.cache||'']);
}
if(page.cache!=='no-cache')problems.push(`page: cache-control "${page.cache}", expected no-cache`);
console.log(`Live check: ${origin}\n`);
for(const [file,expected,served,cache] of rows)console.log(`${expected===served?'ok  ':'DIFF'} ${file.padEnd(18)} build ${expected}  live ${served}  ${cache}`);
console.log(problems.length?`\n${problems.length} problem(s):\n- ${problems.join('\n- ')}`:'\nLive site matches this build.');
process.exitCode=problems.length?1:0;

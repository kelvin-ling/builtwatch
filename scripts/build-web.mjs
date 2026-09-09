import { mkdir, readFile, writeFile, rm } from 'node:fs/promises';
await rm('dist', { recursive:true, force:true });
await mkdir('dist/server', { recursive:true });
const types = {html:'text/html; charset=utf-8',css:'text/css; charset=utf-8',js:'text/javascript; charset=utf-8',json:'application/json',svg:'image/svg+xml'};
const assets = {};
for (const file of ['index.html','style.css','app.js','client.js','handoff.js','config.js','demo.json','favicon.svg']) {
  assets['/'+file] = {content:await readFile('web/'+file,'utf8'),type:types[file.split('.').pop()]};
}
const source = await readFile('server/worker.mjs','utf8');
await writeFile('dist/server/index.js',source+'\nexport default createWorker('+JSON.stringify(assets)+');\n');
console.log('BuiltWatch server and web assets built.');

import { mkdir, readFile, writeFile, rm } from 'node:fs/promises';
await rm('dist', { recursive:true, force:true });
await mkdir('dist/server', { recursive:true });
const types = {html:'text/html; charset=utf-8',css:'text/css; charset=utf-8',js:'text/javascript; charset=utf-8',json:'application/json',svg:'image/svg+xml'};
const assets = {};
for (const file of ['index.html','style.css','app.js','status.js','client.js','handoff.js','perspectives.js','demo.js','config.js','demo.json','favicon.svg']) {
  assets['/'+file] = {content:await readFile('web/'+file,'utf8'),type:types[file.split('.').pop()]};
}
const source = await readFile('server/worker.mjs','utf8');
await writeFile('dist/server/index.js',source+'\nexport default createWorker('+JSON.stringify(assets)+');\n');
console.log('BuiltWatch server and web assets built.');
// A downloadable, standalone demonstration survives API/model allowances and can run offline.
let offline=assets['/index.html'].content.replace(/<link rel="stylesheet" href="\/style.css(?:\?[^\"]*)?">/,'<style>'+assets['/style.css'].content+'</style>');
offline=offline.replace(/<script[^>]*src="\/(.*?)"><\/script>/g,(_,file)=>'<script>'+assets['/'+file.split('?')[0]].content.replaceAll('</script','<\\/script')+'</script>');
offline=offline.replace('<script>'+assets['/config.js'].content,'<script>window.BUILTWATCH_OFFLINE=true;window.BUILTWATCH_DEMO_DATA='+JSON.stringify(JSON.parse(assets['/demo.json'].content)).replaceAll('<','\\u003c')+';'+assets['/config.js'].content);
// Preserve deferred execution after the DOM exists when scripts become inline.
const scripts=[...offline.matchAll(/<script>[\s\S]*?<\/script>/g)].map(x=>x[0]).join('');
offline=offline.replace(/<script>[\s\S]*?<\/script>/g,'').replace('</body>',scripts+'</body>');
assets['/offline-demo.html']={content:offline,type:'text/html; charset=utf-8'};
await writeFile('dist/server/index.js',source+'\nexport default createWorker('+JSON.stringify(assets)+');\n');
await writeFile('dist/offline-demo.html',offline);

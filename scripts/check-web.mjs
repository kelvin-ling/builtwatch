import {readdir} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
for(const directory of ['web','server','scripts']){
 for(const name of await readdir(directory)){
  if(/\.(?:js|mjs)$/.test(name))execFileSync(process.execPath,['--check',`${directory}/${name}`],{stdio:'inherit'});
 }
}
console.log('All browser, gateway and build scripts parse.');

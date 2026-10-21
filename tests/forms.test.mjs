import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const source=readFileSync(new URL('../web/app.js',import.meta.url),'utf8');
function harness(){
 const attributes=new Map(),error={textContent:''},controls=['name','purpose','services','technologies','data_categories','jurisdictions','assumptions','constraints','unknowns','consequential_actions'].map(name=>({name,value:name==='name'?'Saved app':name==='purpose'?'Submitted purpose':name==='services'?'Gmail API\nHubSpot':'',disabled:false,isConnected:true}));
 const submit={disabled:false,isConnected:true,focus(){}},unavailable={disabled:true,isConnected:true},closeButton={disabled:false,isConnected:true};controls.push(submit,unavailable,closeButton);
 const dialog={open:true,querySelectorAll:()=>controls},form={id:'system-form',dataset:{id:'saved-app'},closest:()=>dialog,querySelector:q=>q==='.error'?error:null,getAttribute:k=>attributes.get(k)??null,setAttribute:(k,v)=>attributes.set(k,v),removeAttribute:k=>attributes.delete(k),after(){}};
 let handler,resolve,reject,calls=0,payload,closed=false;
 const context=vm.createContext({busy:false,draftProfile:null,state:{demo:false,systems:[{id:'saved-app',name:'Saved app',purpose:'Old purpose',services:['Gmail API','HubSpot']}]},document:{body:{},activeElement:submit,createElement:()=>({setAttribute(){},remove(){}}),addEventListener:(type,fn)=>{if(type==='submit')handler=fn;}},FormData:class{constructor(){this.values=new Map(controls.filter(c=>c.name&&!c.disabled).map(c=>[c.name,c.value]));}get(k){return this.values.get(k)??null;}},$:q=>q==='#modal'?dialog:null,api:async(path,data)=>{calls++;payload=JSON.parse(JSON.stringify(data));return new Promise((yes,no)=>{resolve=yes;reject=no;});},close:()=>{closed=true;dialog.open=false;},refresh:async()=>{},navigate:()=>{},toast:()=>{}});
 const start=source.indexOf("document.addEventListener('submit',async e=>{e.preventDefault();"),end=source.indexOf("\ndocument.addEventListener('input'",start),helper=source.indexOf('function lockModalForm(');
 assert.ok(start>=0&&end>start);
 if(helper>=0)vm.runInContext(source.slice(helper,start),context);
 vm.runInContext(source.slice(start,end),context);
 const event={target:form,preventDefault(){}};
 return {context,form,controls,submit,unavailable,closeButton,error,run:()=>handler(event),resolve:()=>resolve({ok:true}),reject:()=>reject(Error('Save unavailable')),get calls(){return calls;},get payload(){return payload;},get closed(){return closed;}};
}
test('a pending profile save locks edits and dismissal without losing disabled form fields from its payload',async()=>{
 const h=harness(),pending=h.run();try{
  assert.equal(h.calls,1);assert.equal(h.controls.find(c=>c.name==='purpose').disabled,true,'typing must not race a submitted profile');assert.equal(h.closeButton.disabled,true);assert.equal(h.submit.disabled,true);assert.equal(h.form.getAttribute('aria-busy'),'true');
  assert.equal(h.payload.name,'Saved app');assert.equal(h.payload.purpose,'Submitted purpose');assert.deepEqual(h.payload.services,['Gmail API','HubSpot']);
  await h.run();assert.equal(h.calls,1,'a second submit cannot start another mutation');
 }finally{h.resolve();await pending;}
 assert.equal(h.closed,true);assert.equal(h.context.busy,false);assert.equal(h.unavailable.disabled,true,'previously disabled controls stay disabled');
});
test('a rejected profile save keeps values, restores editable controls and permits an explicit retry',async()=>{
 const h=harness(),pending=h.run();h.reject();await pending;
 assert.equal(h.closed,false);assert.equal(h.controls.find(c=>c.name==='purpose').value,'Submitted purpose');assert.equal(h.controls.find(c=>c.name==='purpose').disabled,false);assert.equal(h.closeButton.disabled,false);assert.equal(h.submit.disabled,false);assert.equal(h.unavailable.disabled,true);assert.equal(h.form.getAttribute('aria-busy'),null);assert.match(h.error.textContent,/Save unavailable/);
 const retry=h.run();assert.equal(h.calls,2);h.resolve();await retry;assert.equal(h.closed,true);
});

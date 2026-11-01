const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const handlers={},scope={self:{location:{origin:'https://example.test'},addEventListener:(name,fn)=>handlers[name]=fn},URL,Set};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../ui/service-worker.js'),'utf8'),scope);
let responded=false;
handlers.fetch({request:{method:'GET',url:'https://example.test/legal/privacy',mode:'navigate'},respondWith(){responded=true}});assert.equal(responded,false);
handlers.fetch({request:{method:'GET',url:'https://example.test/legal/terms',mode:'navigate'},respondWith(){responded=true}});assert.equal(responded,false);
handlers.fetch({request:{method:'GET',url:'https://example.test/api/legal',mode:'cors'},respondWith(){responded=true}});assert.equal(responded,false);
console.log('PASS: legal documents never replace the offline app shell, legal metadata stays network-only');

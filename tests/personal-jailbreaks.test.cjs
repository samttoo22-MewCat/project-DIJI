const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),{JSDOM}=require('jsdom');
const root=path.resolve(__dirname,'..'),dom=new JSDOM(fs.readFileSync(path.join(root,'ui/index.html'),'utf8'),{url:'https://example.test',runScripts:'outside-only'}),w=dom.window;
const preset={id:'qa-preset',name:'QA 預設',model:'test/model',last_updated:'2026-11-01',source_url:'https://example.test',review_status:'approved',prompt:'預設內容',openrouter_models:['test/model'],storage_scope:'default'};
let saved=null,requests=0;
w.confirm=()=>true;w.fetch=async(url,options={})=>{
 requests++;
 if(options.method==='PUT'){saved={...JSON.parse(options.body),storage_scope:'personal'};return {ok:true,json:async()=>saved};}
 if(options.method==='DELETE'){saved=null;return {ok:true,json:async()=>preset};}
 return {ok:true,json:async()=>[saved || preset]};
};
w.eval('let workspaceAvailable=true;const state={};\n'+fs.readFileSync(path.join(root,'ui/jailbreak-studio.js'),'utf8'));
const tick=()=>new Promise(resolve=>setTimeout(resolve,15)),d=w.document;
(async()=>{
 d.querySelector('[data-view="jailbreak"]').click();await tick();
 const del=d.querySelector('.jailbreak-editor-actions .danger-button');assert.equal(del.disabled,true);assert.match(d.querySelector('#jailbreak-editor-status').textContent,/系統預設/);assert.match(d.querySelector('#jailbreak-list').textContent,/預設/);
 d.querySelector('#jailbreak-prompt').value='私人修改';d.querySelector('#jailbreak-form').dispatchEvent(new w.Event('submit',{cancelable:true}));await tick();
 assert.equal(saved.prompt,'私人修改');assert.equal(del.disabled,false);assert.equal(del.textContent,'刪除個人版本');assert.match(d.querySelector('#jailbreak-editor-status').textContent,/不影響其他使用者/);assert.match(d.querySelector('#jailbreak-list').textContent,/個人/);
 del.click();await tick();await tick();assert.equal(saved,null);assert.equal(del.disabled,true);assert.equal(d.querySelector('#jailbreak-prompt').value,'預設內容');assert.match(d.querySelector('#jailbreak-editor-status').textContent,/恢復使用系統預設/);
 const strong=[...d.querySelectorAll('.provider-description strong')].find(e=>e.textContent==='提供方便易用的繁體中文介面，十分推薦給台灣使用者。');assert.ok(strong);assert.equal(strong.nextElementSibling.tagName,'BR');
 console.log('PASS: default/private labels, independent save, restore default, protected default deletion, bold recommendation and newline');w.close();
})().catch(e=>{console.error(e);w.close();process.exitCode=1});

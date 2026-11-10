const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),{JSDOM}=require('jsdom');
const root=path.resolve(__dirname,'..'),dom=new JSDOM(fs.readFileSync(path.join(root,'ui/index.html'),'utf8'),{url:'https://example.test',runScripts:'outside-only'}),w=dom.window,d=w.document;
w.matchMedia=()=>({matches:false,addEventListener(){}});w.crypto.randomUUID=()=>`00000000-0000-4000-8000-${String(Math.random()).slice(2,14).padEnd(12,'0')}`;w.confirm=()=>true;w.HTMLElement.prototype.scrollIntoView=function(){};w.HTMLDialogElement.prototype.showModal=function(){this.open=true};w.HTMLDialogElement.prototype.close=function(){this.open=false};
const defaults=[{id:'yelan',name:'夜蘭',premise:'預設角色背景',voice:'預設說話方式',relationship_start:'familiar',profile:{character_name:'夜蘭',personality:'沉著'},style_guide:'預設風格',generation_metadata:{category:'預設'},full_prompt:'原始完整 prompt',source:{}}];
const qaAlt={...defaults[0],id:'yelan-alt',name:'夜蘭二號',profile:{character_name:'夜蘭二號'},source:{visibility:'private'}};
const accountBRole={...defaults[0],id:'account-b-role',name:'B 私人角色',profile:{character_name:'B 私人角色'},source:{visibility:'private'}};
let currentAccount='qa',accountCharacters={qa:[qaAlt],'account-b':[accountBRole]},copyCalls=0,copyKey=null,createOnLostReply=null,firstCopyGate=null,copyPersisted=false,puts=[],holdRoleGet=false,releaseRoleGet=null,holdNextCopyResponse=false,releaseCopyResponse=null,holdNextPutResponse=false,releasePutResponse=null;
const json=(data,status=200)=>({ok:status>=200&&status<300,status,json:async()=>data});
w.fetch=async(url,options={})=>{
 if(url==='/api/characters')return json([...defaults,...accountCharacters[currentAccount]]);
 if(url.startsWith('/api/characters/')&&url.endsWith('/copy')){
   copyCalls++;const key=options.headers['Idempotency-Key'];copyKey??=key;
   if(copyCalls===1){await firstCopyGate;const id='copy-yelan-stable';createOnLostReply={...defaults[0],id,source:{visibility:'private',copied_from:'yelan',copy_request_id:key}};accountCharacters[currentAccount]=[...accountCharacters[currentAccount],createOnLostReply];copyPersisted=true;throw new Error('simulated lost response');}
   if(copyCalls===2){assert.equal(createOnLostReply.source.copy_request_id,key);return json(createOnLostReply,201);}
   const requestAccount=currentAccount,id=`copy-yelan-${copyCalls}`;
   const record={...defaults[0],id,source:{visibility:'private',copied_from:'yelan',copy_request_id:key}};
   accountCharacters[requestAccount]=[...accountCharacters[requestAccount],record];
   if(holdNextCopyResponse){holdNextCopyResponse=false;return await new Promise(resolve=>{releaseCopyResponse=()=>resolve(json(record,201));});}
   return json(record,201);
 }
 const roleId=decodeURIComponent(url.slice('/api/characters/'.length));
 if(url.startsWith('/api/characters/')&&options.method==='PUT'){
   const requestAccount=currentAccount,body=JSON.parse(options.body);puts.push(body);accountCharacters[requestAccount]=accountCharacters[requestAccount].map(item=>item.id===body.id?body:item);
   if(holdNextPutResponse){holdNextPutResponse=false;return await new Promise(resolve=>{releasePutResponse=()=>resolve(json(body));});}
   return json(body);
 }
 if(url.startsWith('/api/characters/')){
   const found=accountCharacters[currentAccount].find(item=>item.id===roleId)||defaults.find(item=>item.id===roleId);
   if(found&&holdRoleGet){holdRoleGet=false;return await new Promise(resolve=>{releaseRoleGet=()=>resolve(json(found));});}
   return json(found||{detail:'not found'},found?200:404);
 }
 if(url==='/api/jailbreaks')return json([{id:'jb',name:'QA',last_updated:'2026-11-11',review_status:'approved',prompt:'x',openrouter_models:['test/model']}]);
 if(url==='/api/character-generations')return json([]);
 return json([]);
};
for(const button of d.querySelectorAll('[data-view]'))button.addEventListener('click',()=>{for(const screen of d.querySelectorAll('[data-screen]'))screen.classList.toggle('active',screen.dataset.screen===button.dataset.view);});
w.eval('let workspaceAvailable=true;let authenticatedUser={id:"qa"};window.__setTestIdentity=(id)=>{authenticatedUser={id};workspaceAvailable=true};window.__logoutTestIdentity=()=>{workspaceAvailable=false};function renderSidebarCharacters(){};window.dijiState={characters:[],playerPersonaId:null};window.dijiSelectCharacter=()=>{};'+fs.readFileSync(path.join(root,'ui/character-creator.js'),'utf8'));
const tick=()=>new Promise(resolve=>setTimeout(resolve,30));
async function switchAccount(id){currentAccount=id;w.__setTestIdentity(id);w.dispatchEvent(new w.Event('diji-workspace-ready'));await tick();}
(async()=>{
 const card=(id)=>d.querySelector(`[data-character-id="${id}"] .character-library-select`);
 const openDetail=async(id)=>{card(id).click();await tick();};
 const openEditor=async(id)=>{await openDetail(id);d.querySelector('[data-character-detail-edit]').click();await tick();};
 await tick();assert.ok(card('yelan'));
 await openDetail('yelan');assert.equal(d.querySelector('[data-character-detail-prompt]').textContent,defaults[0].full_prompt);
 let copy=d.querySelector('[data-character-detail-copy]');let releaseFirst;firstCopyGate=new Promise(resolve=>releaseFirst=resolve);
 copy.click();copy.click();await tick();assert.equal(copyCalls,1);assert.equal(copy.disabled,true);releaseFirst();await tick();await tick();
 assert.equal(copyPersisted,true);assert.match(d.querySelector('#character-library-status').textContent,/simulated lost response/);
 copy.click();await tick();await tick();assert.equal(copyCalls,2);assert.equal(accountCharacters.qa.length,2);
 assert.equal(d.querySelector('[data-character-detail-visibility]').textContent,'我的角色 · 僅自己可見');assert.equal(d.querySelector('[data-character-detail-edit]').hidden,false);
 copy=d.querySelector('[data-character-detail-copy]');d.querySelector('[data-character-detail-close]').click();await openEditor('copy-yelan-stable');
 let review=d.querySelector('.character-review');review.querySelector('input').value='取消不保存';review.querySelector('input').dispatchEvent(new w.Event('input',{bubbles:true}));
 review.querySelector('.creator-cancel-edit').click();await tick();assert.equal(puts.length,0);assert.equal(accountCharacters.qa.find(item=>item.id==='copy-yelan-stable').name,'夜蘭');
 await openEditor('copy-yelan-stable');review=d.querySelector('.character-review');review.querySelector('input').value='夜蘭的新名字';review.querySelector('input').dispatchEvent(new w.Event('input',{bubbles:true}));
 review.querySelector('.creator-review-actions button[type="submit"]').click();await tick();await tick();
 assert.equal(puts.length,1);assert.equal(puts[0].id,'copy-yelan-stable');assert.equal(puts[0].name,'夜蘭的新名字');assert.equal(puts[0].source.copy_request_id,copyKey);assert.equal(puts[0].relationship_start,'familiar');assert.equal(puts[0].generation_metadata.category,'預設');
 assert.equal(defaults[0].name,'夜蘭');assert.equal(defaults[0].premise,'預設角色背景');
 d.querySelector('[data-view="characters"]').click();await tick();await openEditor('copy-yelan-stable');
 let reviewNow=d.querySelector('.character-review');reviewNow.querySelector('input').value='A 帳號未儲存草稿';reviewNow.querySelector('input').dispatchEvent(new w.Event('input',{bubbles:true}));
 d.querySelector('[data-view="characters"]').click();await tick();await openEditor('yelan-alt');assert.equal(d.querySelector('.character-review input').value,'夜蘭二號');
 reviewNow=d.querySelector('.character-review');reviewNow.querySelector('input').value='B 角色未儲存草稿';reviewNow.querySelector('input').dispatchEvent(new w.Event('input',{bubbles:true}));
 d.querySelector('[data-view="characters"]').click();await tick();await openEditor('copy-yelan-stable');assert.equal(d.querySelector('.character-review input').value,'A 帳號未儲存草稿','first role draft must survive opening another role');
 d.querySelector('[data-view="characters"]').click();await tick();await openEditor('yelan-alt');assert.equal(d.querySelector('.character-review input').value,'B 角色未儲存草稿','each role must retain its own draft');
 d.querySelector('.creator-cancel-edit').click();await tick();assert.equal(accountCharacters.qa.find(item=>item.id==='copy-yelan-stable').name,'夜蘭的新名字','canceling a recovered edit must not persist it');
 await openDetail('yelan');holdNextCopyResponse=true;copy=d.querySelector('[data-character-detail-copy]');copy.click();await tick();assert.equal(typeof releaseCopyResponse,'function');
 await switchAccount('account-b');releaseCopyResponse();await tick();await tick();
 assert.equal(d.querySelector('#character-detail-dialog').open,false,'a late copy response must not reopen the previous account details');
 assert.equal(w.dijiState.characters.some(item=>item.id==='copy-yelan-3'),false,'a late copy response must not contaminate the new account library');
 await openEditor('account-b-role');reviewNow=d.querySelector('.character-review');reviewNow.querySelector('input').value='B 帳號更新中';reviewNow.querySelector('input').dispatchEvent(new w.Event('input',{bubbles:true}));
 holdNextPutResponse=true;reviewNow.querySelector('.creator-review-actions button[type="submit"]').click();await tick();assert.equal(typeof releasePutResponse,'function');
 await switchAccount('qa');releasePutResponse();await tick();await tick();
 assert.notEqual(d.querySelector('#creator-title')?.textContent,'編輯角色：B 私人角色','a late save response must not reopen the previous account editor');
 assert.equal(w.dijiState.characters.some(item=>item.name==='B 帳號更新中'),false,'a late save response must not contaminate the new account library');
 await openDetail('copy-yelan-stable');holdRoleGet=true;d.querySelector('[data-character-detail-edit]').click();await tick();assert.equal(typeof releaseRoleGet,'function');
 await switchAccount('account-b');releaseRoleGet();await tick();await tick();
 assert.notEqual(d.querySelector('#creator-title')?.textContent,'編輯角色：夜蘭的新名字','a delayed role GET must not open the previous account editor');
 await openDetail('account-b-role');holdRoleGet=true;d.querySelector('[data-character-detail-edit]').click();await tick();assert.equal(typeof releaseRoleGet,'function');
 w.__logoutTestIdentity();d.querySelector('[data-auth-logout]').click();releaseRoleGet();await tick();await tick();
 assert.notEqual(d.querySelector('#creator-title')?.textContent,'編輯角色：B 帳號更新中','a stale role response must not reopen the previous account editor after logout');
 console.log('PASS: idempotent retry, private edit/copy, per-role draft recovery, stale GET/POST/PUT isolation across account changes and logout');w.close();
})().catch(error=>{console.error(error);w.close();process.exitCode=1;});

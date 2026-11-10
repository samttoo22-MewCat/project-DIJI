const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),{JSDOM}=require('jsdom');
const root=path.resolve(__dirname,'..'),dom=new JSDOM(fs.readFileSync(path.join(root,'ui/index.html'),'utf8'),{url:'https://example.test',runScripts:'outside-only'}),w=dom.window,d=w.document;
w.matchMedia=()=>({matches:false,addEventListener(){}});w.crypto.randomUUID=()=>`00000000-0000-4000-8000-${String(Math.random()).slice(2,14).padEnd(12,'0')}`;w.confirm=()=>true;
w.HTMLElement.prototype.scrollIntoView=function(){};w.HTMLDialogElement.prototype.showModal=function(){this.open=true};w.HTMLDialogElement.prototype.close=function(){this.open=false};
const source={id:'yelan',name:'夜蘭',premise:'沉著敏銳的情報員',voice:'克制而精準',profile:{character_name:'夜蘭',personality:'沉著'},full_prompt:'你是夜蘭。\n\n第二段完整人設。\n風格指南也在此。',style_guide:'克制而精準',source:{}};
const own={...source,id:'own-role',name:'我的夜蘭',profile:{character_name:'我的夜蘭'},full_prompt:'我的私人提示詞\n第二段。',source:{visibility:'private'}};
let catalog=[source,own],copies=0,chatSelections=0;
const json=(data,status=200)=>({ok:status>=200&&status<300,status,json:async()=>data});
w.fetch=async(url,options={})=>{
 if(url==='/api/characters')return json(catalog);
 if(url.startsWith('/api/characters/')&&url.endsWith('/copy')){copies++;const key=options.headers['Idempotency-Key'];const copied={...source,id:`copy-${copies}`,source:{visibility:'private',copied_from:'yelan',copy_request_id:key}};catalog=[...catalog,copied];return json(copied,201);}
 if(url.startsWith('/api/characters/'))return json(catalog.find(item=>item.id===decodeURIComponent(url.slice('/api/characters/'.length)))||{detail:'not found'},200);
 if(url==='/api/jailbreaks')return json([]);
 if(url==='/api/character-generations')return json([]);
 return json([]);
};
for(const button of d.querySelectorAll('[data-view]'))button.addEventListener('click',()=>{for(const screen of d.querySelectorAll('[data-screen]'))screen.classList.toggle('active',screen.dataset.screen===button.dataset.view);});
w.eval('let workspaceAvailable=true;let authenticatedUser={id:"detail-test"};function renderSidebarCharacters(){};window.dijiState={characters:[],playerPersonaId:null};window.dijiSelectCharacter=()=>{window.__chatSelections=(window.__chatSelections||0)+1};'+fs.readFileSync(path.join(root,'ui/character-creator.js'),'utf8'));
const tick=()=>new Promise(resolve=>setTimeout(resolve,30));
(async()=>{
 await tick();
 const publicCard=d.querySelector('[aria-label="選擇角色：夜蘭"]');assert.ok(publicCard);publicCard.click();await tick();
 const dialog=d.querySelector('#character-detail-dialog');assert.equal(dialog.open,true);assert.equal(d.querySelector('[data-character-detail-prompt]').textContent,source.full_prompt,'the full prompt must preserve paragraph breaks');assert.equal(w.__chatSelections||0,0,'opening a role card must not start a conversation');
 assert.equal(d.querySelector('[data-character-detail-edit]').hidden,true,'shared roles cannot be edited directly');assert.equal(d.querySelector('[data-character-detail-copy]').textContent,'複製');assert.equal(d.querySelector('[data-character-detail-chat]').textContent,'開始跟角色聊天');
 d.querySelector('[data-character-detail-copy]').click();await tick();await tick();
 assert.equal(copies,1);assert.equal(dialog.open,true);assert.equal(d.querySelector('[data-character-detail-name]').textContent,'夜蘭');assert.equal(d.querySelector('[data-character-detail-visibility]').textContent,'我的角色 · 僅自己可見');assert.match(d.querySelector('[data-character-detail-status]').textContent,/只有你的帳號看得到/);assert.equal(d.querySelector('[data-character-detail-edit]').hidden,false);assert.equal(d.querySelector('[data-character-detail-prompt]').textContent,source.full_prompt);
 d.querySelector('[data-character-detail-chat]').click();await tick();assert.equal(dialog.open,false);assert.equal(w.__chatSelections,1,'chat starts only after the explicit chat action');
 d.querySelector('[aria-label="選擇角色：我的夜蘭"]').click();await tick();assert.equal(d.querySelector('[data-character-detail-prompt]').textContent,own.full_prompt);assert.equal(d.querySelector('[data-character-detail-edit]').hidden,false);
 d.querySelector('[data-character-detail-edit]').click();await tick();assert.ok(d.querySelector('.character-review'),'the owner can open the existing editor');
 d.querySelector('.creator-cancel-edit').click();await tick();assert.equal(catalog.find(item=>item.id==='own-role').name,'我的夜蘭','cancel must not write role changes');
 console.log('PASS: role cards open full-prompt details, copy creates a private editable copy, chat requires explicit action, own role can edit and cancel');w.close();
})().catch(error=>{console.error(error);w.close();process.exitCode=1;});

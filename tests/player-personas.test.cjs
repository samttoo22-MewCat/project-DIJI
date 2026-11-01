const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),{JSDOM}=require('jsdom');
const root=path.resolve(__dirname,'..');
const dom=new JSDOM(fs.readFileSync(path.join(root,'ui/index.html'),'utf8'),{url:'https://example.test/',runScripts:'outside-only'}),w=dom.window;
w.matchMedia=()=>({matches:false,addEventListener(){}});w.HTMLDialogElement.prototype.showModal=function(){this.open=true};
w.HTMLDialogElement.prototype.close=function(){this.open=false};
const records=[{id:'player-first',label:'旅行者',name:'霧川',sex:'女',age:'28',description:'海邊的調香師'},{id:'player-second',label:'醫師',name:'清河',description:'山城醫師'}];
let chats=[],saved=[],available=[],deleted=[];w.crypto.randomUUID=()=>`00000000-0000-4000-8000-${String(chats.length).padStart(12,'0')}`;
w.fetch=async(url,options={})=>{
 let data=[];
 if(url==='/api/auth/session')data={authenticated:true,auth_required:true,user:{id:'test-owner',display_name:'測試'}};
 else if(url==='/api/connections/priority')data={priority:['openrouter'],connected:['openrouter']};
 else if(url==='/api/bootstrap')data={characters:[],flows:[]};
 else if(url==='/api/player-personas') {if(options.method==='POST'){saved.push(JSON.parse(options.body));data={id:'new',...saved.at(-1)}}else data=available;}
 else if(url.startsWith('/api/player-personas/') && options.method==='DELETE'){const id=url.split('/').at(-1);deleted.push(id);available=available.filter(record=>record.id!==id);}
 else if(url==='/api/conversations' && options.method==='POST') {const body=JSON.parse(options.body),p=records.find(r=>r.id===body.player_persona_id);data={...body,player_persona:p ? {name:p.name,sex:p.sex || '',age:p.age || '',description:p.description,chat_mode:'story'} : {name:'使用者',chat_mode:'story'},messages:[]};chats.push(data);}
 else if(url==='/api/conversations')data=chats;
 return {ok:true,status:200,json:async()=>data};
};
w.eval(fs.readFileSync(path.join(root,'ui/app.js'),'utf8')+'\n'+fs.readFileSync(path.join(root,'ui/player-personas.js'),'utf8')); 
const d=w.document,tick=()=>new Promise(r=>setTimeout(r,30));
(async()=>{
 await tick();assert.equal(d.querySelector('[data-view=characters]').nextElementSibling.dataset.view,'player-personas');
 w.dijiState.characters=[{id:'role-one',name:'角色',profile:{}}];
 await w.dijiSelectCharacter(w.dijiState.characters[0]);await tick();
 assert.equal(chats.length,0);assert.equal(d.querySelector('.screen.active').dataset.screen,'player-personas');
 available=records;w.dijiState.characters=[];w.dijiState.characterId=null;w.dispatchEvent(new w.Event('diji-workspace-ready'));await tick();
 assert.equal(d.querySelectorAll('.player-card').length,2);
 d.querySelector('.player-card .primary-button').click();await tick();
 assert.equal(w.dijiState.playerPersonaId,'player-first');assert.equal(chats.length,0);
 w.dijiState.characters=[{id:'role-one',name:'角色',profile:{}}];
 await w.dijiSelectCharacter(w.dijiState.characters[0]);
 const oldId=w.dijiState.chatId;
 assert.equal(chats[0].player_persona_id,'player-first');
 w.dijiState.history=[{sender_type:1,text:'舊對話'}];
 const select=d.querySelector('#chat-player-select');select.value='player-second';select.dispatchEvent(new w.Event('change'));await tick();
 assert.notEqual(w.dijiState.chatId,oldId);assert.equal(chats.length,2);assert.equal(chats[0].player_persona.name,'霧川');
 assert.equal(w.dijiState.playerPersona.name,'清河');assert.deepEqual([...w.dijiState.history],[]);
 w.eval('setComposerBusy(true)');assert.equal(select.disabled,true);
 const count=chats.length;d.querySelector('.player-card .primary-button').click();await tick();assert.equal(chats.length,count);
 w.eval('setComposerBusy(false)');assert.equal(select.disabled,false);
 d.querySelector('#player-new').click();const form=d.querySelector('#player-persona-form');
 for(const [key,value] of Object.entries({label:'新設定',name:'測試玩家',description:'測試背景'}))form.elements.namedItem(key).value=value;
 form.dispatchEvent(new w.Event('submit',{cancelable:true}));await tick();assert.equal(saved[0].name,'測試玩家');assert.equal(form.hidden,true);
 w.dijiState.history=[{sender_type:1,text:'保留的訊息'}];
 const snapshot=JSON.stringify(w.dijiState.playerPersona);
 d.querySelectorAll('.player-card .player-delete-button')[1].click();assert.equal(d.querySelector('#player-delete-dialog').open,true);assert.equal(deleted.length,0);
 d.querySelector('#player-delete-cancel').click();assert.equal(deleted.length,0);
 d.querySelectorAll('.player-card .player-delete-button')[1].click();d.querySelector('#player-delete-confirm').click();await tick();
 assert.deepEqual(deleted,['player-second']);assert.equal(JSON.stringify(w.dijiState.playerPersona),snapshot);assert.equal(w.dijiState.history[0].text,'保留的訊息');
 assert.match(select.selectedOptions[0].textContent,/此對話保存版本/);
 d.querySelector('.player-card .player-delete-button').click();d.querySelector('#player-delete-confirm').click();await tick();
 assert.equal(available.length,0);assert.equal(await w.dijiEnsurePlayerPersona({existing:true}),true);
 assert.equal(await w.dijiEnsurePlayerPersona(),false);const before=chats.length;
 await w.dijiSelectCharacter(w.dijiState.characters[0]);assert.equal(chats.length,before);
 console.log('PASS: persona creation/switching, delete confirmation/cancel, preserved active snapshot/history, last deletion allows existing chat but blocks new chat');w.close();
})().catch(e=>{console.error(e);w.close();process.exitCode=1});

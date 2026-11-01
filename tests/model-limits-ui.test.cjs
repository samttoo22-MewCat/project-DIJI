const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),{JSDOM}=require('jsdom');
const root=path.resolve(__dirname,'..'),dom=new JSDOM(fs.readFileSync(path.join(root,'ui/index.html'),'utf8'),{url:'https://example.test',runScripts:'outside-only'}),w=dom.window;
w.matchMedia=()=>({matches:false,addEventListener(){}});w.HTMLElement.prototype.scrollIntoView=function(){};w.HTMLDialogElement.prototype.showModal=function(){this.open=true};w.HTMLDialogElement.prototype.close=function(){this.open=false};
const character={id:'qa-role',name:'測試角色',premise:'測試',voice:'簡短',profile:{},source:{}};
const draft={generation_id:'gen-quota',revision:0,character:{character_name:'草稿'},style_guide:'簡短',description_for_app:'測試',full_prompt:''};
let status=429,normalCalls=0,trialCalls=0;
const reply=(value,code=200)=>({ok:code<400,status:code,json:async()=>structuredClone(value),text:async()=>JSON.stringify(value)});
w.fetch=async(url,options={})=>{
 if(url==='/api/auth/session')return reply({authenticated:true,auth_required:true,user:{id:'owner'}});
 if(url==='/api/connections/priority')return reply({connected:['openrouter'],priority:['openrouter']});
 if(url==='/api/bootstrap')return reply({characters:[character],flows:[]});
 if(url==='/api/characters')return reply([character]);
 if(url==='/api/jailbreaks')return reply([{review_status:'approved',prompt:'QA',name:'測試',last_updated:'2026-11-01',openrouter_models:['test/model']}]);
 if(url==='/api/conversations')return reply([]);
 if(url==='/api/interactions'){normalCalls++;return reply({detail:'請稍後再試'},status);}
 if(url==='/api/character-generations')return reply([{id:'gen-quota',status:'completed',name:'草稿',updated:new Date().toISOString()}]);
 if(url==='/api/character-generations/gen-quota')return reply({revision:0,data:{draft}});
 if(url==='/api/character-generations/gen-quota/test-interactions'){trialCalls++;return reply({detail:'請稍後再試'},status);}
 return reply([]);
};
w.eval(['message-editor.js','app.js','character-creator.js'].map(f=>fs.readFileSync(path.join(root,'ui',f),'utf8')).join('\n'));
const tick=()=>new Promise(r=>setTimeout(r,25)),d=w.document;
const button=(scope,text)=>[...scope.querySelectorAll('button')].find(el=>el.textContent===text);
(async()=>{
 await tick();await tick();w.dijiState.characters=[character];w.activeCharacter(character);
 w.renderConversation({chat_id:'quota-main',character_id:'qa-role',character_name:'測試角色',chat_mode:'dialog',messages:[]});
 for(const code of [429,413]){
  status=code;d.querySelector('#chat-input').value='保留我的輸入';d.querySelector('#chat-form').dispatchEvent(new w.Event('submit',{cancelable:true}));await tick();await tick();
  assert.equal(d.querySelector('#chat-input').value,'保留我的輸入');assert.equal(d.querySelectorAll('.message.user').length,0);assert.equal(w.dijiState.history.length,0);assert.match(d.querySelector('.toast').textContent,/尚未送出/);
 }
 assert.equal(normalCalls,2);
 status=504;d.querySelector('#chat-input').value='逾時可能已送出';d.querySelector('#chat-form').dispatchEvent(new w.Event('submit',{cancelable:true}));await tick();await tick();
 assert.equal(normalCalls,3);assert.equal(d.querySelectorAll('.message.user').length,1);assert.equal(w.dijiState.history.length,1);
 button(d,'繼續審核草稿').click();await tick();button(d,'測試對話').click();await tick();
 const trial=d.querySelector('.draft-trial');
 for(const code of [429,413]){
  status=code;trial.querySelector('textarea').value='試聊保留輸入';trial.querySelector('.draft-trial-composer').dispatchEvent(new w.Event('submit',{cancelable:true}));await tick();await tick();
  assert.equal(trial.querySelector('textarea').value,'試聊保留輸入');assert.equal(trial.querySelectorAll('.draft-trial-message.user').length,0);
 }
 assert.equal(trialCalls,2);console.log('PASS: 429/413 keep chat/trial input and remove unsent bubbles; 504 preserves sent turn without automatic retry');w.close();
})().catch(e=>{console.error(e);w.close();process.exitCode=1});

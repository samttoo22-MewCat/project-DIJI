const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),{JSDOM}=require('jsdom');
const root=path.resolve(__dirname,'..');
const dom=new JSDOM(fs.readFileSync(path.join(root,'ui/index.html'),'utf8'),{url:'https://example.test/',runScripts:'outside-only'}),w=dom.window;
w.matchMedia=()=>({matches:false,addEventListener(){}});w.HTMLElement.prototype.scrollIntoView=function(){};
w.HTMLDialogElement.prototype.showModal=function(){this.open=true};w.HTMLDialogElement.prototype.close=function(){this.open=false};
const character={id:'edit-role',name:'測試角色',premise:'測試',voice:'簡短',profile:{},source:{}};
const original={chat_id:'original',character_id:'edit-role',character_name:'測試角色',chat_mode:'dialog',revision:'a'.repeat(64),messages:[{sender_type:1,text:'原訊息',timestamp:1},{sender_type:2,text:'原回覆',timestamp:2},{sender_type:1,text:'後續訊息',timestamp:3},{sender_type:2,text:'後續回覆',timestamp:4}]};
const branch={...original,chat_id:'branch',parent_chat_id:'original',state_checkpoint_available:true,messages:[{sender_type:1,text:'修改後訊息',timestamp:5},{sender_type:2,text:'新的角色回覆',timestamp:6}]};
let normalBody,trialBody,trialSource;const revisionRequests=[];
const draft={generation_id:'gen-trial',revision:0,character:{character_name:'草稿角色'},style_guide:'簡短',description_for_app:'測試',full_prompt:''};
const json=value=>({ok:true,status:200,json:async()=>structuredClone(value)});
w.fetch=async(url,options={})=>{
 if(url==='/api/auth/session')return json({authenticated:true,auth_required:true,user:{id:'owner'}});
 if(url==='/api/connections/priority')return json({connected:['openrouter'],priority:['openrouter']});
 if(url==='/api/bootstrap')return json({characters:[character],flows:[]});
 if(url==='/api/characters')return json([character]);
 if(url==='/api/jailbreaks')return json([{review_status:'approved',prompt:'test',name:'測試',last_updated:'2026-11-01',openrouter_models:['test/model']}]);
 if(url==='/api/conversations')return json([]);
 if(url==='/api/conversations/original')return json(original);
 if(url==='/api/conversations/original/edit'){normalBody=JSON.parse(options.body);return json({conversation:branch,response:{text:'新的角色回覆'}});}
 if(url==='/api/character-generations')return json([{id:'gen-trial',status:'completed',name:'草稿角色',updated:new Date().toISOString()}]);
 if(url==='/api/character-generations/gen-trial')return json({revision:0,data:{draft}});
 if(url==='/api/character-generations/gen-trial/revise'){
   const body=JSON.parse(options.body);revisionRequests.push(body);return json({draft:{...draft,revision:revisionRequests.length,style_guide:body.instruction},summary:'已修改風格',changed_fields:[['style_guide']]});
 }
 if(url==='/api/character-generations/gen-trial/test-interactions'){
   const body=JSON.parse(options.body);trialSource={chat_id:body.chat_id,character_id:'gen-trial',revision:'b'.repeat(64),messages:[{sender_type:1,text:body.text},{sender_type:2,text:'原試聊回覆'}]};return json({text:'原試聊回覆'});
 }
 if(url.startsWith('/api/character-generations/gen-trial/test-conversations/'))return json(trialSource);
 if(url==='/api/character-generations/gen-trial/test-interactions/edit'){
   trialBody=JSON.parse(options.body);return json({conversation:{chat_id:'trial-branch',parent_chat_id:trialSource.chat_id,state_checkpoint_available:true,messages:[{sender_type:1,text:trialBody.text},{sender_type:2,text:'新試聊回覆'}]},response:{text:'新試聊回覆'}});
 }
 if(url.startsWith('/api/memories/'))return json([]);
 return json([]);
};
w.eval(['message-editor.js','app.js','character-creator.js'].map(file=>fs.readFileSync(path.join(root,'ui',file),'utf8')).join('\n'));
const tick=()=>new Promise(resolve=>setTimeout(resolve,25));
const button=(scope,text)=>[...scope.querySelectorAll('button')].find(el=>el.textContent===text);
(async()=>{
 await tick();
 w.dijiState.characters=[character];w.activeCharacter(character);w.renderConversation(original);
 const originalCopy=JSON.stringify(original);
 let article=w.document.querySelector('.message.user');article.querySelector('.message-edit-button').click();
 assert.equal(article.querySelector('.message-editor textarea').value,'原訊息');
 button(article,'取消編輯').click();assert.equal(article.querySelector('.message-editor'),null);assert.equal(normalBody,undefined);
 article.querySelector('.message-edit-button').click();article.querySelector('.message-editor textarea').value='修改後訊息';article.querySelector('.message-editor').dispatchEvent(new w.Event('submit',{cancelable:true}));await tick();await tick();
 assert.equal(normalBody.message_index,0);assert.equal(normalBody.expected_revision,original.revision);assert.deepEqual(normalBody.interaction.history,[]);
 assert.equal(normalBody.interaction.message.text,'修改後訊息');assert.equal(JSON.stringify(original),originalCopy);
 assert.match(w.document.querySelector('#conversation').textContent,/新|修改/);
 assert.equal(w.document.querySelectorAll('.message.user').length,1);
 button(w.document.querySelector('.conversation-branch-notice'),'查看編輯前對話').click();await tick();assert.equal(w.document.querySelectorAll('.message.user').length,2);
 button(w.document,'繼續審核草稿').click();await tick();button(w.document,'測試對話').click();await tick();
 const trial=w.document.querySelector('.draft-trial');trial.querySelector('.draft-trial-composer textarea').value='原試聊';trial.querySelector('.draft-trial-composer').dispatchEvent(new w.Event('submit',{cancelable:true}));await tick();
 article=trial.querySelector('.draft-trial-message.user');article.querySelector('.message-edit-button').click();article.querySelector('.message-editor textarea').value='修改後試聊';article.querySelector('.message-editor').dispatchEvent(new w.Event('submit',{cancelable:true}));await tick();await tick();
 assert.equal(trialBody.message_index,0);assert.equal(trialBody.expected_revision,trialSource.revision);assert.equal(trialBody.text,'修改後試聊');assert.match(trial.querySelector('.draft-trial-log').textContent,/新試聊回覆/);
 assert.equal(trialSource.messages[0].text,'原試聊');assert.ok(trial.querySelector('.conversation-branch-notice'));
 button(trial,'返回審核草稿').click();w.showScreen('create-character');await tick();
 const assistant=w.document.querySelector('.creator-ai-assistant');button(assistant,'AI 修改').click();assistant.querySelector('#creator-ai-instruction').value='原本的修改指令';assistant.querySelector('.creator-ai-panel > form').dispatchEvent(new w.Event('submit',{cancelable:true}));await tick();await tick();
 const entry=assistant.querySelector('.creator-ai-log article');entry.querySelector('.message-edit-button').click();entry.querySelector('.message-editor textarea').value='編輯後的修改指令';entry.querySelector('.message-editor').dispatchEvent(new w.Event('submit',{cancelable:true}));await tick();await tick();
 assert.equal(revisionRequests.length,2);assert.equal(revisionRequests[1].base_revision,0);assert.equal(revisionRequests[1].revision,1);assert.equal(revisionRequests[1].instruction,'編輯後的修改指令');
 const standalone=w.document.createElement('article');w.document.body.append(standalone);
 w.dijiAttachMessageEditor(standalone,{text:'原文',isBusy:()=>false,onSave:async()=>{throw Error('測試失敗');}});standalone.querySelector('button').click();standalone.querySelector('textarea').value='保留的修改';standalone.querySelector('form').dispatchEvent(new w.Event('submit',{cancelable:true}));await tick();
 assert.equal(standalone.querySelector('textarea').value,'保留的修改');assert.match(standalone.querySelector('[role=status]').textContent,/測試失敗/);
 console.log('PASS: chat/trial editing branches, original accessible, assistant instruction base version, cancel no request, failed edit retained');w.close();
})().catch(error=>{console.error(error);w.close();process.exitCode=1});

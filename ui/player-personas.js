(() => {
  const list=document.querySelector('#player-persona-list'),form=document.querySelector('#player-persona-form');
  const select=document.querySelector('#chat-player-select'),status=document.querySelector('#player-status');
  let records=[],editing=null,loading=0,switching=false;
  const busy=()=>switching || document.querySelector('#chat-form').getAttribute('aria-busy')==='true';
  function summary(persona) {
    return persona ? [persona.name,persona.sex,persona.age ? `${persona.age} 歲` : '',persona.description].filter(Boolean).join(' · ') : '尚未設定玩家人設。';
  }
  function render() {
    const current=state.playerPersonaId || '';
    select.replaceChildren(new Option('使用者 · 預設設定',''));
    for(const record of records) select.add(new Option(`${record.label} · ${record.name}`,record.id));
    if(current && !records.some(record=>record.id===current)) select.add(new Option(`${state.playerPersona?.name || '玩家'} · 此對話保存版本`,current));
    select.value=current;select.disabled=busy();
    document.querySelector('#chat-player-summary').textContent=summary(state.playerPersona);
    list.replaceChildren();
    for(const record of records) {
      const card=document.createElement('article');card.className='player-card';card.classList.toggle('selected',current===record.id);
      const heading=document.createElement('h2');heading.textContent=record.label;
      const scope=document.createElement('small');scope.textContent=current===record.id ? '已選用 · 對話保留開始時的版本' : '私人設定 · 僅自己可見';
      const copy=document.createElement('p');copy.textContent=summary(record);
      const actions=document.createElement('div');actions.className='player-actions';
      const use=document.createElement('button');use.type='button';use.className='primary-button';use.textContent='使用此設定';use.disabled=busy();use.addEventListener('click',()=>choose(record.id));
      const edit=document.createElement('button');edit.type='button';edit.className='ghost-button';edit.textContent='編輯';edit.addEventListener('click',()=>openForm(record));
      actions.append(use,edit);card.append(heading,scope,copy,actions);list.append(card);
    }
    if(!records.length) {const empty=document.createElement('p');empty.textContent='還沒有玩家設定。新增一份人設，決定角色眼中的你。';list.append(empty);}
  }
  async function load() {
    const epoch=++loading;
    try {
      const response=await fetch('/api/player-personas',{cache:'no-store'});
      if(!response.ok)throw new Error('無法載入玩家設定，請稍後重試。');
      const data=await response.json();if(epoch!==loading)return;
      records=data;status.textContent='';render();
    }catch(error){if(epoch===loading)status.textContent=error.message;}
  }
  function openForm(record=null) {
    editing=record?.id || null;form.reset();
    for(const key of ['label','name','sex','age','description'])form.elements.namedItem(key).value=record?.[key] || '';
    document.querySelector('#player-form-title').textContent=editing ? '編輯玩家設定' : '新增玩家設定';
    form.hidden=false;form.elements.namedItem('label').focus();
  }
  async function choose(id) {
    if(busy()){render();showToast('請等候這一回合完成後再切換玩家設定。');return;}
    const selected=records.find(record=>record.id===id);
    switching=true;setComposerBusy(true);render();
    try {
      const character=selectedCharacter();
      if(character && state.chatId!=='preview') {
        if(!await startConversation(character,id || null))return;
        setChatReady(true);showScreen('chat');
        showToast('已使用選擇的玩家設定開啟新對話，原對話仍保留。');
      } else {
        state.playerPersonaId=id || null;
        state.playerPersona=selected ? {name:selected.name,sex:selected.sex,age:selected.age,description:selected.description,chat_mode:state.chatMode} : null;
        showToast('已選用玩家設定，請選擇角色開始聊天。');
      }
    }catch(error){showToast(`設定未切換：${error.message}`);}
    finally{switching=false;setComposerBusy(false);render();}
  }
  select.addEventListener('change',()=>{if(select.value!==(state.playerPersonaId || ''))choose(select.value);});
  document.querySelector('#player-new').addEventListener('click',()=>openForm());
  document.querySelector('#player-cancel').addEventListener('click',()=>{form.hidden=true;});
  form.addEventListener('submit',async event=>{
    event.preventDefault();if(!form.reportValidity())return;
    const submit=form.querySelector('[type=submit]');submit.disabled=true;
    const owner=authenticatedUser?.id;
    const value=Object.fromEntries(new FormData(form));
    try {
      const response=await fetch(editing ? `/api/player-personas/${encodeURIComponent(editing)}` : '/api/player-personas',{method:editing ? 'PUT' : 'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)});
      if(!response.ok)throw new Error('儲存失敗，請確認內容後再試。');
      if(owner!==authenticatedUser?.id || !workspaceAvailable)return;
      form.hidden=true;await load();status.textContent='已儲存。選擇「使用此設定」即可開始；已開始的對話不會變更。';showToast('玩家設定已儲存');
    }catch(error){status.textContent=error.message;}
    finally{submit.disabled=false;}
  });
  window.addEventListener('diji-workspace-ready',load);
  window.addEventListener('diji-persona-changed',render);
  window.addEventListener('diji-composer-busy',render);
  window.addEventListener('diji-persona-cleared',()=>{loading++;records=[];form.reset();form.hidden=true;status.textContent='';render();});
  window.addEventListener('diji-screen-changed',event=>{if(event.detail.name==='player-personas')load();});
})();

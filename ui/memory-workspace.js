(() => {
  const el = id => document.getElementById(id);
  const node = (tag, className, text) => { const element = document.createElement(tag); if (className) element.className = className; if (text !== undefined) element.textContent = text; return element; };
  let groups = [], current = null, records = [], filter = 'all', epoch = 0;
  const stamp = value => new Date(value).toLocaleString('zh-TW', {month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false});
  const status = memory => memory.error ? 'error' : memory.extraction_status === 'fallback' ? 'pending' : memory.extraction_status === 'extracted' || Object.keys(memory.keywords || {}).length || memory.key_points?.length ? 'organized' : 'pending';
  const labels = {organized:'已整理', pending:'待整理', error:'抽取異常'};

  function renderRoles() {
    const query = el('memory-role-search').value.trim().toLocaleLowerCase();
    const matches = groups.filter(group => group.name.toLocaleLowerCase().includes(query));
    el('memory-role-grid').replaceChildren(...matches.map(group => {
      const card = node('button', 'character-library-card memory-role-card'); card.type = 'button'; card.dataset.characterId = group.id;
      const character = window.dijiState.characters.find(item => item.id === group.id);
      if (character?.source?.visibility === 'private') card.classList.add('personal-character');
      const avatar = node('span', 'character-library-initial', group.name.slice(0,1)); avatar.setAttribute('aria-hidden','true');
      const copy = node('span','character-library-copy'); copy.append(node('strong','',group.name), node('small','',`${group.conversations.length} 段已聊對話`), node('small','memory-role-date',`最近互動 ${stamp(group.conversations[0].updated_at)}`));
      const arrow = node('span','character-library-arrow','→'); arrow.setAttribute('aria-hidden','true');
      card.append(avatar,copy,arrow); card.addEventListener('click',() => enterRole(group)); return card;
    }));
    el('memory-role-count').textContent = `${matches.length} 位聊過的角色`;
    el('memory-hub-empty').hidden = matches.length > 0;
    el('memory-hub-empty').querySelector('h2').textContent = groups.length ? '找不到相符角色' : '故事還沒開始';
  }
  function showHub(focus = false) {
    epoch++; current = null; records = [];
    el('memory-hub').closest('.memory-shell').classList.remove('memory-show-detail');
    el('memory-hub').hidden = false; el('memory-detail').hidden = true;
    el('memory-status').textContent = '';
    renderRoles();
    if (focus) el('memory-role-search').focus();
  }
  function enterRole(group, chatId) {
    current = group;
    el('memory-hub').closest('.memory-shell').classList.add('memory-show-detail');
    el('memory-hub').hidden = true; el('memory-detail').hidden = false;
    el('memory-character-title').textContent = group.name;
    el('memory-conversation').replaceChildren(...group.conversations.map((conversation,index) => new Option(`${stamp(conversation.updated_at)} · ${conversation.message_count} 則訊息 · 對話 ${index+1}`,conversation.chat_id)));
    if (chatId) el('memory-conversation').value = chatId;
    el('memory-search').value = ''; filter = 'all';
    loadRecords(); el('memory-back').focus();
  }
  async function loadRecords() {
    const ticket = ++epoch;
    el('memory-list').replaceChildren(); records = []; renderRecords();
    el('memory-empty').hidden = true;
    el('memory-status').textContent = '正在讀取這段對話的記憶…';
    el('memory-list').setAttribute('aria-busy','true');
    try {
      const response = await fetch(`/api/memories/${encodeURIComponent(el('memory-conversation').value)}/entries`, {cache:'no-store'});
      if (!response.ok) throw new Error();
      const data = await response.json();
      if (ticket !== epoch) return;
      records = data.slice().sort((a,b) => b.timestamp.localeCompare(a.timestamp));
      el('memory-context').textContent = `記憶所屬對話：${current.name} · 每段對話分開保存`;
      el('memory-status').textContent = ''; renderRecords();
      return true;
    } catch {
      if (ticket !== epoch) return;
      el('memory-status').textContent = '記憶讀取失敗。請重新選擇對話，或稍後再試。';
      return false;
    } finally { if (ticket === epoch) el('memory-list').setAttribute('aria-busy','false'); }
  }
  function memoryCard(memory) {
    const kind = status(memory), article = node('article',`memory-entry memory-entry-${kind}`);
    const meta = node('div','memory-entry-meta');
    const time = node('time','',memory.timestamp); time.dateTime = memory.timestamp.replace(' ','T');
    meta.append(node('span','memory-type',memory.type === 'event' ? '事件' : memory.type),node('span',`memory-state memory-state-${kind}`,labels[kind]),time);
    article.append(meta,node('h3','',memory.summary));
    const tags = node('div','memory-tags');
    Object.entries(memory.keywords || {}).forEach(([category,value]) => {
      if (!value) return;
      const tag = node('span','memory-tag'); tag.append(node('span','',category),document.createTextNode(value)); tags.append(tag);
    });
    if (tags.children.length) article.append(tags);
    if (kind === 'pending') article.append(node('p','memory-caution',memory.extraction_status === 'fallback' ? '這是抽取未完成時保存的對話備份，尚無整理後的關鍵字。' : '舊紀錄未標註抽取狀態，且沒有關鍵字或重點；保留內容供你核對。'));
    if (kind === 'error') article.append(node('p','memory-caution','這次記憶抽取未完成。可返回原對話確認內容。'));
    const details = node('details','memory-source'); details.append(node('summary','','查看原始內容與重點'));
    if (memory.key_points?.length) { const list=node('ul',''); memory.key_points.forEach(point=>list.append(node('li','',point))); details.append(node('h4','','關鍵重點'),list); }
    if (memory.user_message) details.append(node('h4','','使用者訊息'),node('p','',memory.user_message));
    if (memory.character_response_summary) details.append(node('h4','','角色回覆摘要'),node('p','',memory.character_response_summary));
    if (details.children.length > 1) article.append(details);
    if (memory.manually_edited) meta.append(node('span','memory-type','手動編輯'));
    const actions = node('div','memory-entry-actions');
    for (const [mode,label] of [['edit','編輯記憶'],['delete','刪除記憶']]) {
      const button = node('button',mode === 'delete' ? 'danger-button' : 'ghost-button',label); button.type='button';
      button.addEventListener('click',()=>window.dijiMemoryEditor.open(mode,memory,el('memory-conversation').value,async()=>{const loaded=await loadRecords();el('memory-status').textContent=loaded?(mode==='edit'?'記憶已儲存，後續回覆將使用更新內容。':'已刪除這筆記憶，原始對話仍保留。'):'操作已完成，但讀取最新記憶失敗。請重新開啟記憶頁。';el('memory-back').focus();}));
      actions.append(button);
    }
    article.append(actions);
    return article;
  }
  function renderRecords() {
    const query = el('memory-search').value.trim().toLocaleLowerCase();
    const matches = records.filter(memory => (filter === 'all' || status(memory) === filter) && [memory.summary,memory.user_message,...(memory.key_points || []),...Object.values(memory.keywords || {})].join(' ').toLocaleLowerCase().includes(query));
    el('memory-total').textContent = records.length;
    el('memory-organized').textContent = records.filter(memory=>status(memory)==='organized').length;
    el('memory-pending').textContent = records.filter(memory=>status(memory)==='pending').length;
    el('memory-list').replaceChildren(...matches.map(memoryCard));
    el('memory-empty').hidden = matches.length > 0;
    el('memory-results').textContent = `顯示 ${matches.length} / ${records.length} 筆 · 最近 100 筆內 · 由新到舊`;
    el('memory-filters').querySelectorAll('button').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.memoryFilter===filter)));
  }
  async function open(chatId = null) {
    const ticket = ++epoch;
    groups = []; records = []; current = null;
    el('memory-hub').closest('.memory-shell').classList.remove('memory-show-detail');
    el('memory-hub').hidden = false; el('memory-detail').hidden = true;
    el('memory-role-grid').replaceChildren(); el('memory-hub-empty').hidden = true;
    el('memory-status').textContent = '正在整理你聊過的角色…';
    try {
      const response = await fetch('/api/conversations',{cache:'no-store'});
      if (!response.ok) throw new Error();
      const conversations = await response.json(); if (ticket !== epoch) return;
      const map = new Map();
      conversations.filter(item=>item.message_count>0).sort((a,b)=>b.updated_at-a.updated_at).forEach(item=> {
        if (!map.has(item.character_id)) map.set(item.character_id,{id:item.character_id,name:item.character_name,conversations:[]});
        map.get(item.character_id).conversations.push(item);
      });
      groups = [...map.values()]; el('memory-role-search').value = ''; showHub();
      const group = groups.find(group=>group.conversations.some(item=>item.chat_id===chatId));
      if (group) enterRole(group,chatId);
    } catch { if(ticket===epoch) el('memory-status').textContent = '無法讀取已聊角色。請確認登入狀態，再重新開啟記憶頁。'; }
  }
  el('memory-back').addEventListener('click',()=>showHub(true));
  el('memory-choose-role').addEventListener('click',()=>document.querySelector('.rail-button[data-view="characters"]').click());
  el('memory-role-search').addEventListener('input',renderRoles);
  el('memory-conversation').addEventListener('change',loadRecords);
  el('memory-search').addEventListener('input',renderRecords);
  el('memory-filters').addEventListener('click',event=>{const button=event.target.closest('[data-memory-filter]');if(button){filter=button.dataset.memoryFilter;renderRecords();}});
  el('memory-clear-search').addEventListener('click',()=>{el('memory-search').value='';filter='all';renderRecords();el('memory-search').focus();});
  document.querySelectorAll('[data-auth-logout]').forEach(button=>button.addEventListener('click',()=>{epoch++;groups=[];records=[];current=null;el('memory-role-grid').replaceChildren();el('memory-list').replaceChildren();}));
  window.dijiMemory = {open};
})();

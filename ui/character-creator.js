(() => {
  const target = document.querySelector('[data-screen="characters"]');
  if (!target) return;
  target.replaceChildren(document.querySelector("#character-creator").content.cloneNode(true));
  const creationPage = document.querySelector('[data-screen="create-character"]');
  const creationPanel = target.querySelector("#character-creator-panel");
  creationPanel.hidden = false;
  creationPanel.classList.add("creator");
  creationPage.append(creationPanel);
  const createCard = target.querySelector("#open-character-creator");
  createCard.className = "character-library-card character-create-card";
  createCard.innerHTML = '<span class="character-library-initial" aria-hidden="true">＋</span><span class="character-library-copy"><strong>建立角色</strong><small>創造屬於你的角色</small></span><span class="character-library-arrow" aria-hidden="true">→</span>';
  const grid = target.querySelector("#character-library-grid");
  const status = target.querySelector("#character-library-status");
  const search = target.querySelector("#character-library-search");
  const panel = creationPanel;
  const form = panel.querySelector("#creator-brief");
  const creatorStatus = panel.querySelector("#creator-status");
  const result = panel.querySelector("#creator-result");
  const model = panel.querySelector("#creator-model");
  let draft = null;
  let draftId = null;
  let saving = false;
  let generating = false;
  let savedCharacter = null;
  let briefKey = null;
  let syncTimer = null;
  let syncQueue = Promise.resolve();
  let draftDirty = false;
  let editVersion = 0;
  let creatorEpoch = 0;
  const historyPanel = document.createElement('div');
  historyPanel.className = 'creator-draft-history'; historyPanel.hidden = true;
  form.before(historyPanel);
  function storageStatus(message) {
    const notice = result.querySelector('.creator-draft-warning');
    if (notice) notice.textContent = message;
  }
  function syncDraft() {
    clearTimeout(syncTimer); syncTimer = null;
    if (!draft?.generation_id || savedCharacter || !draftDirty) return syncQueue;
    const current = draft; const version = editVersion;
    const snapshot = JSON.parse(JSON.stringify(current));
    syncQueue = syncQueue.then(async () => {
      if (draft !== current || savedCharacter) return;
      snapshot.revision = current.revision;
      try {
        const response = await fetch(`/api/character-generations/${current.generation_id}/draft`, {method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(snapshot)});
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const stored = await response.json();
        if (draft !== current) return;
        current.revision = stored.revision;
        if (editVersion === version) draftDirty = false;
        storageStatus(draftDirty ? '正在同步修改至伺服器…' : '草稿已保存至伺服器。按下儲存角色才會加入角色庫。');
      } catch {
        storageStatus('草稿修改尚未同步，請保留此頁並重試，或直接儲存角色。');
      }
    });
    return syncQueue;
  }
  async function loadDraftHistory() {
    if (!workspaceAvailable) return;
    const epoch = creatorEpoch;
    try {
      const response = await fetch('/api/character-generations', {cache:'no-store'});
      if (!response.ok) throw new Error('history unavailable');
      const rows = (await response.json()).filter(row => row.status === 'completed' && !row.saved_character_id);
      if (epoch !== creatorEpoch) return;
      historyPanel.replaceChildren(); historyPanel.hidden = !rows.length;
      if (!rows.length) return;
      const label = document.createElement('label'); label.textContent = '伺服器保存的未完成草稿';
      const select = document.createElement('select');
      select.append(...rows.map(row => new Option(`${row.name} · ${new Date(row.updated).toLocaleString('zh-TW')}`,row.id)));
      label.append(select);
      const restore = document.createElement('button'); restore.type='button'; restore.className='ghost-button'; restore.textContent='繼續審核草稿';
      restore.addEventListener('click', async () => {
        if (generating || saving) return;
        await syncDraft();
        if (draftDirty && !window.confirm('目前修改尚未同步，仍要切換草稿嗎？')) return;
        restore.disabled=true;
        try {
          const response = await fetch(`/api/character-generations/${select.value}`,{cache:'no-store'});
          if (!response.ok) throw new Error('無法讀取草稿');
          const record = await response.json();
          if (epoch !== creatorEpoch) return;
          if (!record.data.draft || record.data.saved_character_id) throw new Error('此草稿已保存或無法恢復');
          draft={...record.data.draft,revision:record.revision}; draftId=draft.generation_id; savedCharacter=null; draftDirty=false;
          form.hidden=false; renderDraft(); setStep(1); creatorStatus.textContent='已恢復伺服器草稿，不會重新呼叫模型。';
        } catch(error) { creatorStatus.textContent=error.message; }
        finally { restore.disabled=false; }
      });
      historyPanel.append(label,restore);
    } catch { if (epoch !== creatorEpoch) return; historyPanel.hidden=false; historyPanel.textContent='暫時無法讀取伺服器草稿，請重新整理後重試。'; }
  }
  function persistBrief() {
    if (savedCharacter || !briefKey) return;
    try { sessionStorage.setItem(briefKey, JSON.stringify({keywords: panel.querySelector('#creator-keywords').value, online: panel.querySelector('#creator-search').checked, adult: panel.querySelector('#creator-adult').checked, model: model.value})); } catch {}
  }
  let restoredBrief = null;
  function restoreBrief() {
    const accountId = typeof authenticatedUser !== 'undefined' ? authenticatedUser?.id : null;
    briefKey = `diji-creator-brief:${accountId || 'local-user'}`;
    restoredBrief = null;
    form.reset();
    try { restoredBrief = JSON.parse(sessionStorage.getItem(briefKey) || 'null'); } catch {}
    if (restoredBrief) {
      panel.querySelector('#creator-keywords').value = restoredBrief.keywords || '';
      panel.querySelector('#creator-search').checked = Boolean(restoredBrief.online);
      panel.querySelector('#creator-adult').checked = Boolean(restoredBrief.adult);
    }
  }
  form.addEventListener('input', persistBrief);
  form.addEventListener('change', persistBrief);
  window.addEventListener('beforeunload', event => {
    persistBrief();
    if (generating || draftDirty || (draft && !draft.generation_id && !savedCharacter)) { event.preventDefault(); event.returnValue = ''; }
  });
  function setStep(index) {
    panel.querySelectorAll('.creator-steps li').forEach((step,i) => {
      step.classList.toggle('active', i === index);
      if (i === index) step.setAttribute('aria-current', 'step'); else step.removeAttribute('aria-current');
    });
  }

  function filteredCharacters() {
    const query = search.value.trim().toLocaleLowerCase();
    return window.dijiState.characters.filter((character) => !query || [character.name, character.premise, character.voice, character.style_guide].join(" ").toLocaleLowerCase().includes(query));
  }
  window.dijiRenderCharacterLibrary = () => {
    const characters = filteredCharacters();
    grid.replaceChildren(...characters.map((character) => {
      const card = document.createElement("button");
      card.type = "button";
      card.dataset.characterId = character.id;
      card.className = "character-library-card";
      if (character.source?.visibility === "private") card.classList.add("personal-character");
      card.innerHTML = '<span class="character-library-initial"></span><span class="character-library-copy"><strong></strong><small></small></span><span class="character-library-arrow" aria-hidden="true">→</span>';
      card.querySelector(".character-library-initial").textContent = character.name.slice(0, 1);
      card.querySelector("strong").textContent = character.name;
      card.querySelector("small").textContent = character.premise;
      if (character.source?.visibility === "private") {
        const badge = document.createElement("em");
        badge.textContent = "我的角色 · 僅自己可見";
        card.querySelector(".character-library-copy").append(badge);
      }
      card.addEventListener("click", () => window.dijiSelectCharacter(character));
      return card;
    }));
    grid.append(createCard);
    status.textContent = characters.length ? `${characters.length} 位可選角色` : "沒有符合搜尋的角色。";
  };
  search.addEventListener("input", window.dijiRenderCharacterLibrary);
  createCard.addEventListener("click", () => {
    document.querySelector('[data-view="create-character"]').click();
    panel.querySelector("#creator-keywords").focus();
  });

  async function loadModels() {
    if (!workspaceAvailable) return;
    try {
      const response = await fetch("/api/jailbreaks");
      if (!response.ok) throw new Error("jailbreak unavailable");
      const available = (await response.json()).filter((item) => item.review_status === "approved" && item.prompt).sort((a, b) => b.last_updated.localeCompare(a.last_updated));
      model.replaceChildren(...available.flatMap((item) => item.openrouter_models.map((id) => new Option(`${id} · 越獄：${item.name} · ${item.last_updated}`, id))));
      model.disabled = !model.options.length;
      if ([...model.options].some(option => option.value === 'deepseek/deepseek-v4.1-flash')) model.value = 'deepseek/deepseek-v4.1-flash';
      if (restoredBrief?.model && [...model.options].some(option => option.value === restoredBrief.model)) model.value = restoredBrief.model;
      creatorStatus.textContent = model.options.length ? `已載入 ${model.options.length} 個有已核准越獄的模型；最新項目優先。` : "尚無已核准的越獄，請先到越獄工作台完成編輯與核准。";
    } catch { creatorStatus.textContent = "無法讀取可用模型。"; }
  }
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (generating) return;
    const button = form.querySelector("button");
    const keywords = panel.querySelector("#creator-keywords").value.trim();
    if (!keywords || model.disabled) return;
    if (draft && !savedCharacter && !window.confirm('重新生成會取代尚未儲存的草稿，確定繼續嗎？')) return;
    generating = true;
    button.disabled = true; button.textContent = "生成中…";
    await syncDraft();
    form.setAttribute('aria-busy', 'true');
    creatorStatus.textContent = `正以 ${model.value} 與對應越獄生成草稿…`;
    const started = Date.now();
    const waiting = window.setInterval(() => { creatorStatus.textContent = `正在生成完整人設、說話風格與介紹，已等待 ${Math.floor((Date.now()-started)/1000)} 秒。完成草稿會先保存伺服器，確認後才加入角色庫。`; },1000);
    try {
      const response = await fetch("/api/characters/generate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ keywords, model: model.value, enable_search: panel.querySelector("#creator-search").checked, is_nsfw: panel.querySelector("#creator-adult").checked }) });
      if (!response.ok) {
        let errorBody; try { errorBody = await response.json(); } catch {}
        throw new Error(typeof errorBody?.detail === 'string' ? errorBody.detail : `角色生成未完成（HTTP ${response.status}）。請稍後再試。`);
      }
      let generated; try { generated = await response.json(); } catch { throw new Error('草稿回傳格式無法讀取，請稍後重試。'); }
      if (!generated.character?.character_name) throw new Error('草稿缺少角色名稱，請稍後重試。');
      draft = generated; savedCharacter = null; draftDirty=false;
      draftId = generated.generation_id || `draft-${crypto.randomUUID()}`;
      loadDraftHistory();
      renderDraft(); setStep(1); creatorStatus.textContent = "草稿已完成。你可以修改人設與說話風格，再儲存。";
      result.scrollIntoView({block:'start', behavior:'auto'});
    } catch (error) { creatorStatus.textContent = `生成失敗：${error.message}`; }
    finally { window.clearInterval(waiting); generating = false; button.disabled = false; button.textContent = "生成角色草稿"; form.setAttribute('aria-busy', 'false'); }
  });
  function renderDraft() {
    result.hidden = false; result.replaceChildren();
    const title = document.createElement('h2'); title.textContent = '審核你的角色';
    const draftWarning = document.createElement('p'); draftWarning.className = 'creator-draft-warning'; draftWarning.setAttribute('role','status'); draftWarning.textContent = draft.generation_id ? '草稿已保存至伺服器。修改會自動同步；按下儲存角色才會加入角色庫。' : '草稿尚未儲存，請先審核並儲存。';
    const review = document.createElement('form'); review.className = 'character-review';
    review.addEventListener('input',()=>{draftDirty=true;editVersion++;storageStatus('正在同步修改至伺服器…');clearTimeout(syncTimer);syncTimer=setTimeout(syncDraft,700);});
    const labels = {character_name:'角色名稱',basic_info:'基本資料',age:'年齡',gender:'性別',occupation:'職業',personality:'個性',backstory:'背景故事',language_style:'說話方式',appearance:'外貌',motivations:'動機與目標',relationships:'人際關係',core_theme:'角色主題',abilities:'能力',weaknesses:'弱點',interaction_context:'互動情境',cultural_details:'文化背景',psychological_evolution:'關係發展',behavioral_boundaries:'互動界線',evolution_requirements:'發展條件',core_traits:'核心特質'};
    function field(label, value, update, name = '') {
      const wrapper = document.createElement('label'); wrapper.textContent = label;
      const input = document.createElement(name === 'character_name' ? 'input' : 'textarea');
      input.value = value; input.rows = 3;
      if (name === 'character_name') { input.required = true; input.maxLength = 80; }
      input.addEventListener('input', () => update(input.value));
      wrapper.append(input); return wrapper;
    }
    function profileFields(object, parent) {
      for (const [key,value] of Object.entries(object)) {
        const label = labels[key] || key.replaceAll('_',' ');
        if (value && typeof value === 'object' && !Array.isArray(value)) {
          const details = document.createElement('details'); const summary = document.createElement('summary'); summary.textContent = label;
          details.append(summary); profileFields(value, details); parent.append(details);
        } else if (typeof value === 'string' || typeof value === 'number') {
          parent.append(field(label, String(value), text => { object[key] = typeof value === 'number' ? (Number.isFinite(Number(text)) ? Number(text) : value) : text; }, key));
        } else if (Array.isArray(value) && value.every(item => typeof item === 'string')) {
          parent.append(field(`${label}（每行一項）`, value.join('\n'), text => { object[key] = text.split('\n').filter(line => line.trim()); }));
        }
      }
    }
    const summaryField = field('角色簡介', draft.description_for_app || draft.brief_description || '', text => { draft.description_for_app = text; });
    summaryField.querySelector('textarea').required = true; summaryField.querySelector('textarea').maxLength = 2000;
    review.append(summaryField); profileFields(draft.character, review);
    review.append(field('說話風格指南', draft.style_guide || '', text => { draft.style_guide = text; }));
    const presentation = document.createElement('details'); const presentationTitle = document.createElement('summary'); presentationTitle.textContent = '更多顯示資訊與嗜好'; presentation.append(presentationTitle);
    for (const [key,label] of [['brief_description','一句話介紹'],['category','分類'],['hobbies','嗜好與興趣']]) presentation.append(field(label,draft[key] || '',text=>{draft[key]=text;}));
    const advanced = document.createElement('details'); const heading = document.createElement('summary'); heading.textContent = '進階檢視：完整角色 JSON';
    const json = document.createElement('pre'); json.textContent = JSON.stringify(draft.character,null,2);
    advanced.addEventListener('toggle', () => { json.textContent = JSON.stringify(draft.character,null,2); }); advanced.append(heading,json);
    const save = document.createElement('button'); save.type = 'submit'; save.className = 'primary-button'; save.textContent = '儲存角色 · 僅自己可見';
    review.addEventListener('submit', event => { event.preventDefault(); saveDraft(save); });
    review.append(presentation,advanced,save); result.append(title,draftWarning,review);
  }
  async function saveDraft(button) {
    if (saving) return;
    saving = true; button.disabled = true; button.textContent = '正在儲存…';
    await syncDraft();
    const id = draftId;
    const character = { id, name: draft.character.character_name, premise: draft.description_for_app || draft.brief_description || '', voice: (draft.style_guide || '依角色設定互動。').slice(0,2000), profile: draft.character, style_guide: draft.style_guide || '', generation_metadata: {brief_description:draft.brief_description || '',category:draft.category || '',hobbies:draft.hobbies || ''}, full_prompt: '', source: { generated_file: 'DIJI character creator', ...(draft.generation_id ? {generation_id:draft.generation_id} : {}) } };
    try {
      const response = await fetch(`/api/characters/${id}`, {method:'PUT', headers:{'Content-Type':'application/json'},body:JSON.stringify(character)});
      const saved = await response.json();
      if (!response.ok) throw new Error(typeof saved.detail === 'string' ? saved.detail : '請檢查人設欄位內容後重試');
      savedCharacter = saved;
      draftDirty=false; loadDraftHistory();
      window.dijiState.characters = window.dijiState.characters.filter(item => item.id !== saved.id).concat(saved);
      window.dijiRenderCharacterLibrary(); setStep(2);
      if (typeof renderSidebarCharacters === 'function') renderSidebarCharacters();
      form.hidden = true;
      try { sessionStorage.removeItem(briefKey); } catch {}
      result.replaceChildren();
      const title = document.createElement('h2'); title.textContent = '角色已儲存';
      const note = document.createElement('p'); note.textContent = `「${saved.name}」已保存到你的帳號，僅自己可見。`;
      const chat = document.createElement('button'); chat.className = 'primary-button'; chat.textContent = '開始聊天'; chat.addEventListener('click', () => window.dijiSelectCharacter(saved));
      const library = document.createElement('button'); library.className = 'ghost-button'; library.textContent = '回到角色庫'; library.addEventListener('click', () => {search.value='';window.dijiRenderCharacterLibrary();document.querySelector('.rail-button[data-view="characters"]').click();grid.querySelector(`[data-character-id="${saved.id}"]`)?.scrollIntoView({block:'nearest'});});
      const another = document.createElement('button'); another.className='ghost-button'; another.textContent='建立另一位角色'; another.addEventListener('click',()=>{const selectedModel=model.value;savedCharacter=null;draft=null;draftId=null;form.reset();model.value=selectedModel;form.hidden=false;result.hidden=true;result.replaceChildren();setStep(0);creatorStatus.textContent='描述新的角色概念，再開始生成。';persistBrief();panel.querySelector('#creator-keywords').focus();});
      result.append(title,note,chat,library,another); creatorStatus.textContent = '儲存完成。';
      result.scrollIntoView({block:'start'});
    } catch (error) { creatorStatus.textContent = `儲存失敗：${error.message}。修改內容仍保留，可再次儲存。`; }
    finally { saving = false; button.disabled = false; button.textContent = '儲存角色 · 僅自己可見'; }
  }
  async function refreshCharacterLibrary() {
    if (!workspaceAvailable) return;
    try {
      const response = await fetch("/api/characters");
      if (!response.ok) throw new Error("catalog unavailable");
      window.dijiState.characters = await response.json();
      window.dijiRenderCharacterLibrary();
    } catch (error) {
      status.textContent = `角色庫無法載入：${error.message}`;
    }
  }
  function initializeCreator() { creatorEpoch++; restoreBrief(); loadModels(); refreshCharacterLibrary(); loadDraftHistory(); }
  window.addEventListener('diji-workspace-ready', initializeCreator);
  if (workspaceAvailable) initializeCreator();
  document.querySelectorAll('[data-auth-logout]').forEach(button=>button.addEventListener('click',()=>{creatorEpoch++;clearTimeout(syncTimer);draftDirty=false;historyPanel.hidden=true;historyPanel.replaceChildren();briefKey=null;draft=null;savedCharacter=null;form.reset();form.hidden=false;result.replaceChildren();result.hidden=true;setStep(0);}));
})();

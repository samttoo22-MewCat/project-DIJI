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
  let revising = false;
  let restoringVersion = false;
  const assistantMedia = window.matchMedia?.('(min-width:1100px)');
  let assistantOpen = assistantMedia?.matches || false;
  let assistantDraftId = null;
  const assistant = document.createElement('aside'); assistant.className='creator-ai-assistant'; assistant.hidden=true; assistant.setAttribute('aria-label','AI 角色修改助手');
  assistant.innerHTML='<button type="button" class="creator-ai-launcher" aria-controls="creator-ai-panel" aria-expanded="false"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5h14v11H9l-4 4V5Z"/><path d="M9 9h6M9 12h4"/></svg><span>AI 修改</span></button><section id="creator-ai-panel" class="creator-ai-panel" aria-labelledby="creator-ai-title"><header><h2 id="creator-ai-title">AI 修改助手</h2><button type="button" class="creator-ai-close" aria-label="收起 AI 修改助手">×</button></header><p>直接說想改哪裡，AI 會更新草稿並保存至伺服器；確認儲存角色後才會加入角色庫。</p><div class="creator-ai-log" role="log" aria-label="角色修改紀錄"></div><form><label for="creator-ai-instruction">想怎麼修改角色？</label><textarea id="creator-ai-instruction" rows="4" maxlength="4000" required placeholder="例如：個性更幽默，保留背景，說話不要太正式。"></textarea><p class="creator-ai-model"></p><button type="submit" class="primary-button">交給 AI 修改</button></form><p class="creator-ai-status" role="status">使用你選擇的模型及自備額度。</p></section>';
  document.body.append(assistant);
  const assistantLauncher=assistant.querySelector('.creator-ai-launcher'), assistantPanel=assistant.querySelector('.creator-ai-panel'), assistantInput=assistant.querySelector('textarea'), assistantLog=assistant.querySelector('.creator-ai-log'), assistantStatus=assistant.querySelector('.creator-ai-status');
  const assistantForm=assistantPanel.querySelector('form');
  assistantPanel.querySelector('header + p').textContent='AI 會更新並保存草稿；儲存角色後才加入角色庫。';
  const assistantHistory=document.createElement('details'); assistantHistory.className='creator-ai-history'; assistantHistory.open=assistantMedia?.matches || false;
  const historyTitle=document.createElement('summary'); historyTitle.textContent='本次修改紀錄'; assistantLog.replaceWith(assistantHistory); assistantHistory.append(historyTitle,assistantLog);
  function updateAssistant() {
    const visible=Boolean(draft?.generation_id && !savedCharacter && !generating && !restoringVersion && workspaceAvailable && creationPage.classList.contains('active') && !creationPage.classList.contains('provider-locked') && result.querySelector('.character-review') && !result.querySelector('.character-review').hidden);
    assistant.hidden=!visible; assistantPanel.hidden=!assistantOpen; assistantLauncher.hidden=assistantOpen;
    assistantLauncher.setAttribute('aria-expanded',String(assistantOpen));
    creationPage.classList.toggle('creator-ai-visible',visible && assistantOpen);
    creationPage.classList.toggle('creator-ai-available',visible);
    assistant.querySelector('.creator-ai-model').textContent=`修改模型：${model.value || '尚未選擇模型'}`;
    assistant.querySelector('.creator-ai-model').title=model.value;
    assistantLauncher.querySelector('span').textContent=revising ? '修改中…' : 'AI 修改';
    if (draft?.generation_id !== assistantDraftId) {
      assistantDraftId=draft?.generation_id; assistantLog.replaceChildren(); assistantInput.value=''; assistantStatus.textContent='使用你選擇的模型及自備額度。';
    }
    assistantHistory.hidden=assistantLog.children.length===0;
    assistantLog.querySelectorAll('.message-edit-button').forEach(button=>button.disabled=revising || restoringVersion);
  }
  assistantLauncher.addEventListener('click',()=>{assistantOpen=true;updateAssistant();assistantInput.focus();});
  assistant.querySelector('.creator-ai-close').addEventListener('click',()=>{assistantOpen=false;updateAssistant();assistantLauncher.focus();});
  assistant.addEventListener('keydown',event=>{if(event.key==='Escape'){assistantOpen=false;updateAssistant();assistantLauncher.focus();}});
  assistantMedia?.addEventListener('change',event=>{assistantOpen=event.matches;assistantHistory.open=event.matches;updateAssistant();});
  new MutationObserver(updateAssistant).observe(creationPage,{attributes:true,attributeFilter:['class']});
  model.addEventListener('change',updateAssistant);
  assistantForm.addEventListener('submit',event=>{event.preventDefault();reviseAssistant(assistantInput.value.trim()).catch(()=>{});});
  async function reviseAssistant(instruction,baseRevision=null) {
    if (!instruction || revising || saving || generating || restoringVersion || !draft?.generation_id) return;
    if (!result.querySelector('.character-review')?.reportValidity()) return;
    const current=draft, epoch=creatorEpoch;
    const submit=assistantForm.querySelector('button[type="submit"]');
    const locked=[...panel.querySelectorAll('input,textarea,select,button')].filter(el=>!el.disabled);
    revising=true; locked.forEach(el=>el.disabled=true); submit.disabled=true; assistantInput.disabled=true; submit.textContent='正在修改…'; updateAssistant();
    assistantStatus.textContent='正在依照要求修改。可收起視窗，已開始的請求仍可能計費。';
    try {
      await syncDraft();
      if (draftDirty) throw new Error('原有修改尚未同步，請稍後再試');
      const openDetails=[...result.querySelectorAll('details[open]')].map(el=>el.querySelector('summary')?.textContent);
      const scroll=creationPage.scrollTop;
      const instructionBase=baseRevision ?? current.revision;
      const response=await fetch(`/api/character-generations/${current.generation_id}/revise`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision:current.revision,model:model.value,instruction,is_nsfw:panel.querySelector('#creator-adult').checked,...(baseRevision===null ? {} : {base_revision:baseRevision})})});
      const data=await response.json();
      if (!response.ok) throw new Error(typeof data.detail==='string' ? data.detail : `修改未完成（HTTP ${response.status}）`);
      if (epoch!==creatorEpoch || draft!==current) return;
      draft=data.draft; draftDirty=false; renderDraft(); setStep(1);
      result.querySelectorAll('details').forEach(el=>{el.open=openDetails.includes(el.querySelector('summary')?.textContent);}); creationPage.scrollTop=scroll;
      const entry=document.createElement('article'); const asked=document.createElement('strong'); asked.textContent=instruction;
      const summary=document.createElement('p'); summary.textContent=data.summary; entry.append(asked,summary); assistantLog.append(entry);
      window.dijiAttachMessageEditor(entry,{text:instruction,isBusy:()=>revising || restoringVersion || saving || generating,
        note:'會從這次修改前的草稿重新生成並另存新版本，使用你的模型商額度。目前草稿與後續修改仍留在版本歷史。',onSave:value=>reviseAssistant(value,instructionBase)});
      while(assistantLog.children.length>5) assistantLog.firstElementChild.remove();
      assistantInput.value=''; assistantStatus.textContent=`已更新 ${data.changed_fields.length} 個欄位並保存草稿。可繼續審核或測試對話。`; loadDraftHistory();
    } catch(error) {
      if (epoch===creatorEpoch && draft===current) assistantStatus.textContent=`修改失敗：${error.message}。原草稿仍保留。`;
      throw error;
    } finally {
      locked.forEach(el=>el.disabled=false); revising=false; submit.disabled=false; assistantInput.disabled=false; submit.textContent='交給 AI 修改'; updateAssistant();
    }
  }
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
        storageStatus(draftDirty ? '正在同步修改至伺服器…' : `草稿已保存至伺服器，版本 ${current.revision+1}。可從版本歷史還原；按下儲存角色才會加入角色庫。`);
        result.querySelector('.creator-version-history')?.dispatchEvent(new Event('draft-saved'));
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
      const rows = (await response.json()).filter(row => row.status === 'completed');
      if (epoch !== creatorEpoch) return;
      historyPanel.replaceChildren(); historyPanel.hidden = !rows.length;
      if (!rows.length) return;
      const label = document.createElement('label'); label.textContent = '已保存的草稿與版本歷史';
      const select = document.createElement('select');
      select.append(...rows.map(row => new Option(`${row.name}${row.saved_character_id ? ' · 已儲存角色' : ' · 草稿'} · ${new Date(row.updated).toLocaleString('zh-TW')}`,row.id)));
      label.append(select);
      const restore = document.createElement('button'); restore.type='button'; restore.className='ghost-button'; restore.textContent='繼續審核草稿';
      restore.addEventListener('click', async () => {
        if (generating || saving || revising || restoringVersion) return;
        await syncDraft();
        if (draftDirty && !window.confirm('目前修改尚未同步，仍要切換草稿嗎？')) return;
        restore.disabled=true;
        try {
          const response = await fetch(`/api/character-generations/${select.value}`,{cache:'no-store'});
          if (!response.ok) throw new Error('無法讀取草稿');
          const record = await response.json();
          if (epoch !== creatorEpoch) return;
          if (!record.data.draft) throw new Error('此紀錄沒有可恢復的草稿');
          draft={...record.data.draft,revision:record.revision}; draftId=draft.generation_id; savedCharacter=record.data.saved_character_id ? {id:record.data.saved_character_id} : null; draftDirty=false;
          const brief=record.data.request;
          if (brief) {
            panel.querySelector('#creator-keywords').value=brief.keywords || '';
            panel.querySelector('#creator-search').checked=Boolean(brief.enable_search);
            panel.querySelector('#creator-adult').checked=Boolean(brief.is_nsfw);
            if ([...model.options].some(option=>option.value===brief.model)) model.value=brief.model;
            persistBrief();
          }
          form.hidden=Boolean(savedCharacter); renderDraft(); setStep(1); creatorStatus.textContent=savedCharacter ? '已開啟已儲存角色的草稿紀錄，可從版本歷史還原為新草稿。' : '已恢復伺服器草稿，不會重新呼叫模型。';
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
    if (generating || revising || restoringVersion || draftDirty || (draft && !draft.generation_id && !savedCharacter)) { event.preventDefault(); event.returnValue = ''; }
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
    if (generating || revising || restoringVersion) return;
    const button = form.querySelector("button");
    const keywords = panel.querySelector("#creator-keywords").value.trim();
    if (!keywords || model.disabled) return;
    if (draft && !savedCharacter && !window.confirm('重新生成會建立另一份草稿，原草稿與已同步的版本仍會保留，確定繼續嗎？')) return;
    generating = true;
    updateAssistant();
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
    finally { window.clearInterval(waiting); generating = false; button.disabled = false; button.textContent = "生成角色草稿"; form.setAttribute('aria-busy', 'false'); updateAssistant(); }
  });
  function renderDraft() {
    panel.classList.remove('creator-trial-active');
    result.hidden = false; result.replaceChildren();
    const title = document.createElement('h2'); title.textContent = savedCharacter ? '已儲存角色的草稿紀錄' : '審核你的角色';
    const draftWarning = document.createElement('p'); draftWarning.className = 'creator-draft-warning'; draftWarning.setAttribute('role','status'); draftWarning.textContent = savedCharacter ? '這份角色已保存。查看舊版本並還原時，會建立新草稿，不會修改已保存的角色。' : draft.generation_id ? `目前版本 ${draft.revision+1}。修改成功同步後會另存一版，可從下方版本歷史還原；按下儲存角色才會加入角色庫。` : '草稿尚未儲存，請先審核並儲存。';
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
    const test = document.createElement('button'); test.type='button'; test.className='ghost-button creator-test-button'; test.textContent='測試對話';
    const actions = document.createElement('div'); actions.className='creator-review-actions'; actions.append(test,save);
    test.addEventListener('click', async () => {
      if (saving || generating || revising || restoringVersion || test.disabled || !review.reportValidity()) return;
      test.disabled=true; test.textContent='準備測試對話…';
      try {
        await syncDraft();
        if (!draft.generation_id || draftDirty) throw new Error('草稿尚未同步，請保留此頁，等同步完成後再試。');
        openTrial(review, test, title, draftWarning);
      } catch(error) { creatorStatus.textContent=error.message; storageStatus(error.message); }
      finally { test.disabled=false; test.textContent='測試對話'; }
    });
    review.addEventListener('submit', event => { event.preventDefault(); saveDraft(save); });
    review.append(presentation,advanced,actions); result.append(title,draftWarning);
    if (draft.generation_id) result.append(versionHistory(labels));
    result.append(review);
    if (savedCharacter) { review.querySelectorAll('input,textarea,button').forEach(el=>el.disabled=true); actions.hidden=true; }
    updateAssistant();
  }
  function versionHistory(labels) {
    const id=draft.generation_id, epoch=creatorEpoch;
    const details=document.createElement('details'); details.className='creator-version-history';
    const heading=document.createElement('summary'); heading.textContent='版本歷史與回滾';
    const note=document.createElement('p'); note.textContent='停止輸入約 0.7 秒後自動同步並保存一版。還原會建立新版本，保留目前內容。功能上線前缺少快照的中間版本無法補回。';
    const label=document.createElement('label'); label.textContent='選擇草稿版本'; const select=document.createElement('select'); label.append(select);
    const controls=document.createElement('div'); controls.className='creator-version-actions';
    const view=document.createElement('button'); view.type='button'; view.className='ghost-button'; view.textContent='查看這一版';
    const more=document.createElement('button'); more.type='button'; more.className='ghost-button'; more.textContent='載入更早版本'; more.hidden=true;
    const preview=document.createElement('section'); preview.className='creator-version-preview'; preview.hidden=true;
    const status=document.createElement('p'); status.setAttribute('role','status');
    let nextBefore=null, selected=null, loading=false;
    const valid=()=>draft?.generation_id===id && epoch===creatorEpoch && details.isConnected;
    async function load(append=false) {
      if (loading || !valid()) return;
      loading=true; view.disabled=true; more.disabled=true;
      try {
        if (!append) { await syncDraft(); if (draftDirty) throw new Error('目前修改尚未同步，請稍後再試'); }
        const response=await fetch(`/api/character-generations/${id}/versions${append ? `?before=${nextBefore}` : ''}`,{cache:'no-store'});
        if (!response.ok) throw new Error('無法讀取版本歷史');
        const data=await response.json(); if (!valid()) return;
        if (!append) { select.replaceChildren();selected=null;preview.hidden=true; }
        const names={generated:'首次生成',manual:'手動修改',ai:'AI 修改',rollback:'版本還原',recovered:'歷史快照',confirmed:'確認儲存'};
        select.append(...data.versions.map(item=>new Option(`版本 ${item.revision+1} · ${names[item.source] || '草稿'} · ${new Date(item.created).toLocaleString('zh-TW')}`,String(item.revision))));
        nextBefore=data.next_before; more.hidden=!data.has_more; status.textContent=`目前保存至版本 ${data.current_revision+1}，已列出 ${select.options.length} 個版本。`;
      } catch(error) { status.textContent=error.message; }
      finally { loading=false; view.disabled=!select.options.length; more.disabled=false; }
    }
    details.addEventListener('toggle',()=>{if(details.open)load();});
    details.addEventListener('draft-saved',()=>{if(details.open)load();});
    more.addEventListener('click',()=>load(true));
    select.addEventListener('change',()=>{selected=null;preview.hidden=true;});
    const restore=document.createElement('button'); restore.type='button'; restore.className='primary-button'; restore.textContent='還原這一版';
    view.addEventListener('click',async()=>{
      if (revising || saving || restoringVersion) return;
      view.disabled=true;
      try {
        const response=await fetch(`/api/character-generations/${id}/versions/${select.value}`,{cache:'no-store'});
        if (!response.ok) throw new Error('無法讀取這個版本');
        const data=await response.json(); if (!valid() || String(data.revision)!==select.value) return;
        selected=data;
        const title=document.createElement('h3'); title.textContent=`版本 ${data.revision+1}：${data.draft.character.character_name}`;
        const intro=document.createElement('p'); intro.textContent=data.draft.description_for_app || data.draft.brief_description;
        const content=document.createElement('details'); const caption=document.createElement('summary'); caption.textContent='完整人設、說話風格與其他設定';
        function describe(value,depth=0) {
          if(Array.isArray(value))return value.map(item=>'  '.repeat(depth)+'・'+String(item)).join('\n');
          if(value && typeof value==='object')return Object.entries(value).map(([key,item])=>'  '.repeat(depth)+(labels[key] || key.replaceAll('_',' '))+'：'+(item && typeof item==='object' ? '\n'+describe(item,depth+1) : String(item ?? '未設定'))).join('\n');
          return String(value ?? '未設定');
        }
        const copy=document.createElement('pre'); copy.textContent=describe(data.draft.character)+'\n\n說話風格\n'+data.draft.style_guide+'\n\n嗜好\n'+data.draft.hobbies;
        content.append(caption,copy); const explain=document.createElement('p'); explain.textContent=savedCharacter ? '已儲存角色不會改動；還原會建立一份新的可編輯草稿。' : '目前內容會保留在版本歷史，之後仍可再還原回來。';
        preview.replaceChildren(title,intro,content,explain,restore); preview.hidden=false;
      } catch(error) { status.textContent=error.message; }
      finally { view.disabled=false; }
    });
    restore.addEventListener('click',async()=>{
      if (!selected || revising || saving || generating || restoringVersion) return;
      const targetRevision=selected.revision;
      const locked=[...panel.querySelectorAll('input,textarea,select,button')].filter(el=>!el.disabled);
      restoringVersion=true;locked.forEach(el=>el.disabled=true);updateAssistant();
      try {
        await syncDraft(); if (draftDirty) throw new Error('目前修改尚未同步，這次未還原');
        const response=await fetch(`/api/character-generations/${id}/rollback`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision:draft.revision,target_revision:targetRevision})});
        const data=await response.json(); if (!valid()) return;
        if (!response.ok) throw new Error(typeof data.detail==='string' ? data.detail : '還原未完成');
        const fork=data.generation_id!==id;
        assistantLog.replaceChildren();assistantInput.value='';assistantStatus.textContent='草稿已還原，下一次 AI 修改會使用還原後的內容。';
        draft=data;draftId=data.generation_id;savedCharacter=null;draftDirty=false;form.hidden=false;renderDraft();setStep(1);loadDraftHistory();
        creatorStatus.textContent=fork ? '已從舊版本建立新草稿，原角色保持不變。' : `已還原版本 ${targetRevision+1}，並另存為版本 ${data.revision+1}；目前內容仍在歷史中。`;
        storageStatus(creatorStatus.textContent);result.querySelector('.creator-version-history').open=true;result.scrollIntoView({block:'start'});
      } catch(error) { if(valid())status.textContent=`還原失敗：${error.message}`; }
      finally { restoringVersion=false;locked.forEach(el=>el.disabled=false);updateAssistant(); }
    });
    controls.append(view,more);details.append(heading,note,label,controls,preview,status);return details;
  }
  function openTrial(review, testButton, title, warning) {
    result.querySelector('.draft-trial')?.remove();
    const trial = document.createElement('section'); trial.className='draft-trial'; trial.setAttribute('aria-label','草稿測試對話');
    const generationId=draft.generation_id, revision=draft.revision, epoch=creatorEpoch;
    let chatId=`trial-${crypto.randomUUID()}`;
    let trialPersonaId=window.dijiState?.playerPersonaId || null;
    const selectedModel=model.value, adult=panel.querySelector('#creator-adult').checked;
    const header=document.createElement('header'); header.className='draft-trial-header';
    const back=document.createElement('button'); back.type='button'; back.className='primary-button'; back.textContent='返回審核草稿';
    const name=document.createElement('h3'); name.textContent=`和「${draft.character.character_name}」試聊`;
    const note=document.createElement('p'); note.textContent='使用你的模型商額度；試聊不會將角色加入角色庫。返回後可繼續修改，重新測試會開始新的對話。';
    const modelNote=document.createElement('p'); modelNote.className='draft-trial-model'; modelNote.textContent=`測試模型：${selectedModel}`;
    const modeLabel=document.createElement('label'); modeLabel.textContent='回覆方式';
    const mode=document.createElement('select'); mode.append(new Option('短對話','dialog'),new Option('長對話','story')); modeLabel.append(mode);
    const log=document.createElement('div'); log.className='draft-trial-log'; log.setAttribute('role','log'); log.setAttribute('aria-label','測試對話記錄');
    const composer=document.createElement('form'); composer.className='draft-trial-composer';
    const inputLabel=document.createElement('label'); inputLabel.textContent='測試訊息';
    const input=document.createElement('textarea'); input.required=true; input.rows=3; input.maxLength=16000; input.placeholder='用一句話試試角色的反應…'; inputLabel.append(input);
    const send=document.createElement('button'); send.type='submit'; send.className='primary-button'; send.textContent='送出測試訊息';
    const status=document.createElement('p'); status.className='draft-trial-status'; status.setAttribute('role','status'); status.textContent='尚未發送訊息，不會產生模型費用。';
    function appendMessage(author,text,role,index=log.querySelectorAll('.draft-trial-message').length) {
      const article=document.createElement('article'); article.className=`draft-trial-message ${role}`;
      const label=document.createElement('strong'); label.textContent=author;
      const copy=document.createElement('p'); copy.textContent=text; article.append(label,copy); log.append(article);
      if(role==='user')window.dijiAttachMessageEditor(article,{text,isBusy:()=>busy,onSave:value=>editTrialMessage(index,text,value)});
      return article;
    }
    let busy=false;
    function setBusy(value) {
      busy=value;input.disabled=value;send.disabled=value;mode.disabled=value;send.textContent=value?'正在生成…':'送出測試訊息';
      log.querySelectorAll('.message-edit-button').forEach(button=>button.disabled=value);
    }
    function showRecord(record) {
      chatId=record.chat_id;trialPersonaId=record.player_persona_id || null;log.replaceChildren();
      if(record.parent_chat_id) {
        const notice=document.createElement('div');notice.className='conversation-branch-notice';notice.textContent='已從編輯處重新生成，原試聊仍保留。'+(record.state_checkpoint_available===false?' 舊試聊缺少狀態快照，記憶將重新累積。':'');
        const original=document.createElement('button');original.type='button';original.className='ghost-button';original.textContent='查看編輯前對話';
        original.addEventListener('click',async()=>{
          if(busy)return;
          try{const response=await fetch(`/api/character-generations/${generationId}/test-conversations/${record.parent_chat_id}`,{cache:'no-store'});if(!response.ok)throw new Error('無法讀取原試聊');const source=await response.json();if(epoch===creatorEpoch && trial.isConnected)showRecord(source);}catch(error){status.textContent=error.message;}
        });notice.append(original);log.append(notice);
      }
      record.messages.forEach((message,index)=>appendMessage(message.sender_type===1?'你':'角色',message.text,message.sender_type===1?'user':'assistant',index));
    }
    async function editTrialMessage(index,original,text) {
      const sourceId=chatId;setBusy(true);status.textContent='正在從修改處重新生成，原試聊會保留。';
      try {
        const sourceResponse=await fetch(`/api/character-generations/${generationId}/test-conversations/${sourceId}`,{cache:'no-store'});
        if(!sourceResponse.ok)throw new Error('無法讀取已保存的試聊');const source=await sourceResponse.json();
        if(source.messages[index]?.sender_type!==1 || source.messages[index]?.text!==original)throw new Error('試聊已變更，請重新讀取後再編輯');
        const response=await fetch(`/api/character-generations/${generationId}/test-interactions/edit`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({chat_id:sourceId,revision,model:selectedModel,text,chat_mode:mode.value,is_nsfw:adult,player_persona_id:trialPersonaId,message_index:index,expected_revision:source.revision})});
        const data=await response.json();if(epoch!==creatorEpoch || !trial.isConnected)return;
        if(data.conversation)showRecord(data.conversation);
        if(!response.ok)throw new Error(data.detail || '重新生成未完成');
        status.textContent='已從修改處重新生成，原試聊及原記憶仍保留在原對話。';
      }catch(error){status.textContent=`重新生成未完成：${error.message}`;throw error;}
      finally{setBusy(false);}
    }
    composer.addEventListener('submit',async event=>{
      event.preventDefault();
      const text=input.value.trim(); if (busy || !text) return;
      if(window.dijiEnsurePlayerPersona && !await window.dijiEnsurePlayerPersona())return;
      const chosen=window.dijiState?.playerPersonaId || null;
      if(chosen!==trialPersonaId){chatId=`trial-${crypto.randomUUID()}`;trialPersonaId=chosen;log.replaceChildren();}
      setBusy(true);
      const pending=appendMessage('你',text,'user'); input.value='';
      const waiting=appendMessage('角色','正在生成回覆…','assistant draft-trial-waiting');
      const dots=waiting.querySelector('p'); dots.textContent=''; dots.className='draft-trial-dots'; dots.setAttribute('aria-label','角色正在生成回覆');
      for (let i=0;i<3;i++) { const dot=document.createElement('span'); dot.textContent='●'; dot.setAttribute('aria-hidden','true'); dots.append(dot); }
      status.textContent='可隨時返回審核草稿；已開始的模型請求仍可能計費。';
      try {
        const response=await fetch(`/api/character-generations/${generationId}/test-interactions`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({chat_id:chatId,revision,model:selectedModel,text,chat_mode:mode.value,is_nsfw:adult,player_persona_id:trialPersonaId})});
        const data=await response.json();
        if (!response.ok) {
          const error=new Error(typeof data.detail==='string' ? data.detail : `測試未完成（HTTP ${response.status}）`);
          error.notAccepted=[413,429].includes(response.status);throw error;
        }
        waiting.remove(); appendMessage('角色',data.text,'assistant'); status.textContent='測試對話已保存至伺服器，與正式聊天分開。';
      } catch(error) {
        waiting.remove();if(error.notAccepted)pending.remove();
        status.textContent=error.notAccepted ? `尚未送出：${error.message}。文字已保留，請稍後再試。` : `測試未完成：${error.message}。請確認已送出訊息，再決定是否重新生成；已開始的請求仍可能計費。`;
        input.value=text;
      }
      finally { setBusy(false); }
    });
    const previousHistoryHidden=historyPanel.hidden;
    back.addEventListener('click',()=>{
      panel.classList.remove('creator-trial-active');
      trial.hidden=true; review.hidden=false; form.hidden=false; warning.hidden=false; title.hidden=false; historyPanel.hidden=previousHistoryHidden;
      updateAssistant();
      testButton.focus(); testButton.scrollIntoView({block:'center'});
    });
    header.append(back,name); composer.append(inputLabel,send); trial.append(header,note,modelNote,modeLabel,log,composer,status); result.append(trial);
    review.hidden=true; form.hidden=true; warning.hidden=true; title.hidden=true; historyPanel.hidden=true;
    panel.classList.add('creator-trial-active');
    updateAssistant();
    trial.scrollIntoView({block:'start'}); back.focus();
  }
  async function saveDraft(button) {
    if (saving || revising || restoringVersion) return;
    saving = true; button.disabled = true; button.textContent = '正在儲存…';
    await syncDraft();
    const id = draftId;
    const character = { id, name: draft.character.character_name, premise: draft.description_for_app || draft.brief_description || '', voice: (draft.style_guide || '依角色設定互動。').slice(0,2000), profile: draft.character, style_guide: draft.style_guide || '', generation_metadata: {brief_description:draft.brief_description || '',category:draft.category || '',hobbies:draft.hobbies || ''}, full_prompt: '', source: { generated_file: 'DIJI character creator', ...(draft.generation_id ? {generation_id:draft.generation_id} : {}) } };
    try {
      const response = await fetch(`/api/characters/${id}`, {method:'PUT', headers:{'Content-Type':'application/json'},body:JSON.stringify(character)});
      const saved = await response.json();
      if (!response.ok) throw new Error(typeof saved.detail === 'string' ? saved.detail : '請檢查人設欄位內容後重試');
      savedCharacter = saved;
      updateAssistant();
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
      if (draft.generation_id) {
        const history=document.createElement('button');history.className='ghost-button';history.textContent='查看草稿版本';
        history.addEventListener('click',async()=>{
          try {
            const response=await fetch(`/api/character-generations/${draft.generation_id}`,{cache:'no-store'});
            if(!response.ok)throw new Error('無法讀取版本');const record=await response.json();draft={...record.data.draft,revision:record.revision};renderDraft();result.querySelector('.creator-version-history').open=true;
          }catch(error){creatorStatus.textContent=error.message;}
        });result.append(history);
      }
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
  document.querySelectorAll('[data-auth-logout]').forEach(button=>button.addEventListener('click',()=>{creatorEpoch++;panel.classList.remove('creator-trial-active');clearTimeout(syncTimer);draftDirty=false;historyPanel.hidden=true;historyPanel.replaceChildren();briefKey=null;draft=null;savedCharacter=null;form.reset();form.hidden=false;result.replaceChildren();result.hidden=true;setStep(0);updateAssistant();}));
})();

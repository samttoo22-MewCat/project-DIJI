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
  const briefKey = 'diji-creator-brief';
  function persistBrief() {
    try { sessionStorage.setItem(briefKey, JSON.stringify({keywords: panel.querySelector('#creator-keywords').value, online: panel.querySelector('#creator-search').checked, adult: panel.querySelector('#creator-adult').checked, model: model.value})); } catch {}
  }
  let restoredBrief = null;
  try { restoredBrief = JSON.parse(sessionStorage.getItem(briefKey) || 'null'); } catch {}
  if (restoredBrief) {
    panel.querySelector('#creator-keywords').value = restoredBrief.keywords || '';
    panel.querySelector('#creator-search').checked = Boolean(restoredBrief.online);
    panel.querySelector('#creator-adult').checked = Boolean(restoredBrief.adult);
  }
  form.addEventListener('input', persistBrief);
  form.addEventListener('change', persistBrief);
  window.addEventListener('beforeunload', persistBrief);
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
      if (restoredBrief?.model && [...model.options].some(option => option.value === restoredBrief.model)) model.value = restoredBrief.model;
      creatorStatus.textContent = model.options.length ? `已載入 ${model.options.length} 個有已核准越獄的模型；最新項目優先。` : "尚無已核准的越獄，請先到越獄工作台完成編輯與核准。";
    } catch { creatorStatus.textContent = "無法讀取可用模型。"; }
  }
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector("button");
    const keywords = panel.querySelector("#creator-keywords").value.trim();
    if (!keywords || model.disabled) return;
    button.disabled = true; button.textContent = "生成中…";
    form.setAttribute('aria-busy', 'true');
    creatorStatus.textContent = `正以 ${model.value} 與對應越獄生成草稿…`;
    try {
      const response = await fetch("/api/characters/generate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ keywords, model: model.value, enable_search: panel.querySelector("#creator-search").checked, is_nsfw: panel.querySelector("#creator-adult").checked }) });
      draft = await response.json();
      if (!response.ok) throw new Error(draft.detail || "生成失敗");
      draftId = `draft-${crypto.randomUUID()}`;
      renderDraft(); setStep(1); creatorStatus.textContent = "草稿已完成。你可以修改人設與說話風格，再儲存。";
      result.scrollIntoView({block:'start', behavior:'auto'});
    } catch (error) { creatorStatus.textContent = `生成失敗：${error.message}`; }
    finally { button.disabled = false; button.textContent = "生成角色草稿"; form.setAttribute('aria-busy', 'false'); }
  });
  function renderDraft() {
    result.hidden = false; result.replaceChildren();
    const title = document.createElement('h2'); title.textContent = '審核你的角色';
    const review = document.createElement('form'); review.className = 'character-review';
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
    const advanced = document.createElement('details'); const heading = document.createElement('summary'); heading.textContent = '進階檢視：完整角色 JSON';
    const json = document.createElement('pre'); json.textContent = JSON.stringify(draft.character,null,2);
    advanced.addEventListener('toggle', () => { json.textContent = JSON.stringify(draft.character,null,2); }); advanced.append(heading,json);
    const save = document.createElement('button'); save.type = 'submit'; save.className = 'primary-button'; save.textContent = '儲存角色 · 僅自己可見';
    review.addEventListener('submit', event => { event.preventDefault(); saveDraft(save); });
    review.append(advanced,save); result.append(title,review);
  }
  async function saveDraft(button) {
    if (saving) return;
    saving = true; button.disabled = true; button.textContent = '正在儲存…';
    const id = draftId;
    const character = { id, name: draft.character.character_name, premise: draft.description_for_app || draft.brief_description || '', voice: (draft.style_guide || '依角色設定互動。').slice(0,2000), profile: draft.character, style_guide: draft.style_guide || '', full_prompt: '', source: { generated_file: 'DIJI character creator' } };
    try {
      const response = await fetch(`/api/characters/${id}`, {method:'PUT', headers:{'Content-Type':'application/json'},body:JSON.stringify(character)});
      const saved = await response.json();
      if (!response.ok) throw new Error(typeof saved.detail === 'string' ? saved.detail : '請檢查人設欄位內容後重試');
      window.dijiState.characters = window.dijiState.characters.filter(item => item.id !== saved.id).concat(saved);
      window.dijiRenderCharacterLibrary(); setStep(2);
      try { sessionStorage.removeItem(briefKey); } catch {}
      result.replaceChildren();
      const title = document.createElement('h2'); title.textContent = '角色已儲存';
      const note = document.createElement('p'); note.textContent = `「${saved.name}」已保存到你的帳號，僅自己可見。`;
      const chat = document.createElement('button'); chat.className = 'primary-button'; chat.textContent = '開始聊天'; chat.addEventListener('click', () => window.dijiSelectCharacter(saved));
      const library = document.createElement('button'); library.className = 'ghost-button'; library.textContent = '回到角色庫'; library.addEventListener('click', () => document.querySelector('.rail-button[data-view="characters"]').click());
      result.append(title,note,chat,library); creatorStatus.textContent = '儲存完成。';
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
  window.addEventListener('diji-workspace-ready', () => { loadModels(); refreshCharacterLibrary(); });
})();

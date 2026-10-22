(() => {
  const target = document.querySelector('[data-screen="characters"]');
  if (!target) return;
  target.replaceChildren(document.querySelector("#character-creator").content.cloneNode(true));
  const grid = target.querySelector("#character-library-grid");
  const status = target.querySelector("#character-library-status");
  const search = target.querySelector("#character-library-search");
  const panel = target.querySelector("#character-creator-panel");
  const form = target.querySelector("#creator-brief");
  const creatorStatus = target.querySelector("#creator-status");
  const result = target.querySelector("#creator-result");
  const model = target.querySelector("#creator-model");
  let draft = null;

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
      card.innerHTML = '<span class="character-library-initial"></span><span class="character-library-copy"><strong></strong><small></small></span><span class="character-library-arrow" aria-hidden="true">→</span>';
      card.querySelector(".character-library-initial").textContent = character.name.slice(0, 1);
      card.querySelector("strong").textContent = character.name;
      card.querySelector("small").textContent = character.premise;
      card.addEventListener("click", () => window.dijiSelectCharacter(character));
      return card;
    }));
    status.textContent = characters.length ? `${characters.length} 位可選角色` : "沒有符合搜尋的角色。";
  };
  search.addEventListener("input", window.dijiRenderCharacterLibrary);
  target.querySelector("#open-character-creator").addEventListener("click", () => {
    panel.hidden = !panel.hidden;
    if (!panel.hidden) panel.querySelector("#creator-keywords").focus();
  });

  async function loadModels() {
    try {
      const response = await fetch("/api/jailbreaks");
      if (!response.ok) throw new Error("jailbreak unavailable");
      const available = (await response.json()).filter((item) => item.review_status === "approved" && item.prompt).sort((a, b) => b.last_updated.localeCompare(a.last_updated));
      model.replaceChildren(...available.flatMap((item) => item.openrouter_models.map((id) => new Option(`${id} · 越獄：${item.name} · ${item.last_updated}`, id))));
      model.disabled = !model.options.length;
      creatorStatus.textContent = model.options.length ? `已載入 ${model.options.length} 個有已核准越獄的模型；最新項目優先。` : "尚無已核准的越獄，請先到越獄工作台完成編輯與核准。";
    } catch { creatorStatus.textContent = "無法讀取可用模型。"; }
  }
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector("button");
    const keywords = target.querySelector("#creator-keywords").value.trim();
    if (!keywords || model.disabled) return;
    button.disabled = true; button.textContent = "生成中…";
    creatorStatus.textContent = `正以 ${model.value} 與對應越獄生成草稿…`;
    try {
      const response = await fetch("/api/characters/generate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ keywords, model: model.value, enable_search: target.querySelector("#creator-search").checked, is_nsfw: target.querySelector("#creator-adult").checked }) });
      draft = await response.json();
      if (!response.ok) throw new Error(draft.detail || "生成失敗");
      renderDraft(); creatorStatus.textContent = "草稿已完成。請審核後再儲存。";
    } catch (error) { creatorStatus.textContent = `生成失敗：${error.message}`; }
    finally { button.disabled = false; button.textContent = "生成角色草稿"; }
  });
  function renderDraft() {
    result.hidden = false; result.replaceChildren();
    const title = document.createElement("h2"); title.textContent = draft.character.character_name;
    const summary = document.createElement("p"); summary.textContent = draft.brief_description || draft.description_for_app || "已生成角色草稿。";
    const details = document.createElement("pre"); details.textContent = JSON.stringify(draft.character, null, 2);
    const save = document.createElement("button"); save.className = "primary-button"; save.textContent = "儲存到角色庫";
    save.addEventListener("click", saveDraft);
    result.append(title, summary, details, save);
  }
  async function saveDraft() {
    const id = `draft-${crypto.randomUUID()}`;
    const character = { id, name: draft.character.character_name, premise: draft.description_for_app || draft.brief_description || "", voice: draft.style_guide || "依角色設定互動。", profile: draft.character, style_guide: draft.style_guide || "", full_prompt: draft.full_prompt || "", source: { generated_file: "DIJI character creator" } };
    const response = await fetch(`/api/characters/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(character) });
    const saved = await response.json();
    if (!response.ok) { creatorStatus.textContent = `儲存失敗：${saved.detail || "未知錯誤"}`; return; }
    window.dijiState.characters.push(saved);
    window.dijiRenderCharacterLibrary();
    window.dijiSelectCharacter(saved);
  }
  async function refreshCharacterLibrary() {
    try {
      const response = await fetch("/api/characters");
      if (!response.ok) throw new Error("catalog unavailable");
      window.dijiState.characters = await response.json();
      window.dijiRenderCharacterLibrary();
    } catch (error) {
      status.textContent = `角色庫無法載入：${error.message}`;
    }
  }
  loadModels();
  refreshCharacterLibrary();
})();

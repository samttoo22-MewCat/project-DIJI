(() => {
  const content = document.querySelector(".content");
  const screen = document.createElement("section");
  screen.className = "screen studio-screen jailbreak-screen";
  screen.dataset.screen = "jailbreak";
  screen.innerHTML = `<header class="page-header"><div><p class="eyebrow">JAILBREAK 工作台</p><h1>選擇、編輯與審核本機越獄。</h1><p>越獄獨立管理；成人虛構互動會依所選模型自動套用對應的已核准越獄。</p></div><button class="primary-button" id="jailbreak-new" type="button">建立本機越獄</button></header><div class="jailbreak-workbench"><section class="jailbreak-library" aria-label="Jailbreak 越獄清單"><div class="jailbreak-library-head"><div><h2>越獄目錄</h2><p id="jailbreak-count">載入中…</p></div><button class="ghost-button" id="jailbreak-reload" type="button">重新讀取</button></div><label class="sr-only" for="jailbreak-list">選擇越獄</label><select id="jailbreak-list" size="12"></select></section><section class="jailbreak-editor" aria-labelledby="jailbreak-editor-title"><h2 id="jailbreak-editor-title">越獄編輯器</h2><p>來源目錄項目也可在本機改名或補上自訂越獄文字；變更只寫入本機 runtime。</p><form id="jailbreak-form"><label>名稱<input id="jailbreak-name" maxlength="80" required /></label><div class="jailbreak-grid"><label>模型範圍<input id="jailbreak-model" maxlength="160" required /></label><label>審核狀態<select id="jailbreak-review"><option value="metadata_only">僅中繼資料</option><option value="approved">已核准</option></select></label></div><label>來源 URL<input id="jailbreak-source" maxlength="2000" required /></label><label>指南路徑／備註<input id="jailbreak-guide-path" maxlength="500" /></label><label>本機越獄文字<textarea id="jailbreak-prompt" maxlength="20000" placeholder="輸入你自行撰寫、要在本機使用的越獄文字。"></textarea></label><p class="jailbreak-editor-status" id="jailbreak-editor-status" aria-live="polite"></p><div class="jailbreak-editor-actions"><button class="primary-button" id="jailbreak-save" type="submit">儲存越獄</button><button class="ghost-button" id="jailbreak-use" type="button">選取越獄</button></div></form></section></div>`;
  content.append(screen);

  const el = (selector) => screen.querySelector(selector);
  const deleteButton = document.createElement("button");
  deleteButton.className = "danger-button";
  deleteButton.type = "button";
  deleteButton.textContent = "刪除規則";
  el(".jailbreak-editor-actions").append(deleteButton);
  let records = [];
  let selectedId = localStorage.getItem("diji-jailbreak-id") || "";
  const localId = () =>
    `custom-${crypto.randomUUID().replaceAll("-", "").slice(0, 20)}`;
  const status = (message, stateName = "") => {
    const node = el("#jailbreak-editor-status");
    node.textContent = message;
    node.dataset.state = stateName;
  };
  const today = () => new Date().toISOString().slice(0, 10);

  function selected() {
    return records.find((item) => item.id === selectedId);
  }
  function show(record) {
    selectedId = record.id;
    el("#jailbreak-name").value = record.name;
    el("#jailbreak-model").value = record.model;
    el("#jailbreak-review").value = record.review_status;
    el("#jailbreak-source").value = record.source_url;
    el("#jailbreak-guide-path").value = record.guide_path || "";
    el("#jailbreak-prompt").value = record.prompt || "";
    status(
      `最後更新：${record.last_updated}；OpenRouter 模型：${record.openrouter_models?.length || 0} 個。`,
    );
  }
  function render() {
    const list = el("#jailbreak-list");
    list.replaceChildren(
      ...records.map(
        (item) =>
          new Option(
            `${item.name} · ${item.review_status === "approved" ? "已核准" : "僅中繼資料"}`,
            item.id,
          ),
      ),
    );
    el("#jailbreak-count").textContent = `${records.length} 個本機越獄`;
    if (!records.length) {
      status("尚無越獄，請建立本機越獄。");
      return;
    }
    if (!records.some((item) => item.id === selectedId))
      selectedId = records[0].id;
    list.value = selectedId;
    show(selected());
  }
  async function load() {
    if (!workspaceAvailable) return;
    status("正在讀取本機目錄…");
    try {
      const response = await fetch("/api/jailbreaks");
      if (!response.ok) throw new Error("catalog unavailable");
      records = await response.json();
      render();
      const remembered = localStorage.getItem("diji-jailbreak-id");
      if (remembered && remembered === selectedId) {
        const record = selected();
        state.jailbreakId = record.id;
        state.experimentId =
          record.review_status === "approved" ? "ui-jailbreak" : null;
      }
    } catch {
      records = [];
      el("#jailbreak-list").replaceChildren();
      el("#jailbreak-count").textContent = "目錄無法載入";
      status("無法讀取本機 jailbreak 目錄。", "error");
    }
  }
  async function save(event) {
    event.preventDefault();
    const previous = selected();
    const record = {
      id: previous?.id || localId(),
      name: el("#jailbreak-name").value.trim(),
      model: el("#jailbreak-model").value.trim(),
      openrouter_models: previous?.openrouter_models || [],
      guide_path: el("#jailbreak-guide-path").value.trim(),
      last_updated: today(),
      source_url: el("#jailbreak-source").value.trim(),
      review_status: el("#jailbreak-review").value,
      prompt: el("#jailbreak-prompt").value,
    };
    if (!record.name || !record.model || !record.source_url) {
      status("名稱、模型範圍與來源 URL 為必填。", "error");
      return;
    }
    const button = el("#jailbreak-save");
    button.disabled = true;
    button.textContent = "儲存中…";
    try {
      const response = await fetch(`/api/jailbreaks/${record.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(record),
      });
      const saved = await response.json();
      if (!response.ok) throw new Error(saved.detail || "save failed");
      selectedId = saved.id;
      const index = records.findIndex((item) => item.id === saved.id);
      if (index < 0) records.push(saved);
      else records[index] = saved;
      render();
      status("已儲存至本機規則目錄。", "saved");
    } catch (error) {
      status(`無法儲存：${error.message}`, "error");
    } finally {
      button.disabled = false;
      button.textContent = "儲存越獄";
    }
  }
  async function useSelected() {
    const record = selected();
    if (!record) return;
    localStorage.setItem("diji-jailbreak-id", record.id);
    state.jailbreakId = record.id;
    state.experimentId =
      record.review_status === "approved" ? "ui-jailbreak" : null;
    if (record.review_status === "approved") {
      const experiment = {
        id: state.experimentId,
        name: `${record.name} 本機互動`,
        jailbreak_id: record.id,
      };
      const response = await fetch(`/api/experiments/${experiment.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(experiment),
      });
      if (!response.ok) {
        state.experimentId = null;
        status("無法建立互動越獄設定。", "error");
        return;
      }
    }
    status(
      record.review_status === "approved"
        ? "已選取供檢視；互動仍會依所選模型解析對應越獄。"
        : "已選取供檢視；未核准越獄不會注入互動。",
      "saved",
    );
  }
  async function deleteSelected() {
    const record = selected();
    if (
      !record ||
      !window.confirm(
        `確定要刪除「${record.name}」嗎？這只會刪除本機目錄中的這筆規則。`,
      )
    )
      return;
    deleteButton.disabled = true;
    try {
      const response = await fetch(`/api/jailbreaks/${record.id}`, {
        method: "DELETE",
      });
      if (!response.ok)
        throw new Error((await response.json()).detail || "delete failed");
      records = records.filter((item) => item.id !== record.id);
      selectedId = records[0]?.id || "";
      if (localStorage.getItem("diji-jailbreak-id") === record.id) {
        localStorage.removeItem("diji-jailbreak-id");
        state.jailbreakId = null;
        state.experimentId = null;
      }
      render();
      status("已從本機目錄刪除。重新匯入可恢復來源中繼資料。", "saved");
    } catch (error) {
      status(`無法刪除：${error.message}`, "error");
    } finally {
      deleteButton.disabled = false;
    }
  }
  el("#jailbreak-list").addEventListener("change", (event) => {
    selectedId = event.target.value;
    show(selected());
  });
  el("#jailbreak-reload").addEventListener("click", load);
  el("#jailbreak-new").addEventListener("click", () => {
    selectedId = "";
    el("#jailbreak-form").reset();
    el("#jailbreak-review").value = "metadata_only";
    el("#jailbreak-source").value = "local";
    el("#jailbreak-guide-path").value = "本機自訂";
    status("新規則尚未儲存。");
    el("#jailbreak-name").focus();
  });
  el("#jailbreak-form").addEventListener("submit", save);
  el("#jailbreak-use").addEventListener("click", useSelected);
  deleteButton.addEventListener("click", deleteSelected);
  document
    .querySelector('[data-view="jailbreak"]')
    .addEventListener("click", load);
  window.addEventListener('diji-workspace-ready', load);
})();

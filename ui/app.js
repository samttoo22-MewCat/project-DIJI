window.dijiState = {
  character: "", characterId: null, avatar: "", flowId: "immersive",
  chatId: "preview", history: [], liveSession: false, jailbreakId: null,
  experimentId: null, chatMode: "story", characters: [], conversations: [],
};
const state = window.dijiState;
const conversations = document.querySelector("#conversation");
const toast = document.querySelector("#toast");
const chatMemoryBackfill = document.querySelector("#chat-memory-backfill");
const chatMemoryBackfillNote = document.querySelector("#chat-memory-backfill-note");
const chatMemoryBackfillStatus = document.querySelector("#chat-memory-backfill-status");

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 2200);
}
function showScreen(name) {
  const previous = document.querySelector('.screen.active')?.dataset.screen;
  if (name === 'connections' && ['chat', 'create-character'].includes(previous)) rememberPendingTask(previous);
  if (document.querySelector(`[data-screen="${name}"]`) && window.location.hash !== `#${name}`) history.pushState(null, '', `#${name}`);
  document.querySelectorAll(".screen").forEach((screen) => screen.classList.toggle("active", screen.dataset.screen === name));
  document.querySelectorAll(".rail-button[data-view]").forEach((button) => button.classList.toggle("active", button.dataset.view === name));
  if (name !== "chat") setChatList(false);
  else if (!compactChatList.matches) setChatList(isChatListAvailable());
  if (name === "memory" && requireLogin()) loadMemories();
  if (name === "chat" || name === "create-character") refreshChatProviderState();
}

function rememberPendingTask(name) {
  try { sessionStorage.setItem('diji-pending-task', name); } catch {}
  window.dispatchEvent(new Event('diji-task-changed'));
}
function pendingTask() {
  try { const task = sessionStorage.getItem('diji-pending-task'); return ['chat','create-character'].includes(task) ? task : null; } catch { return null; }
}
function resumePendingTask() {
  const task = pendingTask() || 'chat';
  try { sessionStorage.removeItem('diji-pending-task'); } catch {}
  if (task === 'chat') openRolePicker(); else showScreen(task);
  window.dispatchEvent(new Event('diji-task-changed'));
}
async function updateHomeJourney() {
  const button = document.querySelector('#home-start');
  const note = document.querySelector('.home-note');
  const steps = document.querySelectorAll('#home-journey li');
  const signedIn = Boolean(authenticatedUser);
  let connected = false;
  if (signedIn) {
    try { const response = await fetch('/api/connections/priority', {cache:'no-store'}); if (response.ok) connected = (await response.json()).connected.length > 0; } catch {}
  }
  const stage = !signedIn ? 0 : !connected ? 1 : 2;
  steps.forEach((step,index) => { step.classList.toggle('complete', index < stage); if (index === stage) step.setAttribute('aria-current','step'); else step.removeAttribute('aria-current'); });
  button.textContent = ['登入，保存我的角色世界', '連接模型商，開始使用', '選擇角色開始對話'][stage];
  button.dataset.next = ['login','connections','chat'][stage];
  note.textContent = ['登入後，角色、對話與記憶會保存到你的 DIJI 帳號。', '選擇 BazaarLink 或 OpenRouter，連接自己的模型額度。', '已準備完成。選一位角色，開始第一段對話。'][stage];
}

function setChatProviderLocked(locked, title = '尚未連接模型商') {
  for (const name of ['chat', 'create-character']) {
    const screen = document.querySelector(`[data-screen="${name}"]`);
    const gate = screen.querySelector('.chat-provider-gate');
    screen.classList.toggle('provider-locked', locked);
    gate.hidden = !locked;
    gate.querySelector('h2').textContent = title;
    for (const child of screen.children) {
      if (child === gate) continue;
      child.inert = locked;
      if (locked) child.setAttribute('aria-hidden', 'true');
      else child.removeAttribute('aria-hidden');
    }
  }
  if (locked) { setDetails(false); setChatList(false); }
}

async function refreshChatProviderState() {
  const status = document.querySelector('#chat-provider-status');
  const config = document.querySelector('#chat-provider-config');
  const controls = document.querySelector('#chat-provider-controls');
  const explain = '角色生成與回覆需要由模型商提供 AI 模型。連接後才能建立角色及聊天，費用會使用你自己的額度。請前往左側「模型連線」完成設定。';
  const names = {openrouter: 'OpenRouter', bazaarlink: 'BazaarLink'};
  try {
    const response = await fetch('/api/connections/priority', {cache:'no-store'});
    if (response.status === 401) {
      status.textContent = '尚未連接模型商'; config.textContent = explain; controls.hidden = true; setChatProviderLocked(true); return false;
    }
    if (!response.ok) throw new Error();
    const data = await response.json();
    const providers = data.priority.filter(id => data.connected.includes(id));
    setChatProviderLocked(providers.length === 0);
    controls.hidden = providers.length === 0;
    status.textContent = providers.length ? `已連接模型商：${providers.map(id => names[id]).join('、')}` : '尚未連接模型商';
    const model = document.querySelector('#model-input').value;
    config.textContent = providers.length ? `額度順序：${providers.map(id => names[id]).join(' → ')}。目前模型：${model || '尚未選擇'}。` : explain;
    return providers.length > 0;
  } catch {
    status.textContent = '無法確認模型商連接狀態，請稍後重試'; config.textContent = explain; controls.hidden = true; setChatProviderLocked(true, status.textContent); return false;
  }
}
function openRolePicker() {
  setChatReady(false);
  showScreen("chat");
  window.location.hash = "chat";
}
function setChatReady(ready) {
  const chatScreen = document.querySelector('.screen[data-screen="chat"]');
  chatScreen.classList.toggle("awaiting-character", !ready);
  if (!ready) { setDetails(false); setChatList(false); }
}
function activeCharacter(character) {
  state.character = character.name;
  state.characterId = character.id;
  state.avatar = character.name.slice(0, 1);
  document.querySelectorAll("#chat-title,#detail-character").forEach((node) => (node.textContent = state.character));
  document.querySelectorAll("#chat-avatar,#detail-avatar").forEach((node) => (node.textContent = state.avatar));
  const detailMeta = document.querySelector("#detail-character-meta");
  if (detailMeta) detailMeta.textContent = character.premise || character.voice || "";
  document.querySelectorAll(".character-row").forEach((row) => row.classList.toggle("selected", row.dataset.characterId === character.id));
}
function selectedCharacter() { return state.characters.find((character) => character.id === state.characterId); }
function resetTranscript(label = "新的本機對話已開始") {
  conversations.innerHTML = '<div class="date-divider"><span>新的對話</span></div>';
  state.history = [];
  state.liveSession = false;
  renderChatMemories([]);
  showToast(label);
}
async function startConversation(character) {
  if (!requireLogin()) return false;
  const chatId = `chat-${crypto.randomUUID()}`;
  const response = await fetch("/api/conversations", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, character_id: character.id, character_name: character.name, chat_mode: state.chatMode }),
  });
  if (!response.ok) throw new Error("無法建立本機對話");
  state.chatId = chatId;
  resetTranscript(`${character.name} 已設為目前角色`);
  await loadConversations();
  return true;
}
window.dijiSelectCharacter = async (character, openChat = true) => {
  activeCharacter(character);
  if (!openChat) return;
  try {
    if (!await startConversation(character)) return;
    setChatReady(true); showScreen("chat");
  } catch (error) { showToast(`無法建立對話：${error.message}`); }
};
function message(role, text, timestamp = Date.now()) {
  const article = document.createElement("article");
  article.className = `message ${role}`;
  const meta = document.createElement("div");
  meta.className = "message-meta";
  if (role === "assistant") {
    const avatar = document.createElement("span");
    avatar.className = "initial mini avatar-a";
    avatar.textContent = state.avatar;
    meta.append(avatar);
  }
  const author = document.createElement("strong"); author.textContent = role === "assistant" ? state.character : "你";
  const time = document.createElement("time"); time.textContent = new Date(timestamp).toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit" });
  const copy = document.createElement("p"); copy.textContent = text;
  meta.append(author, time); article.append(meta, copy); conversations.append(article);
  conversations.scrollTop = conversations.scrollHeight;
}
function showTypingIndicator() {
  const article = document.createElement("article");
  article.className = "message assistant typing-indicator";
  article.setAttribute("role", "status");
  article.setAttribute("aria-live", "polite");
  const meta = document.createElement("div");
  meta.className = "message-meta";
  const avatar = document.createElement("span");
  avatar.className = "initial mini avatar-a";
  avatar.textContent = state.avatar;
  const author = document.createElement("strong");
  author.textContent = `${state.character} 正在輸入`;
  meta.append(avatar, author);
  const bubble = document.createElement("div");
  bubble.className = "typing-bubble";
  bubble.setAttribute("aria-label", "角色正在生成回覆");
  for (let index = 0; index < 3; index += 1) {
    const dot = document.createElement("span");
    dot.className = "typing-dot";
    bubble.append(dot);
  }
  article.append(meta, bubble);
  conversations.append(article);
  conversations.scrollTop = conversations.scrollHeight;
  return article;
}
function renderConversation(record) {
  conversations.innerHTML = '<div class="date-divider"><span>已儲存的對話</span></div>';
  state.chatId = record.chat_id;
  state.history = record.messages.map(({ sender_type, text, timestamp }) => ({ sender_type, text, timestamp }));
  state.liveSession = state.history.length > 0;
  setChatMode(record.chat_mode || "story");
  for (const item of record.messages) message(item.sender_type === 1 ? "user" : "assistant", item.text, item.timestamp);
  loadChatMemories();
}
function renderConversationHistory(query = "") {
  const list = document.querySelector("#conversation-history");
  const empty = document.querySelector("#conversation-history-empty");
  const count = document.querySelector("#conversation-history-count");
  if (!list || !empty || !count) return;
  const needle = query.trim().toLocaleLowerCase();
  const records = state.conversations.filter((item) => `${item.character_name} ${item.preview}`.toLocaleLowerCase().includes(needle));
  list.replaceChildren(...records.map((item) => {
    const row = document.createElement("button");
    row.type = "button"; row.className = "chat-row"; row.dataset.chatId = item.chat_id;
    if (item.chat_id === state.chatId) row.classList.add("selected");
    row.innerHTML = '<span class="initial avatar-a"></span><span class="row-copy"><strong></strong><small></small></span><time></time>';
    row.querySelector(".initial").textContent = item.character_name.slice(0, 1);
    row.querySelector("strong").textContent = item.character_name;
    row.querySelector("small").textContent = item.preview;
    row.querySelector("time").textContent = new Date(item.updated_at).toLocaleDateString("zh-TW", { month: "numeric", day: "numeric" });
    row.addEventListener("click", () => openConversation(item.chat_id));
    return row;
  }));
  count.textContent = String(records.length);
  empty.hidden = records.length > 0;
}
async function loadConversations() {
  try {
    const response = await fetch("/api/conversations");
    if (!response.ok) throw new Error("history unavailable");
    state.conversations = await response.json();
    renderConversationHistory(document.querySelector("#search-input")?.value || "");
  } catch { showToast("已聊對話無法載入；請確認本機服務正在執行。"); }
}
async function openConversation(chatId) {
  if (!requireLogin()) return;
  try {
    const response = await fetch(`/api/conversations/${chatId}`);
    if (!response.ok) throw new Error("conversation unavailable");
    const record = await response.json();
    const character = state.characters.find((item) => item.id === record.character_id);
    if (!character) throw new Error("角色已不存在於角色庫");
    activeCharacter(character); renderConversation(record); renderConversationHistory(document.querySelector("#search-input")?.value || "");
    setChatReady(true); showScreen("chat");
  } catch (error) { showToast(`無法開啟對話：${error.message}`); }
}
function interactionPayload(text) {
  const character = selectedCharacter();
  const profile = character?.profile || {};
  return {
    chat_id: state.chatId,
    llm: { model: document.querySelector("#model-input").value.trim() || "deepseek/deepseek-v4.1-flash" },
    character: {
      id: state.characterId, name: state.character, brief_description: character?.premise || "",
      description: character?.full_prompt || JSON.stringify(profile), place_description: "",
      category: { id: 0, name: character?.source?.generated_file ? "ai-server 匯入" : "未分類", is_nsfw: false },
      sample_dialog: Array.isArray(profile.language_style) ? profile.language_style.slice(0, 10).map((line) => ({ sender_type: 2, text: String(line).slice(0, 800) })) : [],
      psychological_evolution: profile.psychological_evolution || null,
      behavioral_boundaries: profile.behavioral_boundaries || null,
      evolution_requirements: profile.evolution_requirements || null,
    },
    user: { id: "local-user", persona: { name: "使用者", chat_mode: state.chatMode } },
    message: { sender_id: "local-user", text }, history: state.history,
    style_prompt: character?.style_guide || undefined, experiment_id: state.experimentId,
    is_nsfw: document.querySelector("#chat-adult").checked,
    enable_favorability: document.querySelector("#chat-favorability").checked,
  };
}
function setChatMode(mode) {
  state.chatMode = mode === "dialog" ? "dialog" : "story";
  document.querySelectorAll("[data-chat-mode]").forEach((button) => {
    const selected = button.dataset.chatMode === state.chatMode;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-checked", String(selected));
  });
  const status = document.querySelector("#chat-mode-status");
  if (status) status.textContent = state.chatMode === "story" ? "長對話" : "短對話";
}
async function saveChatMode(mode) {
  const previousMode = state.chatMode;
  setChatMode(mode);
  if (!state.chatId || state.chatId === "preview") return;
  try {
    const response = await fetch(`/api/conversations/${state.chatId}/mode`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ chat_mode: state.chatMode }),
    });
    if (!response.ok) throw new Error("無法儲存對話設定");
    showToast(`已切換為${state.chatMode === "story" ? "長對話" : "短對話"}`);
    await loadConversations();
  } catch (error) {
    setChatMode(previousMode);
    showToast(`對話模式未變更：${error.message}`);
  }
}
function setComposerBusy(busy) {
  const send = document.querySelector(".send-button"), input = document.querySelector("#chat-input");
  send.disabled = busy; input.disabled = busy; send.querySelector("span").textContent = busy ? "傳送中…" : "送出";
}
function renderSidebarCharacters() {
  const library = document.querySelector(".chat-list .character-library");
  if (!library) return;
  library.querySelectorAll(".character-row").forEach((row) => row.remove());
  for (const character of state.characters) {
    const row = document.createElement("button");
    row.type = "button"; row.className = "character-row"; row.dataset.characterId = character.id;
    row.innerHTML = '<span class="initial avatar-a"></span><span><strong></strong><small></small></span>';
    row.querySelector(".initial").textContent = character.name.slice(0, 1);
    row.querySelector("strong").textContent = character.name;
    row.querySelector("small").textContent = character.premise;
    row.addEventListener("click", () => window.dijiSelectCharacter(character));
    library.append(row);
  }
}
function renderRolePicker(query = "") {
  const grid = document.querySelector("#role-picker-grid");
  const status = document.querySelector("#role-picker-status");
  const empty = document.querySelector("#role-picker-empty");
  if (!grid || !status || !empty) return;
  const createCard = document.querySelector("#role-picker-create");
  const needle = query.trim().toLocaleLowerCase();
  const characters = state.characters.filter((character) => `${character.name} ${character.premise}`.toLocaleLowerCase().includes(needle));
  grid.replaceChildren(...characters.map((character) => {
    const card = document.createElement("button");
    card.type = "button"; card.className = "role-picker-card";
    if (character.source?.visibility === "private") card.classList.add("personal-character");
    card.innerHTML = '<span class="initial avatar-a"></span><span class="role-picker-copy"><strong></strong><small></small><em>開始對話</em></span><span class="role-picker-arrow" aria-hidden="true">›</span>';
    card.querySelector(".initial").textContent = character.name.slice(0, 1);
    card.querySelector("strong").textContent = character.name;
    card.querySelector("small").textContent = character.premise;
    if (character.source?.visibility === "private") card.querySelector("em").textContent = "我的角色 · 僅自己可見";
    card.addEventListener("click", () => window.dijiSelectCharacter(character));
    return card;
  }));
  if (createCard) grid.append(createCard);
  status.textContent = `共 ${characters.length} 位可選角色`;
  empty.hidden = characters.length > 0;
}
async function loadLocalCatalog() {
  try {
    const response = await fetch("/api/characters");
    if (!response.ok) throw new Error("catalog unavailable");
    state.characters = await response.json();
    const character = state.characters.find((item) => item.id === state.characterId);
    if (character) activeCharacter(character);
    renderSidebarCharacters();
    renderRolePicker();
    window.dijiRenderCharacterLibrary?.();
  } catch { showToast("角色庫無法載入；請確認以本機網址開啟。"); }
}
async function loadInteractionModels() {
  const select = document.querySelector("#model-input");
  const status = document.querySelector("#model-jailbreak-status");
  try {
    const response = await fetch("/api/jailbreaks");
    if (!response.ok) throw new Error("jailbreak unavailable");
    const presets = (await response.json())
      .filter((item) => item.review_status === "approved" && item.prompt)
      .sort((left, right) => right.last_updated.localeCompare(left.last_updated));
    const choices = presets.flatMap((preset) => preset.openrouter_models.map((model) => ({ model, preset })));
    select.replaceChildren(...choices.map(({ model, preset }) => new Option(`${model} · 越獄：${preset.name}`, model)));
    const defaultChoice = choices.find((choice) => choice.model === "deepseek/deepseek-v4.1-flash") || choices[0];
    if (!defaultChoice) throw new Error("no approved models");
    select.value = defaultChoice.model;
    select.disabled = false;
    const describe = () => {
      const choice = choices.find((item) => item.model === select.value);
      state.jailbreakId = choice?.preset.id || null;
      state.experimentId = null;
      status.textContent = choice ? `成人虛構互動時，後端會套用「${choice.preset.name}」越獄（更新：${choice.preset.last_updated}）。` : "找不到此模型的已核准越獄。";
    };
    select.addEventListener("change", describe);
    describe();
    refreshChatProviderState();
  } catch (error) {
    select.replaceChildren(new Option("沒有可用的已核准模型", ""));
    select.disabled = true;
    status.textContent = "尚無可用模型；請在越獄工作台完成文字編輯與核准。";
  }
}
async function loadMemories() {
  const list = document.querySelector("#memory-list"), empty = document.querySelector("#memory-empty");
  try {
    const response = await fetch(`/api/memories/${state.chatId}`);
    if (!response.ok) throw new Error("memory unavailable");
    const memories = await response.json();
    list.replaceChildren(...memories.map((memory) => {
      const item = document.createElement("article"); item.className = "memory-card";
      item.innerHTML = `<p>${memory.type} · ${memory.timestamp}</p><h2></h2><small></small>`;
      item.querySelector("h2").textContent = memory.summary;
      item.querySelector("small").textContent = Object.entries(memory.keywords).map(([key, value]) => `${key}：${value}`).join(" · ");
      return item;
    }));
    empty.hidden = memories.length > 0;
  } catch { list.replaceChildren(); empty.hidden = false; }
}
function renderChatMemories(memories) {
  const list = document.querySelector("#chat-memory-list");
  const empty = document.querySelector("#chat-memory-empty");
  if (!list || !empty) return;
  list.replaceChildren(...memories.map((memory) => {
    const item = document.createElement("article");
    item.className = "chat-memory-item";
    const meta = document.createElement("p");
    meta.textContent = `${memory.type} · ${memory.timestamp}`;
    const summary = document.createElement("strong");
    summary.textContent = memory.summary;
    item.append(meta, summary);
    return item;
  }));
  empty.hidden = memories.length > 0;
  const canBackfill = memories.length === 0 && state.chatId !== "preview" && state.history.length > 0;
  chatMemoryBackfill.hidden = !canBackfill;
  chatMemoryBackfillNote.hidden = !canBackfill;
  if (!canBackfill) chatMemoryBackfillStatus.textContent = "";
}
async function loadChatMemories() {
  try {
    const response = await fetch(`/api/memories/${state.chatId}`);
    if (!response.ok) throw new Error("memory unavailable");
    renderChatMemories(await response.json());
  } catch {
    renderChatMemories([]);
  }
}

document.querySelectorAll("[data-view]").forEach((button) => button.addEventListener("click", () => { showScreen(button.dataset.view); if (compactMobileNav.matches) setMobileNav(false); }));
document.querySelector("#home-start").addEventListener("click", () => {
  const next = document.querySelector('#home-start').dataset.next;
  if (!authenticatedUser) { rememberPendingTask('chat'); openLoginDialog(); }
  else if (next !== 'chat') { rememberPendingTask('chat'); showScreen('connections'); }
  else openRolePicker();
});
document.querySelector(".logo").addEventListener("click", (event) => {
  event.preventDefault();
  showScreen("home");
  window.location.hash = "home";
});
const content = document.querySelector(".content");
const compactDetails = window.matchMedia("(max-width:1120px)");
const compactMobileNav = window.matchMedia("(max-width:760px)");
const detailsPanel = document.querySelector("#details-panel");
const detailsBackdrop = document.querySelector("#details-backdrop");
const detailsToggle = document.querySelector("#toggle-details");
const app = document.querySelector(".app");
const compactChatList = window.matchMedia("(max-width:960px)");
const chatList = document.querySelector("#chat-list");
const chatListBackdrop = document.querySelector("#chat-list-backdrop");
const chatListToggle = document.querySelector("#toggle-chat-list");
const mobileNavBackdrop = document.querySelector("#mobile-nav-backdrop");
const mobileNavToggle = document.querySelector("#toggle-mobile-nav");
const chatMemoryToggle = document.querySelector("#toggle-chat-memory");
const chatMemoryPanel = document.querySelector("#chat-memory-panel");
chatMemoryToggle.addEventListener("click", () => {
  const expanded = chatMemoryToggle.getAttribute("aria-expanded") === "true";
  chatMemoryToggle.setAttribute("aria-expanded", String(!expanded));
  chatMemoryToggle.textContent = expanded ? "展開" : "收合";
  chatMemoryPanel.hidden = expanded;
  if (!expanded) loadChatMemories();
});
chatMemoryBackfill.addEventListener("click", async () => {
  if (state.chatId === "preview" || state.history.length === 0) return;
  chatMemoryBackfill.disabled = true;
  chatMemoryBackfillStatus.textContent = "正在從既有對話建立事件記憶…";
  try {
    const response = await fetch(`/api/memories/${state.chatId}/backfill`, { method: "POST" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "無法建立記憶");
    await loadChatMemories();
    chatMemoryBackfillStatus.textContent = payload.skipped ? "這段對話已有事件記憶。" : `已建立 ${payload.created} 筆事件記憶。`;
  } catch (error) {
    chatMemoryBackfillStatus.textContent = `建立記憶失敗：${error.message}`;
  } finally {
    chatMemoryBackfill.disabled = false;
  }
});
function mobileNavIsOpen() { return compactMobileNav.matches && app.classList.contains("mobile-nav-open"); }
function setMobileNav(open) {
  const visible = compactMobileNav.matches && open;
  app.classList.toggle("mobile-nav-open", visible);
  mobileNavToggle.setAttribute("aria-expanded", String(visible));
  mobileNavBackdrop.hidden = !visible;
  syncOverlayLock();
  if (visible) window.requestAnimationFrame(() => document.querySelector(".rail-nav .rail-button.active").focus());
}
function isChatListAvailable() {
  const chatScreen = document.querySelector('.screen[data-screen="chat"].active');
  return chatScreen !== null && !chatScreen.classList.contains("awaiting-character");
}
function chatListIsOpen() {
  if (!isChatListAvailable()) return false;
  return compactChatList.matches ? app.classList.contains("chat-list-open") : app.classList.contains("chat-list-visible");
}
function syncOverlayLock() { document.body.classList.toggle("mobile-overlay-open", mobileNavIsOpen() || chatListIsOpen() || (compactDetails.matches && detailsAreOpen())); }
function setChatList(open) {
  const inChat = isChatListAvailable();
  const visible = inChat && open;
  const compactVisible = compactChatList.matches && visible;
  app.classList.toggle("chat-list-open", compactVisible);
  app.classList.toggle("chat-list-visible", !compactChatList.matches && visible);
  chatListToggle.setAttribute("aria-expanded", String(visible));
  chatListToggle.setAttribute("aria-label", visible ? "關閉角色與對話列表" : "開啟角色與對話列表");
  chatListToggle.title = visible ? "關閉角色與對話列表" : "開啟角色與對話列表";
  chatList.setAttribute("aria-hidden", String(!visible));
  chatListBackdrop.hidden = !compactVisible;
  syncOverlayLock();
  if (compactVisible) window.requestAnimationFrame(() => document.querySelector("#close-chat-list").focus());
}
function detailsAreOpen() { return compactDetails.matches ? content.classList.contains("details-open") : !content.classList.contains("details-hidden"); }
function setDetails(open) {
  if (compactDetails.matches) { content.classList.toggle("details-open", open); content.classList.remove("details-hidden"); }
  else { content.classList.toggle("details-hidden", !open); content.classList.remove("details-open"); }
  detailsToggle.setAttribute("aria-expanded", String(open));
  detailsPanel.setAttribute("aria-hidden", String(compactDetails.matches && !open));
  detailsBackdrop.hidden = !compactDetails.matches || !open;
  syncOverlayLock();
  if (compactDetails.matches && open) window.requestAnimationFrame(() => document.querySelector("#close-details").focus());
}
if (compactDetails.matches) setDetails(false);
if (compactChatList.matches) setChatList(false);
else setChatList(true);
if (compactMobileNav.matches) setMobileNav(false);
detailsToggle.addEventListener("click", () => { if (!detailsAreOpen()) { setChatList(false); setMobileNav(false); } setDetails(!detailsAreOpen()); });
document.querySelector("#close-details").addEventListener("click", () => { setDetails(false); detailsToggle.focus(); });
detailsBackdrop.addEventListener("click", () => { setDetails(false); detailsToggle.focus(); });
chatListToggle.addEventListener("click", () => { if (!chatListIsOpen() && compactChatList.matches) { setDetails(false); setMobileNav(false); } setChatList(!chatListIsOpen()); });
document.querySelector("#close-chat-list").addEventListener("click", () => { setChatList(false); chatListToggle.focus(); });
chatListBackdrop.addEventListener("click", () => { setChatList(false); chatListToggle.focus(); });
chatList.addEventListener("click", (event) => { if (compactChatList.matches && event.target.closest("button:not(#close-chat-list), a")) setChatList(false); });
mobileNavToggle.addEventListener("click", () => { if (!mobileNavIsOpen()) { setChatList(false); setDetails(false); } setMobileNav(!mobileNavIsOpen()); });
mobileNavBackdrop.addEventListener("click", () => { setMobileNav(false); mobileNavToggle.focus(); });
window.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    if (mobileNavIsOpen()) { setMobileNav(false); mobileNavToggle.focus(); }
    else if (chatListIsOpen()) { setChatList(false); chatListToggle.focus(); }
    else if (compactDetails.matches && detailsAreOpen()) { setDetails(false); detailsToggle.focus(); }
  }
});
compactDetails.addEventListener("change", (event) => setDetails(!event.matches));
compactChatList.addEventListener("change", (event) => setChatList(!event.matches && isChatListAvailable()));
compactMobileNav.addEventListener("change", () => setMobileNav(false));
document.querySelector("#new-chat").addEventListener("click", () => { setChatReady(false); showScreen("chat"); });
document.querySelector("#new-session").addEventListener("click", () => { const character = selectedCharacter(); if (character) startConversation(character).catch((error) => showToast(`無法建立對話：${error.message}`)); });
document.querySelector("#clear-chat").addEventListener("click", () => { const character = selectedCharacter(); if (character) startConversation(character).catch((error) => showToast(`無法建立對話：${error.message}`)); });
document.querySelector("#search-input").addEventListener("input", (event) => { renderConversationHistory(event.target.value); renderRolePicker(event.target.value); });
document.querySelector("#role-picker-search").addEventListener("input", (event) => renderRolePicker(event.target.value));
document.querySelector("#role-picker-create").addEventListener("click", () => showScreen("create-character"));
const loginDialog = document.querySelector("#google-login-dialog");
const loginStatus = document.querySelector("#google-login-status");
const accountLogin = document.querySelector("#account-login");
const accountLoginLabel = document.querySelector("#account-login-label");
const accountStatus = document.querySelector("#account-status");
let authenticatedUser = null;

function updateAccountAccess() {
  updateHomeJourney();
  const signedIn = Boolean(authenticatedUser);
  accountLogin.hidden = signedIn;
  document.querySelectorAll("[data-auth-logout]").forEach((button) => { button.hidden = !signedIn; });
  if (signedIn) {
    const name = authenticatedUser.display_name || "Google 使用者";
    accountLoginLabel.textContent = name;
    accountStatus.textContent = `已登入為 ${name}；角色、對話與記憶會保存到你的 DIJI 帳號。可在左側「模型連線」管理自己的額度。`;
    return;
  }
  accountLoginLabel.textContent = "登入";
  accountStatus.textContent = "登入後可建立並保存角色對話與記憶，並在「模型連線」連接自己的額度。";
}
function openLoginDialog(message = "") {
  loginStatus.textContent = message;
  if (!loginDialog.open) loginDialog.showModal();
}
function requireLogin() {
  if (authenticatedUser) return true;
  openLoginDialog("登入後即可建立與保存對話。");
  return false;
}
async function loadAuthentication() {
  if (window.location.protocol === "file:") {
    authenticatedUser = null;
    updateAccountAccess();
    return false;
  }
  try {
    const response = await fetch("/api/auth/session", { cache: "no-store" });
    if (!response.ok) throw new Error("無法確認登入狀態");
    const data = await response.json();
    authenticatedUser = data.user;
    updateAccountAccess();
    return Boolean(data.authenticated);
  } catch (error) {
    authenticatedUser = null;
    updateAccountAccess();
    loginStatus.textContent = `無法確認登入狀態：${error.message}`;
    return false;
  }
}
accountLogin.addEventListener("click", () => openLoginDialog());
document.querySelectorAll("[data-google-login-close]").forEach((button) => button.addEventListener("click", () => loginDialog.close()));
loginDialog.addEventListener("click", (event) => { if (event.target === loginDialog) loginDialog.close(); });
document.querySelector("#google-login").addEventListener("click", () => {
  if (window.location.protocol === "file:") {
    loginStatus.textContent = "原始檔預覽不能登入；請改用已部署的 DIJI 網站。";
    return;
  }
  loginStatus.textContent = "正在前往 Google…";
  try { sessionStorage.setItem('diji-login-return', '1'); } catch {}
  window.location.assign("/api/auth/google/start");
});
document.querySelectorAll("[data-auth-logout]").forEach((button) => button.addEventListener("click", async () => {
  await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
  authenticatedUser = null;
  updateAccountAccess();
  state.characters = [];
  await loadLocalCatalog();
  setChatReady(false);
  showToast("你已登出此裝置。");
}));
document.querySelector("#chat-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = document.querySelector("#chat-input"), text = input.value.trim();
  if (!text) return;
  if (!requireLogin()) return;
  if (!await refreshChatProviderState()) { showToast("請先設定模型商連線，再傳送訊息。"); showScreen("connections"); return; }
  const payload = interactionPayload(text);
  if (!state.liveSession) { conversations.innerHTML = '<div class="date-divider"><span>本機互動</span></div>'; state.liveSession = true; }
  const timestamp = Date.now(); message("user", text, timestamp); state.history.push({ sender_type: 1, text, timestamp }); input.value = ""; setComposerBusy(true);
  const typingIndicator = showTypingIndicator();
  try {
    const response = await fetch("/api/interactions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    const body = await response.text();
    let data = {};
    try { data = body ? JSON.parse(body) : {}; } catch { data = { detail: body }; }
    if (!response.ok) throw new Error(data.detail || `互動請求失敗（HTTP ${response.status}）`);
    typingIndicator.remove();
    const replyTimestamp = Date.now(); message("assistant", data.text, replyTimestamp); state.history.push({ sender_type: 2, text: data.text, timestamp: replyTimestamp });
    loadChatMemories();
  } catch (error) { typingIndicator.remove(); showToast(`模型回覆未完成：${error.message}；你的訊息已保存在本機。`); } finally { setComposerBusy(false); loadConversations(); }
});
document.querySelector("#chat-input").addEventListener("keydown", (event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); document.querySelector("#chat-form").requestSubmit(); } });
document.querySelector("#chat-input").addEventListener("input", (event) => { event.target.style.height = "auto"; event.target.style.height = `${Math.min(event.target.scrollHeight, 160)}px`; });
document.querySelectorAll("[data-chat-mode]").forEach((button) => button.addEventListener("click", () => saveChatMode(button.dataset.chatMode)));
setChatProviderLocked(true, '正在確認模型商連接狀態…');
loadAuthentication().then((signedIn) => {
  refreshChatProviderState();
  loadLocalCatalog();
  loadInteractionModels();
  if (signedIn) loadConversations();
  else renderConversationHistory();
  const destination = window.location.hash.slice(1);
  if (['home','chat','characters','memory','jailbreak','settings','connections','create-character'].includes(destination)) showScreen(destination);
  try {
    if (signedIn && sessionStorage.getItem('diji-login-return') === '1') {
      sessionStorage.removeItem('diji-login-return');
      if (pendingTask()) showScreen('connections');
    }
  } catch {}
});
window.addEventListener('popstate', () => showScreen(window.location.hash.slice(1) || 'home'));
document.querySelector('#model-input').addEventListener('change', refreshChatProviderState);

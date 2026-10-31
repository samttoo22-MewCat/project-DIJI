from pathlib import Path
import subprocess


ROOT = Path(__file__).parents[1]


def test_local_ui_has_the_required_assets() -> None:
    for path in ("ui/index.html", "ui/styles.css", "ui/responsive.css", "ui/home.css", "ui/pwa.css", "ui/pwa.js", "ui/service-worker.js", "ui/manifest.webmanifest", "ui/icons/diji-icon.svg", "ui/icons/diji-180.png", "ui/icons/diji-192.png", "ui/icons/diji-512.png", "ui/live-interaction.css", "ui/role-picker.css", "ui/conversation-history.css", "ui/settings.css", "ui/account-access.css", "ui/age-confirmation.css", "ui/age-confirmation.js", "ui/jailbreak-catalog.css", "ui/jailbreak-studio.css", "ui/jailbreak-studio-overrides.css", "ui/jailbreak-delete.css", "ui/character-import.css", "ui/jailbreak-studio.js", "ui/app.js", "ui_server.py", "deploy/diji-ui.service", "scripts/install-user-service", "scripts/diji-healthcheck"):
        assert (ROOT / path).is_file()


def test_pwa_installation_caches_only_the_static_shell() -> None:
    markup = (ROOT / "ui/index.html").read_text()
    script = (ROOT / "ui/pwa.js").read_text()
    worker = (ROOT / "ui/service-worker.js").read_text()
    manifest = (ROOT / "ui/manifest.webmanifest").read_text()

    assert 'rel="manifest" href="/manifest.webmanifest"' in markup
    assert 'rel="apple-touch-icon" href="/icons/diji-180.png"' in markup
    assert 'data-pwa-install' in markup
    assert 'id="pwa-install-guide"' in markup
    assert 'serviceWorker.register("/service-worker.js", { scope: "/" })' in script
    assert "appInstalled = true" in script
    assert "if (!appInstalled)" in script
    assert 'beforeinstallprompt' in script
    assert '加入主畫面' in script
    assert 'url.pathname.startsWith("/api/")' in worker
    assert 'User data, sessions and all model APIs stay network-only.' in worker
    assert '"display": "standalone"' in manifest
    assert '"/icons/diji-512.png"' in manifest


def test_pwa_keeps_install_entry_until_the_browser_confirms_installation() -> None:
    harness = r'''
const fs = require("fs");
const vm = require("vm");
const listeners = {};
function button() { return { hidden: true, textContent: "", disabled: false, addEventListener(name, callback) { if (name === "click") this.click = callback; } }; }
const buttons = [button(), button()];
const guide = { open: false, addEventListener() {}, showModal() { this.open = true; }, close() { this.open = false; } };
const guideTitle = { textContent: "" };
const guideIntro = { textContent: "" };
const iosGuide = { hidden: false };
const browserGuide = { hidden: true };
const document = {
  querySelectorAll(selector) {
    if (selector === "[data-pwa-install]") return buttons;
    if (selector === "[data-pwa-guide-close]") return [];
    return [];
  },
  querySelector(selector) {
    if (selector === "#pwa-install-guide") return guide;
    if (selector === "[data-pwa-guide-title]") return guideTitle;
    if (selector === "[data-pwa-guide-intro]") return guideIntro;
    if (selector === "[data-pwa-guide-ios]") return iosGuide;
    if (selector === "[data-pwa-guide-browser]") return browserGuide;
    return null;
  },
};
const window = {
  navigator: { userAgent: "Mozilla/5.0 Chrome/140", standalone: false },
  location: { protocol: "https:" },
  matchMedia() { return { matches: false }; },
  addEventListener(name, callback) { listeners[name] = callback; },
  setTimeout() {},
};
const navigator = { serviceWorker: { register() { return Promise.resolve(); } } };
vm.runInNewContext(fs.readFileSync("ui/pwa.js", "utf8"), { window, document, navigator, Promise, Set, console });
listeners.beforeinstallprompt({ preventDefault() {}, prompt: async () => {}, userChoice: Promise.resolve({ outcome: "accepted" }) });
(async () => {
  await buttons[0].click();
  if (buttons.some((item) => item.hidden)) throw new Error("install entry disappeared before appinstalled");
  if (buttons.some((item) => item.textContent !== "Web App 安裝中…" || !item.disabled)) throw new Error("installing state is not visible");
  if (guide.open) throw new Error("fallback instructions opened before installation had time to finish");
})().catch((error) => { console.error(error.message); process.exit(1); });
'''
    result = subprocess.run(["node", "-e", harness], cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


def test_ui_is_explicitly_local_only() -> None:
    source = (ROOT / "ui_server.py").read_text()
    assert "127.0.0.1" in source
    assert "openai" not in source.lower()


def test_age_confirmation_uses_an_optional_secure_cookie_and_requires_acceptance() -> None:
    markup = (ROOT / "ui/index.html").read_text()
    stylesheet = (ROOT / "ui/age-confirmation.css").read_text()
    script = (ROOT / "ui/age-confirmation.js").read_text()

    assert 'id="age-confirmation"' in markup
    assert 'id="age-confirmation-accepted"' in markup
    assert 'id="age-confirmation-remember"' in markup
    assert 'id="age-confirmation-submit"' in markup
    assert 'id="reset-age-confirmation"' in markup
    assert 'age-confirmation.js?v=20261028-age-gate-2' in markup
    assert "AGE_COOKIE_NAME = \"diji_age_confirmed\"" in script
    assert "Max-Age=${AGE_COOKIE_MAX_AGE}; Path=/; SameSite=Lax${secure}" in script
    assert 'window.location.protocol === "https:"' in script
    assert "ageSubmit.disabled = !ageAccepted.checked" in script
    assert "ageDialog.showModal()" in script
    assert 'ageDialog.addEventListener("cancel"' in script
    assert "clearAgeConfirmation" in script
    assert "age-confirmation::backdrop" in stylesheet
    assert "min-height: 48px" in stylesheet

    harness = r'''
const fs = require("fs");
const vm = require("vm");
const listeners = {};
const dialog = { open: false, showModal() { this.open = true; }, close() { this.open = false; }, addEventListener(name, callback) { listeners.cancel = callback; } };
const accepted = { checked: false, addEventListener(name, callback) { listeners.accept = callback; } };
const remember = { checked: true };
const submit = { disabled: true, addEventListener(name, callback) { listeners.submit = callback; } };
const reset = { addEventListener(name, callback) { listeners.reset = callback; } };
let cookie = "";
const document = {
  get cookie() { return cookie; },
  set cookie(value) { cookie = value; },
  querySelector(selector) {
    return { "#age-confirmation": dialog, "#age-confirmation-accepted": accepted, "#age-confirmation-remember": remember, "#age-confirmation-submit": submit, "#reset-age-confirmation": reset }[selector] || null;
  },
};
const window = { location: { protocol: "https:" } };
vm.runInNewContext(fs.readFileSync("ui/age-confirmation.js", "utf8"), { document, window });
if (!dialog.open || !submit.disabled) throw new Error("age gate should block until acceptance");
accepted.checked = true;
listeners.accept();
if (submit.disabled) throw new Error("accepted age should enable submit");
remember.checked = true;
listeners.submit();
if (dialog.open || !cookie.includes("diji_age_confirmed=1") || !cookie.includes("Secure")) throw new Error("remembered confirmation was not persisted safely");
listeners.reset();
if (!dialog.open || !submit.disabled || !cookie.includes("Max-Age=0")) throw new Error("reset should clear the remembered confirmation and reopen the gate");
'''
    result = subprocess.run(["node", "-e", harness], cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


def test_mobile_forms_keep_a_touch_safe_font_size() -> None:
    responsive = (ROOT / "ui/responsive.css").read_text()
    live_interaction = (ROOT / "ui/live-interaction.css").read_text()

    assert "font-size: 16px" in responsive
    assert ".connection-field input,.connection-field select" in live_interaction


def test_mobile_navigation_and_details_drawer_are_reachable() -> None:
    markup = (ROOT / "ui/index.html").read_text()
    responsive = (ROOT / "ui/responsive.css").read_text()
    script = (ROOT / "ui/app.js").read_text()

    assert 'id="details-backdrop"' in markup
    assert ".rail-footer { display: block;" in responsive
    assert "position: fixed; z-index: 10; top: 60px" in responsive
    assert "detailsBackdrop.addEventListener(\"click\"" in script
    assert 'event.key === "Escape"' in script
    assert 'detailsPanel.setAttribute("aria-hidden"' in script


def test_compact_layout_has_an_accessible_left_list_drawer_and_readable_copy() -> None:
    markup = (ROOT / "ui/index.html").read_text()
    responsive = (ROOT / "ui/responsive.css").read_text()
    script = (ROOT / "ui/app.js").read_text()

    assert 'id="toggle-chat-list"' in markup
    assert 'id="chat-list-backdrop"' in markup
    assert ".app.chat-list-open .chat-list" in responsive
    assert "width: min(340px, 88vw)" in responsive
    assert "--muted: #bac8d8" in responsive
    assert ".chat-list .character-row small" in responsive
    assert "chatListBackdrop.addEventListener" in script
    assert "chatListToggle.addEventListener" in script
    assert 'id="toggle-mobile-nav"' in markup
    assert 'id="mobile-nav-backdrop"' in markup
    assert ".app.mobile-nav-open .rail" in responsive
    assert "flex-direction: column" in responsive
    assert "mobileNavBackdrop.addEventListener" in script
    assert "responsive.css?v=20261030-openrouter-1" in markup
    assert "app.js?v=20261030-openrouter-1" in markup
    assert ".app.chat-list-visible" in responsive
    assert 'name !== "chat"' in script
    assert 'app.classList.toggle("chat-list-visible"' in script
    assert "function isChatListAvailable()" in script
    assert 'document.querySelector(".logo").addEventListener("click"' in script
    assert 'setChatReady(false);' in script


def test_conversation_settings_labels_are_large_and_the_logo_returns_home() -> None:
    responsive = (ROOT / "ui/responsive.css").read_text()
    markup = (ROOT / "ui/index.html").read_text()

    assert ".live-switch { min-height: 44px; gap: 12px; font-size: 18px;" in responsive
    assert ".live-switch input { width: 20px; height: 20px; }" in responsive
    assert "app.js?v=20261030-openrouter-1" in markup


def test_studio_subpage_secondary_copy_is_readable() -> None:
    responsive = (ROOT / "ui/responsive.css").read_text()

    assert "Studio subpages use readable secondary copy" in responsive
    assert ".studio-screen .jailbreak-editor label" in responsive
    assert ".studio-screen .jailbreak-library p" in responsive
    assert "Description copy is deliberately two type steps larger" in responsive
    assert "font-size: 17px; line-height: 1.72" in responsive
    assert "font-size: 18px;" in responsive
    assert "@media (max-width: 760px)" in responsive


def test_local_deployment_healthcheck_waits_for_server_startup() -> None:
    healthcheck = (ROOT / "scripts/diji-healthcheck").read_text()

    assert "time.monotonic() + 10" in healthcheck
    assert "time.sleep(0.5)" in healthcheck


def test_user_service_loads_the_local_environment_file() -> None:
    service = (ROOT / "deploy/diji-ui.service").read_text()

    assert "EnvironmentFile=%h/project-DIJI/.env" in service


def test_live_interaction_is_explicitly_opt_in() -> None:
    markup = (ROOT / "ui/index.html").read_text()
    script = (ROOT / "ui/app.js").read_text()

    assert 'id="live-mode"' in markup
    assert 'id="model-input"' in markup
    assert '<select id="model-input"' in markup
    assert 'document.querySelector("#live-mode").checked' in script
    assert 'fetch("/api/interactions"' in script
    assert 'fetch("/api/jailbreaks")' in script
    assert 'id="chat-adult" type="checkbox" checked' in markup
    assert "是否開啟色情內容" in markup
    assert 'id="chat-favorability" type="checkbox"' in markup
    assert 'id="chat-favorability" type="checkbox" checked' not in markup
    assert "function showTypingIndicator()" in script
    assert "typing-indicator" in script
    assert "typingIndicator.remove()" in script


def test_chat_mode_is_a_visible_per_conversation_long_or_short_choice() -> None:
    markup = (ROOT / "ui/index.html").read_text()
    script = (ROOT / "ui/app.js").read_text()
    responsive = (ROOT / "ui/responsive.css").read_text()

    assert 'data-chat-mode="story"' in markup
    assert 'data-chat-mode="dialog"' in markup
    assert "長對話" in markup and "短對話" in markup
    assert 'chat_mode: state.chatMode' in script
    assert 'fetch(`/api/conversations/${state.chatId}/mode`' in script
    assert ".chat-mode-card.active" in responsive
    assert "@media (min-width: 761px)" in responsive
    assert ".chat-mode-grid { grid-template-columns: 1fr; }" in responsive
    assert ".chat-mode-card small { font-size: 14px; line-height: 1.55; }" in responsive
    assert "responsive.css?v=20261030-openrouter-1" in markup


def test_chat_has_distinct_left_list_and_right_settings_controls() -> None:
    markup = (ROOT / "ui/index.html").read_text()
    responsive = (ROOT / "ui/responsive.css").read_text()

    assert "此對話設定" in markup
    assert 'class="chat-side-control chat-list-toggle"' in markup
    assert 'class="chat-side-control chat-settings-toggle"' in markup
    assert "Chat uses two distinct edge controls" in responsive


def test_chat_messages_preserve_model_paragraph_breaks() -> None:
    styles = (ROOT / "ui/styles.css").read_text()
    responsive = (ROOT / "ui/responsive.css").read_text()

    assert ".message p" in styles
    assert "white-space:pre-wrap" in styles
    assert ".typing-bubble" in responsive
    assert "@keyframes diji-typing" in responsive


def test_chat_details_can_open_current_conversation_memories() -> None:
    markup = (ROOT / "ui/index.html").read_text()
    script = (ROOT / "ui/app.js").read_text()
    responsive = (ROOT / "ui/responsive.css").read_text()

    assert 'id="toggle-chat-memory"' in markup
    assert 'id="chat-memory-panel" hidden' in markup
    assert 'id="chat-memory-list"' in markup
    assert 'id="chat-memory-backfill"' in markup
    assert "function loadChatMemories()" in script
    assert 'fetch(`/api/memories/${state.chatId}`)' in script
    assert 'fetch(`/api/memories/${state.chatId}/backfill`, { method: "POST" })' in script
    assert 'chatMemoryToggle.addEventListener("click"' in script
    assert ".chat-memory-panel" in responsive


def test_mobile_chat_uses_drawers_and_a_touch_safe_composer() -> None:
    responsive = (ROOT / "ui/responsive.css").read_text()

    assert "Mobile Web App shell" in responsive
    assert ".content.details-open .details { transform: translateY(0); }" in responsive
    assert ".app.chat-list-open .chat-list" in responsive
    assert "min-height: 68px" in responsive
    assert "env(safe-area-inset-bottom)" in responsive


def test_ui_uses_a_user_requested_google_login_without_browser_key_storage() -> None:
    markup = (ROOT / "ui/index.html").read_text()
    script = (ROOT / "ui/app.js").read_text()

    assert 'id="auth-gate"' not in markup
    assert 'id="account-login"' in markup
    assert 'id="google-login-dialog"' in markup
    assert 'id="google-login"' in markup
    assert "OpenRouter 登入" not in markup
    assert "app.js?v=20261030-openrouter-1" in markup
    assert 'fetch("/api/auth/session", { cache: "no-store" })' in script
    assert 'window.location.protocol === "file:"' in script
    assert 'window.location.assign("/api/auth/google/start")' in script
    assert 'fetch("/api/auth/google/start"' not in script
    assert 'fetch("/api/auth/logout"' in script
    assert "function requireLogin()" in script
    assert "localStorage" not in script


def test_ui_exposes_jailbreak_catalog_without_auto_injection() -> None:
    script = (ROOT / "ui/jailbreak-studio.js").read_text()

    assert 'fetch("/api/jailbreaks")' in script
    assert 'review_status === "approved"' in script
    assert 'ui-jailbreak' in script


def test_jailbreak_has_an_independent_editor() -> None:
    markup = (ROOT / "ui/index.html").read_text()
    script = (ROOT / "ui/jailbreak-studio.js").read_text()
    styles = (ROOT / "ui/jailbreak-studio.css").read_text()

    assert 'data-view="jailbreak"' in markup
    assert 'fetch(`/api/jailbreaks/${record.id}`' in script
    assert '建立本機越獄' in script
    assert 'method: "DELETE"' in script
    assert "jailbreak-studio.css?v=20261018-actions-aligned-1" in markup
    assert "grid-template-columns:repeat(3,max-content)" in styles
    assert ".jailbreak-editor-actions>button{display:inline-flex" in styles


def test_ui_exposes_a_reviewed_ai_server_character_import() -> None:
    markup = (ROOT / "ui/index.html").read_text()
    source = (ROOT / "src/diji/local_app.py").read_text()

    assert 'id="character-import-panel"' in markup
    assert '"/api/character-imports/preview"' in source
    assert '"/api/character-imports"' in source


def test_ui_exposes_three_step_character_creator() -> None:
    markup = (ROOT / "ui/index.html").read_text()
    script = (ROOT / "ui/character-creator.js").read_text()

    assert 'id="character-creator"' in markup
    assert '創作簡報' in markup and '審核草稿' in markup and '儲存角色' in markup
    assert 'fetch("/api/characters/generate"' in script


def test_ui_exposes_selectable_character_library_without_a_flow_screen() -> None:
    markup = (ROOT / "ui/index.html").read_text()
    app = (ROOT / "ui/app.js").read_text()
    library = (ROOT / "ui/character-creator.js").read_text()

    assert 'data-view="flows"' not in markup
    assert 'data-screen="flows"' not in markup
    assert 'id="character-library-grid"' in markup
    assert 'fetch("/api/characters")' in app
    assert "window.dijiSelectCharacter" in app
    assert "window.dijiRenderCharacterLibrary" in library


def test_character_cards_do_not_expose_ai_server_import_labels() -> None:
    app = (ROOT / "ui/app.js").read_text()
    library = (ROOT / "ui/character-creator.js").read_text()
    markup = (ROOT / "ui/index.html").read_text()

    assert "ai-server 匯入角色" not in app
    assert 'character.source?.generated_file ? "ai-server 匯入" : "本機角色"' not in library
    assert '<em></em>' not in library
    assert "app.js?v=20261030-openrouter-1" in markup
    assert "character-creator.js?v=20261030-openrouter-1" in markup


def test_chat_starts_with_role_selection_before_opening_a_conversation() -> None:
    markup = (ROOT / "ui/index.html").read_text()
    script = (ROOT / "ui/app.js").read_text()

    assert 'id="role-picker"' in markup
    assert 'class="screen awaiting-character" data-screen="chat"' in markup
    assert 'character: "", characterId: null' in script
    assert "function setChatReady(ready)" in script
    assert "function renderRolePicker(query = \"\")" in script
    assert "const body = await response.text()" in script


def test_project_home_introduces_diji_before_the_role_picker() -> None:
    markup = (ROOT / "ui/index.html").read_text()
    script = (ROOT / "ui/app.js").read_text()
    styles = (ROOT / "ui/home.css").read_text()

    assert 'class="screen home-screen active" data-screen="home"' in markup
    assert 'class="screen awaiting-character" data-screen="chat"' in markup
    assert 'id="home-start"' in markup
    assert "選擇角色開始對話" in markup
    assert "非商業、可自架的角色互動專案" in markup
    assert 'href="#home" aria-label="DIJI 首頁"' in markup
    assert 'home.css?v=20261020-project-home-1' in markup
    assert "function openRolePicker()" in script
    assert 'document.querySelector("#home-start").addEventListener("click", openRolePicker)' in script
    assert 'showScreen("home")' in script
    assert "min-height: 48px" in styles
    assert "@media (max-width: 760px)" in styles


def test_ui_can_restore_a_persisted_conversation_from_the_history_list() -> None:
    markup = (ROOT / "ui/index.html").read_text()
    script = (ROOT / "ui/app.js").read_text()

    assert 'id="conversation-history"' in markup
    assert 'fetch("/api/conversations")' in script
    assert 'fetch(`/api/conversations/${chatId}`)' in script
    assert 'app.js?v=' in markup


def test_ui_defers_google_sign_in_until_the_user_requests_it() -> None:
    markup = (ROOT / "ui/index.html").read_text()
    script = (ROOT / "ui/app.js").read_text()

    assert 'id="auth-gate"' not in markup
    assert 'id="account-login"' in markup
    assert 'id="google-login-dialog"' in markup
    assert 'id="google-login"' in markup
    assert "使用 Google 登入" in markup
    assert "OpenRouter 登入" not in markup
    assert "account-access.css?v=20261031-topnav-1" in markup
    assert ".account-logout[hidden] { display: none; }" in (ROOT / "ui/account-access.css").read_text()
    assert 'fetch("/api/auth/session", { cache: "no-store" })' in script
    assert 'window.location.assign("/api/auth/google/start")' in script
    assert 'fetch("/api/auth/google/start"' not in script
    assert 'fetch("/api/auth/logout"' in script
    assert "function requireLogin()" in script
    assert "authGate" not in script


def test_runtime_private_data_is_ignored_by_git() -> None:
    ignored = (ROOT / ".gitignore").read_text()

    assert "runtime/*" in ignored
    assert "!runtime/.gitkeep" in ignored

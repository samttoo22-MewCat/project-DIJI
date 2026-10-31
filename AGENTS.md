# project-DIJI

## 專案目的

這是非商業、可自架的角色扮演實驗框架。核心是人設生成流程，以及可替換的越獄、提示詞、歷史、記憶與關係演進互動流程。

## 架構原則

- `character_generation`：以 ai-server 邏輯執行「概念 → JSON 人設 → 對話風格 → App 摘要／分類 → 嗜好 → 完整 prompt」。角色生成只產生可審核草稿；只有 UI 明確儲存時才寫入角色庫。`OpenRouterGenerationClient` 只在 `POST /api/characters/generate` 時發送請求。
- `interaction`：組裝互動上下文、依 ai-server 路由模型、清理輸出、保存記憶並更新關係狀態。
- `experiments`：可重現的內部組裝設定與越獄參照；成人虛構請求才可使用其中的越獄欄位，不能內嵌在核心模組。
- `experiments` 的外部越獄匯入只保存可審核中繼資料；每筆須同時有指南路徑與 OpenRouter 現存模型 ID。共用指南應合併為模型範圍名稱（例如 `Opus 4.5–4.8`），不得按同一提示詞重複建立。只有人工核准為 `approved` 的本機內容可以被互動層注入。
- `ui` 的「越獄工作台」必須呈現目錄與審核狀態；`metadata_only` 可檢視但不得啟用。使用者選擇聊天模型後，成人虛構互動由後端依 `openrouter_models` 強制解析同一筆 `approved` 越獄並建立相應 experiment，前端選取的越獄不得覆寫這個對應。
- 越獄一律由獨立的「越獄工作台」管理；工作台可建立、選取與編輯本機內容，並保存到 `runtime/jailbreaks.json`。互動 UI 不提供流程實驗頁。
- 工作台的刪除動作必須先顯示越獄名稱並要求使用者確認；刪除只影響本機 JSON 項目，重新匯入能恢復來源中繼資料。
- `ui`：純 HTML、CSS、JavaScript 的本機工作台。預設畫面是對話；角色庫（含角色創建）、越獄工作台與記憶檢視各自是獨立頁面。互動組裝順序固定在後端，不提供流程實驗 UI。
- 角色創建 UI 固定使用「創作簡報 → 審核草稿 → 明確儲存」三步；生成結果不可自動寫入角色庫。成人虛構角色生成同樣只可使用所選模型對應的已核准越獄。
- 角色頁必須先呈現可搜尋、可選取的角色庫；選取角色會切換目前對話角色並建立新的本機對話。ai-server 匯入資料已寫入 catalog 後才會出現在此清單。
- `local_catalog`：角色與流程的版本化資料模型與 JSON 儲存；UI 只經由 `/api/bootstrap`、角色與流程的保存端點讀寫它。
- `character_import`：只讀取 `ai-server/api_server/configs/output` 的完整角色 JSON、同名完整 prompt 與風格指南；匯入前必須預覽、排除 `incomplete`／無效 JSON 並以角色名稱去重。不得讀取或搬入 memories、favorability、日誌或角色圖片。
- `prompt_assembly`：把角色、流程、場景、歷史與記憶組成可檢查的 bundle；不負責呼叫模型。
- `memory_store`：以 `runtime/memories/{chat_id}.json` 保存 ai-server 相容事件記憶，包含同樣的近期讀取、關鍵字文字搜尋與分類搜尋（分類命中後仍以時間排序）；互動時另以目前訊息的 `keywords` 值形成 `<RELEVANT_MEM>`。
- `conversation_store`：以 `runtime/conversations/{chat_id}.json` 保存完整逐字對話與角色識別；它只負責恢復聊天畫面與歷史訊息，絕不能取代、濃縮或改寫 `memory_store` 的 ai-server 事件記憶。
- `user_profile`：以 `runtime/user_profiles/{user_id}.json` 保存關係判決器回傳的使用者偏好；只可作為 `<FAVORABILITY>` 的內部狀態注入，不得直接當作角色台詞或前端可編輯 prompt。
- `memory_extraction`：互動回合後以 ai-server 相容的抽取提示、OpenRouter adapter、`deepseek/deepseek-v4.1-flash` 與 JSON 輸出設定產生事件記憶；若供應商未回傳可解析 JSON，互動層必須保存同一回合的結構相容回退事件，不能讓成功對話留下空記憶。
- `model_adapter`：保留 ai-server 的 OpenRouter/Skylark、DIGI vLLM、ORPO `/api/generate` 三種路由，未設定金鑰時須在發送前失敗。
- `relationship` 與 `favorability_judge`：保存 ai-server 的五階段好感度門檻、四維分數、深度乘數、致命失誤扣分、關鍵事件晉級規則與 OpenRouter 零分回退。
- `interaction` 的 story 與 dialog 不可共用預設 style：story 必須有小說體、換行與預設 300～700 字規則；dialog 必須有短訊息藝術家與約 50 字規則。兩者都先套用共通格式規則；成人互動再同時注入 `DEFAULT_NSFW_WRITING_RULES` 與模型對應、已核准越獄，任何一層都不得以另一層取代。自訂 `style_prompt` 與實驗風格只能追加，不得覆蓋必要規則層。
- `relationship` 的 prompt 注入不是原始 JSON dump：必須保存角色專屬階段設定、輸出當前階段的語氣／邊界／情緒／profile，並在低好感成人互動時加入防禦層。
- `InteractionRequest.enable_favorability` 預設為 `true`；UI 的「啟用好感度系統」關閉時，不得注入 `<FAVORABILITY>`／`<DEFENSE>`、呼叫 judge、更新關係狀態或 profile。
- `runtime`：本機產生的記憶、關係狀態、實驗設定、日誌與輸出；不得提交。
- `auth`：公開部署時以 Google OAuth 建立 DIJI 帳號；首頁不得強制彈出登入。右上角「登入」及需要寫入使用者資料的動作才可開啟只含 Google 的登入視窗。帳號與雜湊 session 存於 `runtime/accounts.sqlite3` 的 `google_users`、`google_sessions`，使用者的對話、記憶、關係與 profile 存於 `runtime/users/<user-id>/`；不得再以全站共用 JSON 或 `.env` key 識別使用者。
- 公開模式設定 `DIJI_AUTH_REQUIRED=true`、`DIJI_GOOGLE_CLIENT_ID`、`DIJI_GOOGLE_CLIENT_SECRET`、`DIJI_GOOGLE_OAUTH_CALLBACK_URL=https://<公開網域>/api/auth/google/callback` 與不可遺失的 `DIJI_CREDENTIAL_ENCRYPTION_KEY`。Google 登入與模型供應商連線是獨立設計：登入後可持久化資料；模型互動、記憶抽取、好感度判決與角色生成在尚未完成供應商綁定時必須先回 `409`，不得暗用全站金鑰。未登入的私有資料請求一律回 `401`。
- 現有 OpenRouter PKCE、資料表與舊帳號可為相容與未來供應商綁定保留，但不得出現在現在的登入 UI、登入文案或帳號狀態。新的供應商綁定流程必須另行設計與審核後才可開放。
- Python 依賴安裝在專案 `.venv`；`deploy/diji-ui.service` 必須用 `%h/project-DIJI/.venv/bin/python ui_server.py` 啟動。帳號資料庫、使用者資料夾與新寫入的對話／記憶／關係／profile 檔案分別維持 `0600`、`0700`、`0600`。
- 角色圖片、ComfyUI 與訓練資料不屬於本專案範圍。
- `experiments` 與 `interaction` 是 package；不得重新建立同名的 `src/diji/experiments.py` 或 `src/diji/interaction.py`，否則會讓匯入目標含混。
- 每次改動互動層前，先對照 `docs/architecture.md` 的資料流與 `docs/migration-map.md`；這兩份文件定義可開源範圍與 ai-server 行為不變量。

## UI 設計約束

- 主題為低彩度深藍、霧面面板與節制的青紫色重點；不可改成高飽和電競風。
- 對話為預設工作畫面，角色與流程設定只在使用者需要時呈現。
- 對話頁初次開啟時必須先顯示角色選擇器；不得自動選取角色或顯示預設對話。選到角色後才建立新的 `chat_id`、開啟對話與模型設定。
- 左欄「已聊對話」必須讀取本機 `conversation_store`，開啟後恢復角色、逐字訊息與供模型使用的歷史；每則實際互動要先持久化使用者訊息，再持久化成功的角色回覆。
- `960px` 以下隱藏角色／對話列表；`1120px` 以下將設定改為手動開啟的抽屜；`760px` 以下使用手機導覽與 `100dvh` 聊天高度。
- 手機導覽必須保留「設定」入口；窄視窗的對話設定以帶遮罩的 fixed drawer 顯示，支援觸控遮罩、Escape 與關閉後回復觸發按鈕焦點。手機角色卡只能單欄排列，內容需可換行且頁面不得有水平溢位。
- 角色／對話列表只屬於已建立的對話：角色選擇階段及角色、記憶、越獄、設定頁都必須隱藏並釋出內容寬度；桌面已進入對話時預設展開，可由對話標頭按鈕開關。`960px` 以下改為左側 fixed drawer；必須有左側開啟按鈕、面板內關閉鈕、觸控遮罩與 Escape，且與右側對話設定抽屜互斥。各 UI 文字要使用高可讀性淺色與至少 15px 正常內文；角色名稱與人設等長字串必須可換行，不能以水平捲動解決。
- `760px` 以下不得把主要導覽按鈕排列在頂欄；頂欄只保留品牌與「主要導覽」開關。對話、角色、記憶、越獄工作台與設定必須在同一個左側導覽抽屜中顯示，支援遮罩、Escape、44px 觸控目標與選擇頁面後自動關閉。
- 手機版以 Web App 的單一主線呈現：聊天畫面依序為角色標頭、單欄訊息與安全區輸入列；已聊對話／角色庫為左側抽屜，模型設定／本段記憶為 bottom sheet。抽屜必須可由遮罩與 Escape 關閉，聊天與設定不得同時開啟。設計依據記於 `docs/taiwan-mobile-webapp-research.md`；只採資訊架構，不複製外部品牌視覺。
- 正常內文與背景對比至少 4.5:1，互動元件保留鍵盤 focus 樣式。
- 互動區最小高度為 44px，並支援 `prefers-reduced-motion`。
- UI 的預覽結果不得被描述為已呼叫模型；它只能注入已存在於該 `chat_id` 的本機記憶。
- UI 的實際互動必須由使用者勾選「啟用實際模型請求」後才可呼叫 `/api/interactions`；送出中需鎖定 composer，失敗只顯示錯誤、不製造假角色回覆。每個新對話都必須產生新的 `chat_id`。
- UI 的「啟用好感度系統」預設關閉；僅在使用者明確勾選時才傳送 `enable_favorability=true`。實際模型請求送出後到取得結果前，聊天區必須顯示帶有角色名稱的三點輸入泡泡；成功或失敗都要移除，並尊重 `prefers-reduced-motion`。
- 對話右側設定框必須提供預設收合、可展開的「本段記憶」；它只讀取目前 `chat_id` 的事件記憶，於開啟既有對話與每次成功回覆後刷新，並保留「開啟完整記憶資料」入口。
- 已有逐字對話若尚無事件記憶，右側「本段記憶」必須顯示使用者主動觸發的「從既有對話建立記憶」；只回填目前登入帳號的一個 `chat_id`、最多最近 80 則、每 8 則抽取。抽取有任一批失敗時不得寫入部分結果；已有記憶時不得重複回填。此按鈕要明示會使用該帳號 OpenRouter 授權。
- 對話設定必須將 ai-server 的 `story`／`dialog` 分別顯示為「長對話」／「短對話」；以圖像化、可辨識的選擇卡呈現，並在 `runtime/conversations/{chat_id}.json` 持久化 `chat_mode`。模型請求仍傳送原始相容值，禁止在 UI 露出技術名稱。
- 對話標頭的兩個入口固定為左右兩側：左側使用「對話清單」圖示開啟角色／對話列表，右側使用「調整滑桿」圖示開啟「此對話設定」。兩者不得共用漢堡圖示；窄螢幕仍維持至少 44px 觸控目標。
- 聊天模型不可由使用者手動輸入；UI 僅列出已有核准越獄的 OpenRouter 模型，預設為 `deepseek/deepseek-v4.1-flash`（可用時）。成人虛構互動由 `/api/interactions` 依所選模型強制解析同一筆已核准越獄並建立對應實驗，不能信任前端傳入的 experiment id。
- 聊天的「是否開啟色情內容」預設勾選，對應既有 `is_nsfw`；未勾選時不得注入越獄。設定頁可經 `/api/settings/openrouter-key` 寫入本機 `.env`，只接受、保存並套用金鑰，絕不讀回或顯示金鑰值，也不得使用 localStorage。
- 後端會將模型的字面 `\\n` 正規化為換行；聊天訊息 `.message p` 必須維持 `white-space: pre-wrap`，以保留模型輸出的段落與空行。
- `ui_server.py` 只綁定 `127.0.0.1:8080`；第一次保存角色或流程時才會建立 `runtime/catalog.json`。
- Kali 的長駐方式使用 `deploy/diji-ui.service` 與 `scripts/install-user-service`；若需跨登出與重開機，啟用該帳號的 `loginctl enable-linger`。維運前先跑 `scripts/diji-healthcheck`。服務維持 loopback-only，遠端操作只經 SSH tunnel。
- `diji-ui.service` 必須以 `EnvironmentFile=%h/project-DIJI/.env` 載入 provider 金鑰；不得把金鑰放入 unit、日誌或前端。
- 公開 `diji.mewcat.me` 使用獨立 `diji-kali` Cloudflare Tunnel；connector 是 Kali 使用者層的 `diji-cloudflared.service`，執行 `~/.local/bin/cloudflared tunnel run --token-file ~/.config/diji/cloudflared.token`。token 檔必須是 0600、不得進入 repository、unit 或日誌；Tunnel 的公開主機名稱以 Cloudflare managed route 指向 `http://127.0.0.1:8080`，不得將 Tailscale `100.x` 位址放入公開 DNS。
- 公開入口是 PWA：`ui/manifest.webmanifest`、`ui/service-worker.js` 與 `ui/icons/` 必須可由根目錄靜態路由提供。Service Worker 只能快取靜態介面外殼，必須排除 `/api/`、登入、對話、記憶與任何使用者資料；離線時只保證能開啟既有介面，不得宣稱可離線對話。變更 Service Worker 的快取策略時遞增 `CACHE_NAME`。Android/Chromium 以 `beforeinstallprompt` 顯示安裝入口；iPhone/iPad 只能呈現 Safari「分享 → 加入主畫面 → 以 Web App 開啟」指引。安裝按鈕維持至少 44px 觸控目標，已在 standalone 顯示模式時不得顯示。不得以 `userChoice` 的 accepted 結果隱藏入口；收到 accepted 後，按鈕必須顯示「Web App 安裝中…」且停用，只有瀏覽器實際發出 `appinstalled` 後才能隱藏。取消、錯誤或等待 2.5 秒仍未完成時要保留入口並顯示瀏覽器選單的手動安裝指引。
- Google 登入回呼與 `/api/auth/session` 必須回傳 `Cache-Control: no-store`，前端讀取 session 也必須使用 `cache: "no-store"`；每次變更 `ui/app.js` 都要遞增 `index.html` 的 query version，避免 OAuth 回跳重用登入前的未登入快取。
- Google 登入啟動必須以瀏覽器頂層導向 `/api/auth/google/start`，讓伺服器 303 直接前往 Google；不得用 `fetch(..., redirect: "manual")` 讀取 `Location`。`runtime/` 內的帳號、session、對話、記憶與 provider 憑證一律保持 Git 忽略；推送前以 `git ls-files runtime` 確認只存在 `runtime/.gitkeep`。
- 驗證登入 UI 時，必須確認初始首頁沒有登入遮罩或已開啟對話框、右上角有登入入口，且只有使用者點擊登入／私有動作後才打開 Google 對話框。
- 帳號按鈕使用自訂 `display` 時，`ui/account-access.css` 必須保留 `.account-login[hidden], .account-logout[hidden] { display: none; }`；否則 HTML `hidden` 屬性會被樣式蓋掉，使未登入首頁錯誤顯示登出。
- `file:///.../ui/index.html` 只是靜態原始檔預覽，不能呼叫登入 API；UI 必須偵測 `file:` 協定並在登入對話框清楚提示改用已部署的 DIJI 網站。每次登入問題先同時確認瀏覽器目前 URL、本機 session HTTP 回應與 Kali healthcheck。
- 所有面向玩家的描述、摘要、說明與欄位提示，都以目前 UI 原本尺寸至少加大 2px：桌面主要描述為 17px、次要描述／欄位說明為 16px、微型 metadata 為 14px；手機主要描述為 18px。時間戳、純圖示與按鈕內控制文字不屬描述文字，維持既有階層。統一由 `ui/responsive.css` 最後的 Description copy 規則維護。
- DIJI 預設入口為介紹專案的 `home` 畫面；首頁只介紹專案與網站，唯一主要 CTA 為「選擇角色開始對話」，它會呼叫 `setChatReady(false)` 後進入既有角色選擇器。左上角 `.logo` 必須攔截預設 anchor 行為並呼叫 `showScreen("home")` 回首頁，不建立或刪除對話。
- 對話設定的桌面右側欄固定偏窄；「長對話／短對話」一律單欄，避免把文字擠成逐字換行。此處的卡片輔助文在桌面可使用 14px／1.55 行高以維持資訊密度；手機仍保留全站可讀的 16px。
- 角色的 `source.generated_file` 僅供內部匯入追溯；玩家介面的角色庫卡片與對話標頭不得顯示「ai-server 匯入」或「本機角色」來源標籤，優先顯示角色人設摘要。
- 新增模板或層順序時，先在 prompt preview 驗證 bundle，再新增模型 adapter。
- 記憶注入必須保持 ai-server 的 `MEM0_INJECT_MODE`（`system`／`user`／`none`）與請求覆寫規則；`<MEM>` 區塊上限為 1200 字元，最近記憶上限為 20 筆。
- 互動 prompt 的可移植層順序是：角色／風格 → 關係引導（啟用時）→ 記憶與相關記憶 → 時間 → 收尾規則 → 歷史 → 本回合 OOC。越獄不是固定程式碼，仍只可由已核准的獨立越獄資料注入。
- `docs/ai-server-parity-audit.md` 是原始架構對照的唯一狀態表；新增或改動互動層前必須更新此表與對應測試。
- `pyproject.toml` 必須列出完整 runtime dependencies；不可依賴 Kali 系統層已安裝的 FastAPI、OpenAI、Pydantic、HTTP client 或 ASGI server。
- `reset=true` 必須對齊 ai-server：只刪除該 `chat_id` 的事件記憶與關係狀態，不刪除完整逐字對話或使用者 profile；對話模式則保留短訊息、自然資訊分享的獨立提示層。

## 目前遷移狀態

互動與人設生成的可呼叫服務已拆出。仍以遠端專案的既有 pytest 環境做最後的整合驗證；不要把本機 UI 的預覽或未設定金鑰的端點誤稱為實際模型執行。

### 2026-10-13 目前可用狀態

- 已部署於 Kali `/home/kali/project-DIJI`；`diji-ui.service` 為 `active`，僅監聽 `127.0.0.1:8080`，以 SSH tunnel 從本機瀏覽。最後驗證為 `pytest -q` 48 passed，`scripts/diji-healthcheck` 的 `/`、`/api/bootstrap`、`/api/characters`、`/api/jailbreaks` 均通過。
- 工作中的同步來源是 `/tmp/diji-ui-patch`；變更 UI 後必須同步到上述 Kali 專案、重啟服務並完成瀏覽器驗證。`ui/index.html` 以 `responsive.css?v=20261018-readable-subcopy-2` 與 `app.js?v=20261017-chat-mode-1` 避免舊靜態資產快取；修改這兩個檔案後必須遞增對應版本。

### 2026-10-21 公開入口

- 正式公開網址為 `https://diji.mewcat.me`。Cloudflare 的 `diji-kali` Tunnel 已健康連線，`diji.mewcat.me` 是 Cloudflare 自動建立的 proxied CNAME，公開路由只會轉至 Kali 的 `http://127.0.0.1:8080`；不要另建 A/AAAA 記錄，也不要改用 Tailscale 位址。
- `diji-cloudflared.service` 已由 Kali 使用者層啟用並搭配 `loginctl enable-linger kali`，因此會在開機、登入前維持連線。驗證順序為兩個 user service 皆為 active、`https://diji.mewcat.me/` 與 `/api/bootstrap` 回 200，再以公開瀏覽器檢查登入遮罩。
- `.env` 的 `DIJI_OPENROUTER_OAUTH_CALLBACK_URL` 已指向公開 HTTPS callback；`AuthSettings.secure_cookie` 因此會產生 Secure session cookie。修改該值前先備份 `.env`，不得把 encryption key、OpenRouter key 或 Tunnel token 輸出到終端、紀錄或 repository。
- Google OAuth Web client 已建立並配置公開 origin `https://diji.mewcat.me` 與 callback `/api/auth/google/callback`；`.env` 需以 0600 保存 `DIJI_GOOGLE_CLIENT_ID`、`DIJI_GOOGLE_CLIENT_SECRET`、`DIJI_GOOGLE_OAUTH_CALLBACK_URL`。驗證時只回報設定狀態與 `/api/auth/google/start` 是否以 303 導向 Google，絕不可輸出憑證或 state 參數。`diji-ui.service` 是 Kali 使用者層 service，使用 `systemctl --user restart diji-ui.service`，不要以 sudo system unit 重啟。
- 工作台（角色、記憶、越獄、設定）內的副標題與說明文字必須可閱讀：桌面說明至少 15px、欄位標籤與次要清單文字至少 14px；手機說明為 16px。統一在 `responsive.css` 的「Studio subpages」規則維護，避免各子介面各自縮回微小文字。
- 越獄編輯器的「儲存越獄／選取越獄／刪除規則」必須在同一個 `.jailbreak-editor-actions` 格線內排列，三者等高且不受全域手機版 `.primary-button` 外距影響；窄於 `440px` 時才改為單欄。`jailbreak-studio.css` 使用 `?v=20261018-actions-aligned-1` 避免舊快取。
- 手機版已實測 375px：正常文字 15px、角色名稱 16px、角色人設 14px，無水平溢位。`960px` 以下的角色／已聊對話列表為獨立左側抽屜；`760px` 以下的主要導覽為另一個左側抽屜，頂欄只保留品牌與主選單按鈕。主選單含對話、角色、記憶、越獄工作台、設定，點選頁面、點遮罩或按 Escape 都會關閉。
- 桌面工作台頁（角色、記憶、越獄、設定）必須是內容區內可捲動的文件流，不得沿用 `.screen.active` 的 grid 置中行為；`responsive.css` 的桌面覆寫固定 `.app`／`.content` 高度並使 `.studio-screen.active` 以 block 顯示。角色庫採用至少 280px 的自適應卡片欄位，避免在一般桌面寬度壓成過窄卡片；左欄以獨立捲動區承載長清單，角色文字容器必須 `min-width:0`，使長人設維持既有截斷規則而不覆蓋主內容。
- Kali 沒有系統 `rg`；已安裝使用者層級的 `ripgrep 15.2.0` 於 `~/.local/bin/rg`。非互動 SSH 指令需要時以 `PATH="$HOME/.local/bin:$PATH"` 使用它；不需要 sudo。
- 根目錄 `README.md` 維持純技術文件：只描述架構、模組責任、需求、設定、執行、runtime 資料、測試、部署與技術文件連結；專案動機、使用情境、社群宣傳與內容敘事應留在其他適當文件，不得重新加入 README。原始 MIT 版權聲明必須保留於 README 末尾。

## 自主排錯

- 工具、patch、路徑、快取、依賴或環境失敗時，保留變更並自行讀取實際狀態，改用更小範圍 patch 或等效工具繼續完成；不得僅因可自行排除的技術錯誤要求使用者指示。
- 只有需要新權限、敏感資料、不可逆操作，或缺少會改變成果方向的使用者決策時，才暫停詢問。

## 強制部署閉環

任何會改變執行行為的 Python、UI、依賴、服務設定或靜態資產修改，都必須在同一回合完成以下閉環：

1. 以 `ssh diji-kali` 同步修改檔案到 Kali 的 `/home/kali/project-DIJI`；它固定指向 `kali@100.68.219.112` 並使用 `~/.ssh/id_ed25519_arcaneforge_codex`。這把公開金鑰已安裝於 Kali；日常部署不得改回密碼流程，也不得把密碼放入命令、檔案、服務設定或工作紀錄。若金鑰驗證失敗，先檢查 `ssh -O check diji-kali` 與 `ssh -vv diji-kali true`，再處理遠端 `authorized_keys`。
2. 重啟 `diji-ui.service`。
3. 在 Kali 跑 `pytest -q` 與 `scripts/diji-healthcheck`。
4. 用瀏覽器重新載入帶新 query string 的 `http://127.0.0.1:8080/`，驗證受影響 UI 或 API 的實際行為。

完成條件是遠端服務為 `active`、健康檢查與測試通過、受影響功能在網站實際可用；只有本機測試的改動只能標記為「尚未部署」，不可回報完成。SSH 工作階段失效時，保留 staged 變更並在回覆中明確報告部署阻塞，不得遺忘待部署項目。

## 驗證工具自足

- 遠端或本機缺少完成既定驗證所需的通用工具時，先確認它只用於本專案的建置、測試、健康檢查或 UI 驗證；符合時直接安裝並繼續，不必為 `rg`、curl、pytest、Node.js 等工具另外停下詢問。
- 先使用環境現有的封包管理器與專案宣告的依賴；安裝後立刻以版本或單一目標指令確認可用。安裝不得覆寫專案 `.env`、資料庫、runtime 或使用者檔案。
- 驗證靜態資產時，先從 `ui_server.py` 或服務路由確認實際 URL，再做 HTTP 請求；不要從檔案系統路徑猜測公開 URL。任何瀏覽器快取疑慮都以新的 query string 重新載入，並用瀏覽器 computed style 與互動結果作為最後判定。

## 驗證

```bash
python -m compileall -q src
pytest -q
./scripts/diji-healthcheck
```

## 2026-10-24 本機模式

- 目前不提供公開網站。`diji-ui.service` 保持啟用且只監聽 `127.0.0.1:8080`；`diji-cloudflared.service` 必須停用並停止。未經使用者明確要求，不得重新啟用 Tunnel、公開路由或任何外網入口。
- README 僅說明本機 UI 的安裝、啟動、SSH tunnel 與測試；Google OAuth、公開帳號、公開網域與公開部署資訊不應寫入 README。

## 2026-10-27 AWS 公開入口（目前）

- AWS 主機上的 `diji-ui.service` 維持只綁定 `127.0.0.1:8080`。公開 HTTPS 由使用者層 `diji-cloudflared.service` 提供，unit 來源為 `deploy/diji-cloudflared.service`；它使用 `~/.local/bin/cloudflared` 與 `~/.config/diji/cloudflared.token`。token 檔必須維持 `0600`、父目錄 `0700`，不得輸出、提交或複製到本機。
- `diji.mewcat.me` 經 Cloudflare Tunnel 轉送到 loopback；每次修改公開部署後，先驗證 user service 為 `active`，再以 `https://diji.mewcat.me/api/auth/session` 回傳 DIJI JSON 作為公開讀回。Google OAuth 的 callback 必須維持相同公開 HTTPS 網域，並確認 `/api/auth/google/start` 導向 Google 而不是回 `503`。

## 年齡確認

- BazaarLink 使用 S256 PKCE 與帳號綁定，加密存於 `additional_provider_keys`；供應商順序按帳號保存。聊天、角色生成、記憶及好感度統一經 `provider_routing`，只在 HTTP 402 明確額度不足時切換，逾時及其他錯誤不跨供應商重試。真實授權需使用者在供應商頁完成。

- 模型帳號綁定與用量位於獨立 `connections` 導覽頁；聊天與角色生成提供前往設定按鈕。未啟用頁面一律隱藏，避免手機版選角區滲入其他頁面。

- 手機主要導覽按鈕位於頂部帳號列左端，登入／登出位於右端；關閉抽屜時不保留第二條導覽列。維持唯一 `toggle-mobile-nav` ID 與既有開關事件。

- 帳號區使用獨立頂列佔據實際版面；工作區高度取剩餘空間。避免用 fixed 帳號按鈕覆蓋聊天操作，手機版亦須扣除帳號列與導覽列高度。

- OpenRouter 綁定入口在對話設定的實際模型請求旁，使用 `/api/connections/openrouter/*` 將 PKCE 授權綁定既有 session，保留 DIJI 帳號。金鑰加密於帳號資料庫；金額為授權金鑰的累計與今日用量（USD），不是帳號總額。

- 建立角色為獨立 `create-character` 頁面與側欄入口；選角與角色庫皆以最後一張同尺寸卡片開啟。部署必須另行搬移 `runtime/jailbreaks.json`，並核對可用 prompt 與模型選單，Git checkout 不含這份執行資料。

- 帳號角色：公開模式新增角色寫入 `runtime/users/<account>/catalog.json`，公開角色保留於共用目錄。角色列表、bootstrap、單筆讀取、預覽與對話入口均依當前 session 取得角色；回應禁止快取。個人角色使用「我的角色 · 僅自己可見」標示與低彩度紫色卡片。建立角色卡需在選角網格最後一格。

- 選角捲動：`role-picker` 必須受可視高度限制（`min-height:0`、`height:100%`），手機版 awaiting-character 使用扣除導覽列的視窗高度。角色數量增加後，用實際捲動驗證最後一張卡可見；只檢查 `overflow:auto` 不足以驗證。

- 角色部署：2026-10-30 已將 Kali 的 20 位角色恢復至 AWS `runtime/catalog.json`。此檔不在 Git；搬機時須另外備份與複製，先以 `CatalogSnapshot` 驗證，再比對公開 `/api/characters` 數量，不能用兩位內建示範角色當成遷移完成。角色資料與備份維持在 Git 之外。

- 登入按鈕於 2026-10-30 調整為深藍與低彩度青色，圖示使用 Simple Icons Google SVG。更新 `ui/account-access.css` 時同步更換 HTML 的資源版本，並檢查手機登入視窗不溢出。

- 公開頁面在載入後先以 `ui/age-confirmation.js` 顯示原生 18+ 確認視窗；使用者必須勾選「我確認已滿 18 歲」才能關閉。只有自行勾選「在此裝置記住一年」時，才可寫入 `diji_age_confirmed=1` Cookie（`Path=/`、`SameSite=Lax`，HTTPS 時另加 `Secure`）。不得儲存生日、帳號識別碼或任何年齡以外資料；未勾記住時重新載入必須再次確認。
- 在設定頁的「重新確認 18+ 年齡」按鈕是唯一清除該 Cookie 並重新顯示確認視窗的使用者入口；不可由其他前端流程自動清除或改寫使用者選擇。
- 每次更動 `ui/age-confirmation.js` 的行為時，必須同步更新 `ui/index.html` 的版本查詢字串，避免既有瀏覽器保留舊版年齡確認邏輯。

## 公開政策文件

- `docs/privacy-policy.md` 與 `docs/usage-notice.md` 是公開服務前的繁中草案。變更帳號、保存位置、資料類型、模型供應商、資料用途或公開營運方式時，必須一併更新；不可把尚未實作的刪除、加密、備份、審核或資料不蒐集承諾寫成既有事實。
- BazaarLink 與 OpenRouter 的 OAuth 連結是預計的「使用者自備額度」功能，不是 DIJI 登入。實作時使用 PKCE、只在伺服器端受保護地保存供應商憑證、不得以共用 provider key 靜默回退、不得將憑證回傳前端或寫入日誌；中斷連結、撤銷授權與帳號刪除時必須清除保存的憑證。上線前同步把實作狀態與資料流更新到兩份政策文件。

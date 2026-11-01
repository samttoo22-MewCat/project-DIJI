# project-DIJI

## 專案目的

這是非商業、可自架的角色扮演實驗框架。核心是人設生成流程，以及可替換的越獄、提示詞、歷史、記憶與關係演進互動流程。

## 架構原則

- 首頁「安裝 DIJI」獨立換行於主要操作下方，說明加入手機主畫面／電腦應用程式、仍須連網及伺服器保存資料。`pwa.js` 切換按鈕顯示時同步控制 `data-pwa-install-section`，避免不支援安裝或已安裝時殘留空白說明；保留原有安裝進度與 iOS 指引邏輯。
- 2026-11-01 安裝說明驗證：本地與 AWS 各 30 項 UI 測試通過，既有安裝進度測試補查說明區同步顯示／隱藏。Edge 正式站 375px 確認安裝按鈕位於主要按鈕下一行、說明 18px、頁面無水平溢出；沒有實際安裝 App。服務重啟 active、健康檢查 200。
- 玩家設定刪除：DELETE `/api/player-personas/{id}` 僅刪目前帳號的設定列，無 cascade、不碰 conversations／memories／relationships／branch_profiles。確認視窗說明不可復原及既有資料保留。刪掉最後一份也允許既有正式對話與試聊依其 persona 快照續寫、編輯重新生成；只有開新對話需設定庫仍存在可選項。試聊先讀取帳號所屬的既有 transcript 快照，不再強制查詢已刪掉的來源 ID。前端保留已選快照並標示「此對話保存版本」，新的聊天與新的試聊仍檢查有效設定 ID。刪除實測用隔離資料，正式瀏覽器僅檢查及取消確認視窗，不實刪玩家設定。
- 2026-11-01 刪除驗證：本地與 AWS 各 210 項 pytest 通過、七組 Node DOM／Service Worker 測試通過。測試比對刪除前後原 transcript、記憶與關係完全相同，並確認刪最後一份後正式／試聊仍可續寫與編輯重新生成；匿名 401、跨帳號與重刪 404、新對話拒絕已刪 ID。Edge 以只有虛構資料的本機 HTTP 介面 fixture 檢查 375px／1440px 刪除確認視窗及取消焦點，不提交刪除；正式帳號沒有設定，因此僅確認新版頁面載入，沒有新增／實刪正式資料。部署重啟後 active，健康檢查 200。
- 玩家個人設定：`player_personas.py` 的帳號 SQLite 與 AI 抽取偏好 `user_profile.py` 分開，沿用 `UserPersona` 的 name／sex／age／description。左側角色下方的獨立頁可新增與編輯；聊天右側選用時以新 chat_id 建立空白對話，保留原逐字稿、記憶與關係。對話保存 persona ID＋快照，後端使用快照而非前端傳來的人設；編輯訊息分支也保留快照。新自訂 persona 的自動偏好限該對話，預設／舊對話沿用原 profile 行為。修改設定不改既有對話，重新選用才使用新版本。
- 公開服務開新對話必須至少有一份帳號玩家設定，正式聊天與草稿試聊皆在模型呼叫前檢查；沒有設定回 409，多份而未選 ID 也回 409，單份 API 可自動採用。UI 要先明確選用，移除預設使用者選項。未綁定玩家設定的舊對話可讀取，但生成需另開新對話，不就地改寫舊人設。草稿試聊傳入所選 ID，中途改身分也產生新 trial chat_id，保留原試聊。無模型連線仍優先顯示模型商提示，不將角色生成整頁鎖成必須先有玩家設定。
- 必填玩家設定追加驗證：本地及 AWS 209 項 pytest 通過、七組 DOM／Service Worker 測試通過；最後首頁四步驟與快取版本更新另跑 30 項 UI 檢查。缺少人設時正式／試聊 409 且模型呼叫數為 0；多份未選擇及舊對話不能就地改身分也有回歸測試。Edge 正式帳號尚無玩家設定時，點角色會導向玩家設定提示，不建立測試人設與對話、不消耗額度。首頁流程為登入 → 模型連線 → 玩家個人設定 → 選角。
- 2026-11-01 玩家設定驗證：本地與 AWS 各 208 項 pytest 通過，七組 Node DOM／Service Worker 測試通過。隔離帳號驗證儲存重開、權限／跨帳號 404、prompt 使用人設快照、年齡性別不重複注入、新對話空白記憶／關係、原對話保留、訊息編輯分支保留人設；DOM 驗證切換產生新 chat_id 並清空前文、生成中禁止切換。Edge 正式站 375／768／1024／1440px 無水平溢出，手機表單底部可捲動操作、內文 18px、主控台無錯誤。正式帳號只打開與取消空白表單，未留下測試人設，未發送付費模型請求。
- 使用者已明確要求「自己修正並繼續，測試通過後部署、重啟服務和推送，不要再因為這種問題問我」：一般實作、測試與診斷錯誤自行排除後繼續，不再因連續終端失敗要求確認；權限與破壞性操作仍遵守授權範圍。
- 登入前條款：`docs/privacy-policy.md` 與 `docs/usage-notice.md` 是唯一內容來源，`LegalDocuments` 以兩份全文計算同一版本雜湊；公開 `/legal/privacy`、`/legal/terms` 與 `/api/legal`，不需登入。頁面只渲染這兩份部署文件，不接受使用者 Markdown。維運者聯絡連結為 `https://mewcat.me/contact`。
- 登入使用原生 POST 表單送出 `terms_agreed=yes` 與目前 `policy_version`，勾選預設為否；後端檢查 Origin、同意欄位及版本。GET 舊登入入口只回到 `/?login=required` 顯示確認視窗。OAuth state 暫存同意版本，回呼需同時通過目前版本及既有瀏覽器綁定；成功後才在帳號庫 `legal_acceptances` 保存 user_id、version、accepted_at，不收集額外 IP／裝置指紋。Google 與舊 OpenRouter 相容登入都不能繞過；不替既有 session 補填同意。
- 測試條款流程用隔離 TestClient／虛構帳號；正式瀏覽器只檢查未勾選、閱讀連結及阻擋狀態，不代替使用者接受條款。條款導覽不寫成 PWA 的離線首頁，Service Worker 只把根首頁導覽保存為 app shell，避免閱讀文件後覆蓋工作台。
- 2026-11-01 登入條款驗證：本地與 AWS 各 204 項 pytest 通過，本地六組 Node DOM／Service Worker 測試通過；Edge 確認 375px 登入畫面、320px 可捲動至登入按鈕且頁面無水平溢出、1394px 桌面確認窗寬 500px。公開隱私文件 320px 無頁面溢出，內文字級 18px。正式登入確認預設未勾且 Google 按鈕停用；同意後 OAuth 與版本變更拒絕使用隔離測試驗證，未替真實帳號提交同意。
- 使用者本輪已明確要求「有問題自己去修正」：可定位的實作／測試錯誤自行修正並驗證，不因一般測試失敗反覆詢問；新權限、未授權的付費服務或破壞性資料操作仍依原授權範圍處理。
- 本輪安全更新由三個 GPT-6.1 Terra 子代理分工並整合：本地及 AWS 均 196 項 pytest 通過，四組 DOM 測試通過。已備份正式帳號庫；Edge 真實 Google 登入返回工作區，既有 session 保留，公開 API 匿名請求回 401。真實模型隔離驗證改後 prompt 確實送出、舊訊息未混入、新分支與記憶保存、原對話未變；不要以模型是否逐字複述某個詞作唯一判準。生成並發與拒絕／取消測試為隔離假模型，不宣稱完成長時間真實負載測試。
- 公開模型選擇須經 `public_models.validate_public_model`，驗證在模型呼叫與內容寫入前；有既存資源的端點先驗證帳號歸屬，維持跨帳號 404。公開模式拒絕任何 `llm.url` 及舊內網／全站憑證路由，僅接受帳號 ProviderCredentials；本機模式保留 ai-server 路由。不可為了讓測試通過改收一般字串 key 或一般 list 當公開憑證。
- Google 登入使用 `begin_google_oauth_flow`／`consume_google_oauth_flow` 綁定發起瀏覽器，S256 PKCE verifier 僅在伺服器暫存，成功後原子消耗。HTTPS 的 `__Host-diji_google_flow` Cookie 為 HttpOnly、Secure、SameSite=Lax、Path=/、600 秒；成功或交換失敗清除，錯誤綁定不消耗合法流程。舊帳號／session 保留，部署前以 SQLite backup 備份帳號庫，不輸出 Cookie、state、verifier 或憑證。
- 生成工作保護位於純 ASGI `work_limits.ModelWorkMiddleware`，不要用 BaseHTTPMiddleware 的 call_next 外層 timeout 取代，以免工作仍在背景執行卻提早釋放名額。單程序預設全站 8、帳號 2、帳號每分鐘 20 次，工作 180 秒；API 寫入上限 1 MiB，包含無 Content-Length 的分塊上傳。429 帶 Retry-After，504 取消工作並釋放回合鎖；不自動重試已可能計費的請求。
- 正式聊天／試聊收到 429 或 413 時，保留原輸入並移除未被伺服器接受的樂觀泡泡與 history；504 則保留已送出訊息，提示確認狀態，不自動重送。`tests/model-limits-ui.test.cjs` 驗證這三種回應，並保留訊息編輯與 IME 回歸。
- 舊 OpenRouter 相容登入也以獨立的短效 Host Cookie 綁定 state，在消耗 PKCE verifier 前檢查瀏覽器，成功／交換失敗後清除。登入 UI 仍只顯示 Google，模型商連結仍綁定既有帳號；不要為了保留舊 session 而保留未綁定的新登入回呼。
- 流程也採共用預設＋帳號覆寫，公開模式 GET／PUT flows、bootstrap 與 prompt-preview 都用帳號有效 catalog；共用檔只讀。私人角色與流程共存同一 catalog，`LocalCatalog` 保存使用同一檔案鎖與原子替換，初始私人 catalog 為空，不複製內建角色。
- 模型失敗僅回傳通用訊息與 error_id；`errors.report_error` 日誌只記 operation、error_id、例外類型，不記例外字串、traceback 或請求內容。既有記憶 error 記錄在讀取／回傳時遮蔽診斷欄位與摘要，保留原始私有檔案，不把診斷文字注入 prompt。這是經使用者核准的安全修正，其他記憶格式與查詢行為保持不變。
- 多人請求：同一 HTTP 請求只查一次 session 與帳號模型憑證，stores／activity 使用 ContextVar 的請求內快取，請求結束即釋放；不得改成跨帳號或跨請求的憑證快取。模型 client 在請求內重用並於完成、失敗／取消時關閉，維持額度順序與 402 才切換。聊天的同步 prompt／快照／對話／記憶寫入移到執行緒，避免堵住其他玩家的 event loop。
- 同一帳號、同一正式或試聊 chat_id 以 `.turn.lock` 非阻塞 flock 保護整個生成回合，重疊請求回 409、不再呼叫模型；不同帳號與不同對話可並行。不是全站限流／持久工作佇列，不能宣稱支援多台主機或斷線後自動恢復生成。`tests/test_concurrent_usage.py` 驗證並行、隔離、重複回合、慢磁碟不堵住 session 及 client／SQLite 關閉。
- 公開模式越獄採帳號覆寫：共用 `runtime/jailbreaks.json` 只作預設；第一次儲存才產生 `runtime/users/<account>/jailbreaks.json`，以 ID 覆寫預設。刪除個人覆寫恢復預設，純自訂項目則移除；預設不能由玩家刪除。內部 experiment 指標與設定也使用帳號的 `experiments.json`，避免個人越獄名稱／選擇寫回共用檔。聊天、建立角色、AI 修改與草稿試聊均解析同一帳號的有效越獄。個人 JSON 採 flock＋原子替換、0600，目錄 0700，API no-store。舊共用檔缺少作者資訊，不可擅自推測歷史修改者或搬成個人資料。
- 本輪多人／個人越獄驗證：本地與部署主機 134 項 pytest 通過，三組 DOM 測試通過（訊息編輯、IME、個人越獄／推薦句換行）。AWS 隔離 20 帳號模擬模型測試 peak=20、耗時約 1.84 秒，每請求一次 session／憑證載入；此數值不是持續負載容量承諾。真實模型的編輯後重新生成與記憶保存通過，原對話未變。Edge 已確認預設標示／禁止刪除及推薦句 700 字重＋BR；跨帳號寫入隔離與生成用個人越獄由隔離 API 測試驗證，不修改玩家既有越獄來當測試資料。
- 記憶工作區每筆可編輯／刪除。`GET /api/memories/{chat_id}/entries` 提供檔案版本＋內容＋位置 fingerprint；PATCH／DELETE 先驗證目前帳號擁有該對話，再匹配 fingerprint，任何資料變動時回 404 要求重載，避免重複內容位移後被舊操作誤刪。只允許修改分類、摘要、關鍵字、重點與角色回覆摘要，保留時間、原訊息及來源 metadata，附 `manually_edited` 標記。
- Linux/macOS 的記憶追加、修改、單筆刪除與整段 reset 共用檔案鎖與原子替換，避免並行覆寫。不得用整批前端資料覆蓋檔案。刪除 UI 顯示摘要及不可直接復原警告，必須勾選確認；後端測試以隔離資料驗證刪除，不在瀏覽器實刪既有使用者資料。

- 2026-11-01 Edge 實測：記憶抽取的 DeepSeek V4.1 Flash 預設推理可耗盡 1000 token，導致空正文與回退記憶。抽取請求固定 `reasoning.enabled=false`，保留模型、1000-token 上限、JSON schema、提示與 ai-server 查詢語義。`tests/test_memory_reasoning.py` 重現空正文並防止回歸。
- 記憶工作區：記憶入口先顯示角色卡片，僅列 `message_count>0` 的對話並依 character_id 分組。角色內切換對話、查看最近 100 筆記憶及搜尋／篩選；重新整理回角色網格，不自動選取角色。右側「開啟完整記憶資料」直接打開該對話。UI 位於 `memory-workspace.js/css`，不在瀏覽器保存記憶正文。
- 多值關鍵字限制已依使用者明確指示修正，使用分隔符拆值；仍不做語意檢索，不將短片段反向命中整個人名。`extraction_status` 只新增來源 metadata，舊未標記紀錄顯示「待整理」，不得冒稱已確認為模型抽取或回退。
- 本輪驗證：87 項 pytest 通過；Edge 驗證只有已聊角色可進記憶、搜索／篩選／原文展開與四種寬度。新 `tests/test_memory_keywords.py` 保護多值拆分、詞組、時間順序及 API limit；記憶頁 `limit=100`，側欄預設 10 不變。

- `character_generation`：以 ai-server 邏輯執行「概念 → JSON 人設 → 對話風格 → App 摘要／分類 → 嗜好 → 完整 prompt」。角色生成只產生可審核草稿；只有 UI 明確儲存時才寫入角色庫。`OpenRouterGenerationClient` 只在明確的生成／草稿修改 POST 中發送請求。
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

- 首頁頁尾最後一項為 GitHub 開源專案連結 `https://github.com/samttoo22-MewCat/project-DIJI`，另開分頁並提供無障礙說明；沿用作者連結外觀與手機觸控尺寸。
- 首頁底部作者介紹使用 Mewcat 的 AI 記憶／人格／認知系統研究簡介，個人網站連結為 `https://mewcat.me/`，另開分頁並標示。手機底部單欄、連結最少 44px；保留原專案與分級／額度說明。手機設定與桌面共用 `.rail-footer` 齒輪；favicon 與左上品牌共用同一圖檔，避免另設不一致版本。
- 2026-11-01 Edge 手機尺寸驗證：375px 選單底部設定按鈕高 48px，可正常開啟設定；375／430px 作者區單欄、說明 18px、連結約 89px 高，1440px 作者區雙欄，均無橫向溢位。30 項 UI 檔案測試通過。favicon 公開 PNG 與左上品牌檔逐位元一致；自動化操控時瀏覽器可能暫加分頁圖示徽章，這不是網站圖示。尺寸模擬不等於實體 iOS／Android 驗證。
- 左下設定入口使用有齒輪廓與中心圓孔的 SVG，不使用日光放射線圖示；保留 `data-view="settings"` 與無障礙名稱。瀏覽器 favicon 直接沿用左上品牌入口的 `/icons/diji-192.png`，以版本查詢字串更新快取。
- 模型連線頁 BazaarLink 介紹依使用者要求標示「台灣本土 AI 中轉站 · 十分推薦」，說明方便易用的繁體中文介面；此為專案推薦文案，不代表模型品質、價格或可用性的保證。
- 2026-11-01 訊息編輯驗證：124 項 pytest、`message-edit.test.cjs` 與 `chat-ime.test.cjs` 通過。AWS 隔離目錄以真實已連接模型測試原訊息、編輯、重新生成；新回覆符合修改後主題，新訊息／記憶保存，原對話逐字未變，編輯前快照恢復。公開 JS 與部署檔相同。此輪 Edge 控制通道中斷，未完成瀏覽器視覺／實體手機驗證，不能把 DOM 測試當成 Edge 操作證據。
- 正式聊天與草稿試聊的玩家訊息提供「編輯 → 儲存並重新生成」。共用 `ui/message-editor.js`，不以 Enter 自動提交編輯框。後端驗證帳號、完整對話 revision、訊息索引與 sender_type；建立新 chat_id，複製編輯處之前的逐字歷史，從修改訊息重新執行原 `execute_interaction`。原對話與其後續訊息／記憶／關係狀態保留；新畫面提供「查看編輯前對話」，正式列表標示「編輯後」。
- 每回合在追加玩家訊息前將 memory／relationship／profile 存為狀態快照，以完整前文指紋綁定 `(chat_id,message_index)`；SQLite 的 `checkpoint_values` 按內容雜湊共用不可變資料，避免每回合重複保存全部記憶正文。新分支只恢復該點之前的快照，profile 寫入帳號 `branch_profiles/<chat-id>/`，不可改全域或其他分支偏好。試聊仍限於 `creator_trials/`。舊對話沒有匹配快照時，保留前文並從空記憶／初始關係／空偏好累積，UI 必須說明限制；不可拿目前的未來狀態當成過去狀態。
- 編輯後模型失敗仍保存修改後的分支，回應提供該對話與通用錯誤，不回傳原始供應商例外。前端保留編輯失敗時的輸入，取消不送請求；生成中停用其他編輯，帳號／對話已切換時不覆蓋另一個畫面。測試：`tests/test_message_edit.py`、`NODE_PATH=/tmp/diji-onboarding/dom-check/node_modules node tests/message-edit.test.cjs`，並保留 `tests/chat-ime.test.cjs` 的輸入法回歸。
- AI 修改助手目前頁面中的已送出指令亦可編輯。每筆指令綁定執行前的草稿 revision；編輯後以 `base_revision` 讀取該快照重新請求模型，以目前 `revision` 作提交衝突檢查，再另存新版本。後續草稿不摻入舊指令的重新生成，亦不刪除。訊息共用元件要允許不同保留說明（對話分支／草稿版本），避免誤導。浮窗編輯指令時隱藏原輸入表單，避免兩個送出入口混淆。

- 聊天 Enter 送出必須先略過 `event.isComposing` 與 `event.keyCode===229`，避免中文選字確認誤送（含 Safari 的 compositionend／keydown 順序）。選字完成後下一次普通 Enter 才送出，Shift+Enter 保持換行。`tests/chat-ime.test.cjs` 載入真實 app 事件監聽器驗證此行為；可用 `NODE_PATH=/tmp/diji-onboarding/dom-check/node_modules node tests/chat-ime.test.cjs` 執行，缺少依賴時先 `npm install --prefix /tmp/diji-onboarding/dom-check jsdom`。此修正不修改 prompt、草稿或對話保存。

- 草稿每次成功同步都在同一個 SQLite transaction 追加 `draft_versions` 完整快照，包含首次生成、手動、AI 修改、確認儲存與回滾；版本不可覆寫或自動清除。`save_draft` 必須同時驗證當前 revision 並更新最新指標。回滾另存新版本，保留被回滾的內容；已存成角色的紀錄改為 fork 新 generation，原角色與原版本保持不變。不得把未成功的 AI 提案列為已保存版本。
- 版本 API 按帳號隔離、no-store；歷史以 100 筆分頁載入，可持續載入更早版本。UI「版本歷史與回滾」先查看再明確還原；還原前完成待同步修改，版本衝突回 409 並保留本機內容。已保存角色可從草稿列表／保存完成畫面進版本歷史，只讀檢視並還原成新草稿。
- 舊資料首次讀取版本歷史時，只從四階段完整輸出、既有 AI 修改前／完成快照及現存完整草稿補入；缺少的中間版本不造假補齊。新版本從成功同步起保存，700ms 防抖期間尚未同步的逐字輸入不算已存版本。測試見 `tests/test_draft_versions.py`：重開、並行、跨帳號、分頁、回滾再回復、已保存角色 fork 與真實快照回填。
- 2026-11-01：117 項 pytest 與三組隔離 DOM 測試通過。Edge 實測手動修改自動新增版本、查看不改現稿、回滾後再次恢復，測試草稿保留連續 7 版；已保存測試角色只讀，還原為獨立新草稿，伺服器比對原角色完全未變。375／768／1024／1440px 無橫向溢位；手機捲到還原按鈕後位置 top 385px、height 44px，可正常操作。查看／還原不呼叫模型。

- 審核頁的 AI 修改助手：`character_generation/revision.py` 要求模型回傳既有末端欄位的 path/value，驗證欄位範圍、型態與可保存大小，保留未修改資料並沿用 `_full_prompt` 重建。`POST /api/character-generations/{id}/revise` 從當前帳號草稿讀取、驗證 revision 與已核准模型越獄；原子保存時再檢查版本，舊結果不可覆蓋新草稿。要求、修改前快照、模型 prompt／輸出、提案與結果版本記錄為 `draft_revision`，不記錄憑證或原始例外訊息。
- 修改助手固定在畫面右下方，只在已有草稿的審核頁出現；1100px 起預設展開並保留右側空間，小視窗／手機預設為可點開的小浮鈕。切換頁面、試聊、保存完成與登出時隱藏。AI 修改期間鎖住審核輸入，浮窗仍可收起；成功刷新欄位並保留展開與捲動狀態，失敗保留原草稿。修改立即同步至伺服器，仍須明確保存才加入角色庫。修改紀錄浮窗顯示本次頁面最近五筆，完整紀錄保存在伺服器。
- 修改助手的右側預留樣式必須高於 `.screen.studio-screen.active` 的 padding 優先級，避免浮窗遮住表單。手機修改紀錄預設收合，輸入與送出按鈕應在展開後可視區內。2026-11-01：110 項 pytest 通過；Edge 真實模型只在指定背景追加測試文字，伺服器比對其餘人設與風格指南未變，重載後修改仍在。1440px 表單右界 1036、浮窗左界 1080；375px 小浮鈕及展開輸入／送出可見，375／768／1024／1440px 無橫向溢位。

- 角色創建成人選項使用白話「角色設定是否包含色情內容」，輔助說明明確區分生成提示與聊天開關；保留 `creator-adult` 識別碼、預設值與原 `is_nsfw` 行為。
- 審核草稿底部提供「測試對話」與明確保存兩個入口。試聊前同步草稿、核對 revision；後端只從當前帳號的生成紀錄重建角色 prompt，共用正式 `execute_interaction`，不接受前端角色正文。試聊的 conversations／memories／relationships／user_profiles 位於帳號 `creator_trials/`，不加入正式角色／聊天／記憶清單；玩家紀錄以 `purpose=draft_trial` 保存版本與角色快照。預設短對話，可切換長對話，好感度關閉；色情設定沿用此次創建選項。測試 API 拒絕他人、舊版本、已保存角色與跨草稿的 chat_id，見 `tests/test_draft_trial.py`。
- 試聊保留原審核 DOM，返回按鈕在生成中仍可使用，返回後保留欄位、展開狀態並聚焦試聊入口；再次測試使用新 chat_id，避免修改後沿用舊試聊記憶。試聊使用自備模型額度，返回不取消已發出的請求；不得用假回覆代替實際測試。
- 試聊顯示時以 `creator-trial-active` 暫時解除內層 creator 的 overflow，讓返回列黏在真正的畫面捲動容器內；手機須捲到輸入區檢查按鈕沒有被頂部導覽遮住，返回／登出／重畫草稿時移除該 class。2026-11-01：100 項 pytest 與隔離 DOM 往返測試通過；Edge 真實試聊兩回合命中剛修改的人設暗號、生成中可返回且保留展開欄位，375／768／1024／1440px 無橫向溢位，試聊沒有加入正式角色庫。

- 角色建立已於 2026-11-01 以 Edge 真實走過：網路參考生成、審核修改、私人保存、開始聊天，修改後背景的唯一測試設定進入實際回覆。結果與限制見 `docs/creator-usability-test.md`。
- 建立角色預設優先 DeepSeek V4.1 Flash，帳號選擇可覆寫。概念暫存鍵為 `diji-creator-brief:<account-id>`；登入完成後才恢復，忽略舊的不分帳號鍵，登出清空畫面。生成中／未同步修改提供離頁提醒；已完成草稿可由伺服器恢復，明確保存後才加入角色庫。

- 玩家紀錄：`player_activity.py` 在 `runtime/users/<account>/player_activity.sqlite3` 保存生成簡報、模型／越獄版本、四階段實際 prompt／輸出、失敗類型、完整草稿與最終角色快照。每輪對話保存模型設定、模式、輸入／回覆及記憶／關係保存狀態；原有 conversations JSON 仍是逐字對話來源。不得保存 transport、供應商憑證或原始例外訊息。DB 0600、帳號資料夾 0700；runtime 與 SQLite 不提交。
- 草稿 API 按登入帳號隔離；PATCH 使用 revision 防止舊頁覆蓋，已加入角色庫的草稿拒絕修改。UI 修改延遲 700ms 同步，只有同步完成才顯示已保存；網路失敗保留離頁警告。歷史階段未記錄者不能反推或偽造；程序意外終止時 running 紀錄僅代表未確認完成，不代表可自動續跑。
- 修改對話保存時保持 `start`／`append`／`set_mode` 的跨程序檔案鎖與原子替換。驗證包括重開資料庫、不同帳號隔離、失敗階段、revision 衝突與並行訊息追加；見 `tests/test_player_activity.py`。
- 2026-11-01 玩家紀錄驗證：本機與 AWS 97 項 pytest 通過。Edge 真實四階段生成測試角色「伺服器保存測試・紙舟」，修改名稱後同步 revision=1，重新整理可從伺服器恢復，不重做模型請求；明確保存後生成紀錄連結私人角色，資料庫權限 0600。測試角色與輸出只保留在 runtime，不提交 Git。
- `character-creator.js` 除了監聽 `diji-workspace-ready`，載入時若 `workspaceAvailable` 已成立也必須立即初始化，避免登入事件先發出時模型選單永久卡住；此情境在 Edge 重整及隔離 DOM 測試均重現。
- 生成成功先驗證再替換現有草稿，HTTP／非 JSON 失敗保留既有審核資料；顯示真實等待秒數，不假造階段進度。保存後隱藏已完成表單、清除該帳號概念暫存，提供聊天、回角色庫及建立另一位選項。
- `CharacterSpec.generation_metadata` 保存一句話介紹、分類與嗜好，審核頁可在展開區修改；不改既有 `_full_prompt` 組裝或四階段生成提示。

- 全站精緻化與動態集中於最後載入的 `ui/ui-polish.css`、`ui/ui-polish.js`；深藍／低彩度青色、現有大字級與 44px 觸控目標維持。`showScreen` 發出 `diji-screen-changed` 更新頂欄頁名與 `aria-current`，展示層不得發模型請求或改帳號／模型路由。
- 切頁、抽屜與面板進場使用 180–280ms 的 opacity/transform，首頁線條僅一次；hover 位移只在精準滑鼠與無減少動態設定下啟用。減少動態時停用 CSS 動畫並取消首頁 Web Animation；內容預設可見，不以 JS 或動畫作為顯示前提。設計規範見 `docs/ui-design.md`。
- 手機從首頁開導覽時沒有 active rail item，焦點退回第一個導覽項目；requestAnimationFrame 執行時必須確認抽屜仍開啟，避免聚焦已隱藏內容。

- 聊天尚未選角時僅顯示引導與「前往角色頁面」按鈕；角色清單及搜尋統一位於角色頁。此引導不受模型商遮罩限制，選角或恢復既有對話後才套用聊天連線 gate，帳號登入限制照常保留。

- 2026-11-01 全站可見文字的明確 px 字級提高一級（+2px），小字下限 16px；既有斷點及 font shorthand 同步調整，繼承字級的控制項沿用父層。CSS 載入 URL 附 `type=20261101-larger-1`；未來調字級需驗證手機換行、窄側欄及登入視窗，不以頁面 zoom 取代文字放大。

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

## Google 登入優先（2026-11-01）

- 初始頁以 `ui/home.css` 作最後載入的首頁樣式：桌面雙欄大標／情境示意，手機先顯示主標與 Google CTA，再顯示示意與介紹。`home-start-label` 保留動態登入／連線／選角文案，箭頭獨立保留；示意固定標示非模型回覆或使用者資料。首頁修改須驗證 375／768／1024／1440px、不橫向溢位、登入入口與匿名 gate，並更新資源版本。

- 公開部署的訪客只看專案介紹與 Google 登入；前端以 `guest-mode` 預設隱藏工作區並使非首頁 inert，session 驗證成功才解鎖。未登入的直接 hash 路由回首頁，不自動彈出登入。登出後立即收回工作區並清空聊天畫面。
- `DIJI_AUTH_REQUIRED=true` 時 middleware 對所有非登入 API 與 OpenAPI 要求 session，未登入回 401/no-store；Google 授權、回呼、session、登出與舊登入相容端點保留。本機模式維持免登入；`/api/auth/session` 的 `auth_required` 明確區分兩模式。健康檢查在公開模式驗證匿名 API 為 401。
- 子介面資料在 `diji-workspace-ready` 後才載入；角色與聊天仍須另行連接模型商。變更入口流程時驗證匿名、Google 回呼後、登出及直接 hash 路由，維持公開介紹頁可讀。

## 年齡確認

- 新手流程：首頁按登入／模型連接狀態顯示下一步。`diji-pending-task` 僅暫存 chat/create-character 目的地，授權後由使用者按繼續返回；建立概念以 sessionStorage 暫存於目前分頁，憑證不進前端。切頁同步 hash，返回鍵依 hash 切換。
- 角色審核：以可編輯欄位保留完整 profile 結構，JSON 僅作進階檢視；保存沿用單一草稿 ID、防重複送出，伺服器以既有 `_full_prompt` 重組人設與風格。保存成功顯示僅自己可見及開始聊天／回角色庫選項，不自動開對話。

- 建立角色頁與聊天共用模型商 gate 狀態；未連接或無法確認連接時霧化並 inert，連接後共同解鎖。每次進入建立角色頁重新查詢，保留左側導覽可用。

- 未連接模型商時整個聊天頁以 provider gate 霧化鎖定，背景 direct children 使用 inert 阻止滑鼠／鍵盤操作，提示僅文字。左側導覽與頂部帳號區保持可用；確認連接後解除。網路錯誤亦鎖定但明示狀態無法確認。

- 聊天的模型連線區在未連接時僅顯示「尚未連接模型商」及連接用途／自備額度說明，將所有選項收於 `chat-provider-controls` 並隱藏；不顯示設定按鈕。已連接才顯示模型與互動選項。

- 模型商卡片「撤銷連接」呼叫帳號限定 DELETE，清除加密金鑰與待完成連接 state，包含舊 OpenRouter 登入帳號金鑰；保留 DIJI 登入、角色和費用歷史。僅本服務解除綁定，供應商端撤銷需前往金鑰管理頁；已開始請求不取消。

- 聊天不再使用 `live-mode` 勾選。送出前確認當前帳號模型商連接狀態，右側顯示已連接服務、有效額度順序與模型；未連接提供「按此設定模型商」並在送出時導向模型連線頁。

- 首頁品牌入口沿用 Web App manifest 的 `/icons/diji-192.png`，置於頂部帳號列與登入垂直對齊。側欄不再放文字 D；手機仍保留左上主要選單按鈕。

- BazaarLink 費用從模型 JSON 回應 `usage.cost` 按帳號記錄於 SQLite `provider_usage`，以請求 ID 去重、Decimal 累計。記憶／好感度／角色生成子請求皆納入，最近一次代表單次模型請求，並非整個多階段流程。介面顯示啟用紀錄後的 DIJI 累計，進入模型連線頁後每 3 秒刷新；缺失費用不可當作 0。

- 模型連線頁由 `ui/connection-layout.css` 管理：頁首、兩張服務卡、獨立順序卡；手機堆疊。優先順序保留原生 select 的鍵盤與手機選擇器，外觀以深藍底、自訂箭頭及青色聚焦環統一。

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

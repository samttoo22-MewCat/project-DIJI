# DIJI 架構與 ai-server 對齊範圍

DIJI 是把既有 ai-server 的可開源核心拆成可檢查模組，而不是重寫角色扮演規則。以下層次的資料流必須保持順序。

```text
角色概念
  -> character_generation（人設 JSON -> 風格指南 -> 完整 prompt）
互動請求
  -> experiments（內部風格 / 模型對應越獄 / 結尾規則）
  -> interaction（角色、使用者、歷史、時間、記憶、關係上下文）
  -> model_adapter（OpenRouter/Skylark、DIGI vLLM、ORPO）
  -> postprocess（時間戳、標籤、MEM 洩漏、標點）
  -> memory_extraction -> memory_store
  -> relationship + user_profile（符合設定時的狀態與使用者偏好保存）
```

角色保存另以 `CharacterSpec.generation_metadata` 保留生成階段的一句話介紹、分類與嗜好，與完整人設／風格指南分開，不改原 `_full_prompt` 組裝。這些資料原先未由 UI 一併提交，已於 2026-11-01 的建立流程實測後補齊。

`player_activity.py` 是旁路持久化層，使用每帳號 SQLite 保存角色生成四階段的實際輸入／輸出、草稿、保存角色快照與對話回合。此層不改 prompt、記憶抽取或關係判決。草稿修訂以 revision 防止覆寫，完成後的草稿能從建立角色頁恢復；歷史未記錄的階段不可補造。對話 JSON 的修改以檔案鎖與原子替換保護，與事件記憶分開。

`player_personas.py` 保存玩家自行建立的虛構身分，帳號獨立 `player_personas.sqlite3`；不是好感度判決抽取的 `user_profile`。`/api/player-personas` 提供列表、新增與更新，建立對話時解析該帳號的 ID，將 `UserPersona` 快照寫入逐字稿。正式互動使用伺服器保存的快照，名稱與描述仍注入原有使用者資訊區塊，選填性別／年齡併入該區塊描述。聊天選用另一份設定會建立全新 chat_id，沒有舊歷史／記憶／關係；編輯分支保留原 persona 快照。設定修改只影響之後新開的對話；舊資料不補造未知的歷史人設；公開模式與本機模式的續寫方式見下段。自訂玩家人設的自動偏好保存於該對話的 `branch_profiles/<chat-id>/`，避免不同玩家身分互相混入；預設與舊對話保留既有跨會話 profile 行為。

公開服務開啟新的正式聊天與草稿試聊前，必須先有帳號玩家設定。建立對話解析玩家 ID；只有一份時 API 可自動選用，多份未指定時回 409。UI 一律要求先建立並明確選用；未設定時導向玩家頁，已選角色但未選玩家時顯示阻擋提示。缺少玩家 ID 的公開舊對話保留可讀，禁止直接續寫，改以所選玩家另開新對話；上述舊資料首次互動固定 request persona 的相容行為僅保留在本機模式。草稿試聊使用相同帳號設定與快照，切換身分另開新的試聊，角色生成與修改本身不要求先有玩家設定。

DELETE `/api/player-personas/{id}` 只刪除目前帳號設定庫的單一資料列；查無該帳號設定回 404。確認刪除後無法再選用該 ID 開新對話，但已開始的正式／試聊 transcript、persona 快照、記憶、關係與自動偏好都保留；刪除最後一份也不影響這些對話續聊及編輯重新生成。續寫直接讀取對話快照，不查已刪來源。前端下拉顯示「此對話保存版本」，新開對話的選擇仍須通過目前帳號設定庫驗證。

草稿的 `test-interactions` 端點驗證帳號與 revision，從伺服器草稿重建角色，經同一個 `execute_interaction` 與 `InteractionService` 組裝長／短對話 prompt、模型對應越獄與記憶。資料寫入帳號的 `creator_trials/` 子目錄，與正式角色庫及聊天隔離；預設不啟用好感度。試聊不是保存角色，修改後再次開啟使用新 chat_id，原試聊仍保存在伺服器，並以玩家紀錄的 `purpose=draft_trial` 連結生成紀錄與版本。

## 不可改變的行為

玩家訊息編輯採對話分支，不就地刪改舊紀錄。正式與試聊入口都驗證來源對話指紋、玩家訊息索引與帳號，複製編輯點之前的訊息，將修改後訊息送入同一個 `execute_interaction`。新 record 記錄 parent chat 與 edited index；模型、長短對話、越獄、事件記憶抽取與好感度判決的原流程不變。

AI 修改指令的編輯使用草稿版本機制：`base_revision` 指向原指令執行前的快照，`revision` 驗證目前提交版本；生成結果另存為新版本，之後的修改保留在歷史，不混入重新生成的基礎。這與玩家對話分支分開，不觸發正式聊天或角色保存。

每輪生成前保存狀態快照；memory、relationship、profile 的 JSON 以內容雜湊存入 `checkpoint_values`，`turn_checkpoints` 保存引用及前文指紋。編輯分支只恢復精確匹配的快照，後續偏好保存至 `branch_profiles/<chat-id>/`，避免污染原對話或全域偏好。舊資料沒有快照時，不複製編輯點之後的狀態：保留前文，記憶與關係狀態重新累積並告知使用者。原資料不清除，生成失敗的新分支也保留已送出修改。

`player_activity.sqlite3` 的 `draft_versions` 以 `(run_id, revision)` 保存完整且不可覆寫的草稿。新版本快照與 runs 的最新草稿指標在同一個 `BEGIN IMMEDIATE` transaction 提交；手動同步、AI 修改及確認儲存均經此處。回滾將所選舊版內容另存為新 revision，保留回滾前版本。已儲存角色的回滾建立新 generation 並記錄 parent generation/version，不修改原角色。版本列表分頁只限制一次回傳數，不裁切資料庫歷史。

舊資料僅由已保存的四階段原始回傳、AI 修改前與成功提案快照、目前草稿補入版本；未記錄的中間內容無法恢復。此資料表與逐字對話／事件記憶分開，不改 ai-server prompt 與生成邏輯。查看與回滾不呼叫模型。

角色草稿修改是生成流程的額外入口，沒有更改原四階段提示。`revision.py` 將模型輸出限制為既有末端欄位的變更清單，拒絕整份人設替換、未知路徑與型態不符，再用原 `_full_prompt` 重建完整 prompt。API 從帳號草稿讀取並以 revision 原子提交；模型生成期間若其他分頁已更新，回 409 並保留較新版本。每次修改以玩家紀錄 `draft_revision` 保存修改前資料、指令、prompt、原始回傳、提案與結果版本。

- 使用者可在帳號限定的記憶工作區編輯單筆摘要、分類、關鍵字、重點與回覆摘要，或確認後刪除單筆；原始使用者訊息、時間與對話檔保留。entries API 使用整份記憶檔版本、位置與內容的指紋檢查，舊版本不覆寫新資料。記憶追加、編輯、單筆刪除與 reset 在 Linux/macOS 共用 `fcntl` 檔案鎖，並以同目錄暫存檔原子替換 JSON；沒有新增回收桶或還原功能。

- 記憶注入模式使用 `MEM0_INJECT_MODE` 的 `system`、`user`、`none`；請求的 `inject_memory` 覆寫此設定。
- 常規記憶以 `<MEM>` 放入最近 20 筆；目前使用者訊息會以提取後的 `keywords` 值搜尋，另放入 `<RELEVANT_MEM>`。分類搜尋命中數只作 metadata，排序仍依時間新到舊。
- 依使用者 2026-11-01 指示，多值 keyword 會另按頓號、中英文逗號、分號與換行拆分比對，例如「青禾」可命中「青禾、夜蘭」。完整值比對保留、詞組內空格不拆分、時間排序與注入位置不變；此為明確核准的原 ai-server 行為修正，不是語意搜尋。
- OpenRouter 相容的記憶抽取明確停用推理 `reasoning.enabled=false`，讓既有 1000-token 輸出預算用於 JSON；這是模型供應商相容性修正，不改 ai-server 的記憶格式、提示與檢索方式。
- 已有完整逐字對話但尚未建立事件記憶時，登入者可從該對話的右側面板主動回填；回填只處理自己的一個 `chat_id`、最多最近 80 則訊息、每 8 則獨立抽取。所有批次成功前不寫入任何記憶，已有事件記憶的對話不重複回填。
- 模型路由順序為 DIGI/Joi 的 vLLM、ORPO 遠端 `/api/generate`、Skylark、其餘 OpenRouter 相容端點。未設定必要金鑰時必須在網路請求前失敗。
- 輸出清理先移除時間、處理文字換行與內部標籤，再正規化標點；不可將提示詞內部標籤輸出給使用者。
- 關係狀態只有五階：陌生、熟識、親近、親密、靈魂。分數門檻依序是 40、80、120、180；第一階可單憑分數進入第二階，其後必須同時出現對應關鍵事件。`favorability_judge.py` 使用原始 judge 的 `google/gemini-2.5-flash`、四維評分、深度乘數、致命失誤、情緒、關鍵事件與 profile 欄位契約；請求或 JSON 解析失敗時維持零分回退。
- `reset=true` 對齊原始服務：只清除事件記憶與關係狀態。完整逐字對話是 DIJI 額外的持久化層，故不隨 reset 刪除；使用者 profile 為跨會話狀態，也不刪除。
- 越獄是 `PromptExperiment` 的資料，不是程式常數；只有明確 `is_nsfw` 的互動才會放入上下文。`/api/interactions` 會依所選模型解析同一筆已核准越獄，前端不得指定或覆寫此對應。

## 明確不遷移

角色圖片生成、ComfyUI、訓練資料集、使用者既有記憶檔與運行日誌都不進入 repository，也不作為預設執行路徑。

## API 邊界

### 公開請求安全邊界

公開模式的模型輸入以 `public_models.py` 驗證，只能使用當前帳號已連接的 OpenRouter／BazaarLink 憑證，拒絕自訂 URL 與 DIGI、ORPO、Skylark 等舊伺服器路由。聊天、編輯重新生成、角色生成、草稿修改與試聊都在呼叫模型前驗證；固定模型的記憶／好感度仍使用同一帳號路由。本機模式保留原模型 adapter 與 prompt 組裝。

Google 登入新增 S256 PKCE 與 10 分鐘瀏覽器綁定 Cookie。伺服器以 state／binding 的雜湊與一次性 verifier 驗證回呼，另一瀏覽器不能完成該登入，舊 session 不需重新建立。這只處理 Google 登入流程的綁定，不代表其他寫入 API 已具有完整 Origin／CSRF 防護。

`work_limits.py` 在單程序限制同時生成工作數、每帳號頻率、工作逾時及 API 寫入體積。生成工作涵蓋原本的回覆、記憶及關係處理，也涵蓋角色流程各階段；讀取資料與查看頁面不佔生成名額。逾時透過同一 ASGI 執行鏈取消，釋放名額及 chat 回合鎖；已開始的供應商請求可能仍已計費，沒有自動跨供應商重試。多程序或多台主機須另設共享限流狀態，不能直接把每個程序的上限當成全站上限。

共用 FlowSpec 作預設，帳號 flow 及私人角色保存於同一份帳號 catalog。流程讀寫、bootstrap 與 preview 都依帳號解析，私人 catalog 保存採鎖與原子替換。記憶抽取錯誤只保存通用診斷代碼；舊記憶的例外文字及 traceback 在讀取時遮蔽，原私有檔案不被批次刪改。

### 多人並行與個人越獄

登入結果、解密後模型憑證、store 與 activity 在同一請求內重用，請求結束即清除。模型的 HTTP client 依該請求的供應商／憑證重用連線，完成或失敗後關閉；不在玩家之間共用憑證、client 或事件記憶。帳號 SQLite 連線明確提交／回滾並關閉。聊天的 prompt 讀取、快照與逐字／事件記憶保存移至執行緒；LLM 及原有記憶／關係處理順序不變。

同一帳號的同一 chat_id 以非阻塞檔案鎖保護整個回合，重複請求回 409，避免交錯寫成「玩家、玩家、角色、角色」及額外模型費用。不同玩家仍可並行。這只適用於目前單機共享磁碟部署，不是工作佇列或可保證完成的背景工作；全站工作限制另由 work_limits 處理。角色目錄已加入共用寫入鎖與原子替換，關係／profile 的跨對話同步寫入仍有後續優化空間，不把本次改動當成所有儲存層都已支援多程序交易。

2026-11-01 的相同模擬模型／20 帳號測試：登入查詢從 80 次減為 20 次，憑證載入從 40 次減為 20 次；同時進入模型的測試請求為 20。此為隔離 ASGI 測試，不代表約 1GB 生產主機的真實模型容量保證，也不以單次耗時差異推算效能提升百分比。

公開模式以共用越獄作預設，個人修改存於 `runtime/users/<account>/jailbreaks.json`，列表按 ID 合併。沒有修改的項目隨預設更新，已修改的項目持續使用個人版本。個人 experiment 亦隔離保存。刪除個人覆寫後回到預設；共用預設只可由部署維護，玩家 API 不改寫。帳號覆寫的 JSON 使用檔案鎖與原子替換；聊天、角色生成、AI 修改及試聊皆使用同一帳號的有效越獄。

`POST /api/prompt-preview` 僅檢查 prompt，不呼叫模型。模型請求入口包括 `POST /api/characters/generate`、`POST /api/interactions`、`POST /api/conversations/{chat_id}/edit`、`POST /api/character-generations/{id}/revise`、`POST /api/character-generations/{id}/test-interactions` 及其 `/edit`，還有 `POST /api/memories/{chat_id}/extract` 與 `/backfill`；它們都需要使用者自己的 provider 憑證，並受公開生成工作限制。登入與額度查詢會聯絡供應商，但不生成模型內容，也不佔生成名額。

## 公開 Web App 外殼

登入視窗先提供隱私條款與使用者規約全文連結，以及對話／生成資料保存、模型商傳輸與自備額度摘要。使用者自行勾選後，以原生 POST 表單前往 Google；不以 fetch 跟隨跨來源 OAuth。GET 舊登入入口只回到確認畫面。後端檢查 Origin 與目前文件版本，將同意版本連到 OAuth state，登入成功後才存入帳號同意紀錄。版本為兩份部署文件全文的 SHA-256，日期相同但內容變動仍會改版；流程中若版本改變需重新確認，既有 session 不會被偽造同意紀錄。

`/legal/privacy`、`/legal/terms` 公開呈現同一份 repository 文件，表格使用 Python-Markdown 渲染，並以僅限這兩個固定來源的查表路由發布；不提供任意檔案瀏覽或使用者 Markdown 輸入。條款頁不執行腳本，使用同源樣式；登入版本 metadata 不快取。Service Worker 不將條款頁覆寫成離線首頁。

公開帳號識別與模型供應商連線必須是兩個獨立層。首頁不強制要求登入；使用者點擊右上角「登入」，或嘗試建立／開啟／發送對話時，才開啟只含 Google 的登入視窗。Google OAuth 以 `DIJI_GOOGLE_CLIENT_ID`、`DIJI_GOOGLE_CLIENT_SECRET` 與 `DIJI_GOOGLE_OAUTH_CALLBACK_URL` 在伺服器端交換 OIDC code；帳號與雜湊 session 分別存於 `google_users`、`google_sessions`，使用者資料仍隔離在 `runtime/users/<user-id>/`。Google 登入可建立並保存對話；沒有模型連線設定時，會在任何模型請求前回覆 `409`，絕不暗中使用全站金鑰。現有 OpenRouter PKCE 資料僅為舊帳號相容與未來供應商綁定保留，不能出現在目前登入 UI。

`ui/manifest.webmanifest`、`ui/icons/` 與 `ui/service-worker.js` 由同一個 FastAPI 靜態根路由提供，讓公開 HTTPS 入口能安裝為 PWA。Service Worker 的範圍只限靜態介面外殼：安裝時預取首頁、manifest 與圖示，使用時才快取同源的樣式、腳本、字型與圖片。`/api/`、帳號 session、OAuth、對話、角色、記憶與模型請求均維持 network-only，絕不放入 Cache Storage；因此離線只能重開既有的介面，不能登入或互動。

Android/Chromium 使用瀏覽器提供的安裝提示；iPhone/iPad 則由介面說明 Safari 的「分享 → 加入主畫面 → 以 Web App 開啟」流程。這是平台限制，而不是離線資料同步機制。

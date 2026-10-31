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

## 不可改變的行為

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

`POST /api/prompt-preview` 僅檢查 prompt，不呼叫模型。`POST /api/characters/generate`、`POST /api/interactions`、`POST /api/memories/{chat_id}/extract`、`POST /api/memories/{chat_id}/backfill` 是唯一可能發送模型請求的路由；它們都需要使用者自行配置 provider 金鑰。

## 公開 Web App 外殼

公開帳號識別與模型供應商連線必須是兩個獨立層。首頁不強制要求登入；使用者點擊右上角「登入」，或嘗試建立／開啟／發送對話時，才開啟只含 Google 的登入視窗。Google OAuth 以 `DIJI_GOOGLE_CLIENT_ID`、`DIJI_GOOGLE_CLIENT_SECRET` 與 `DIJI_GOOGLE_OAUTH_CALLBACK_URL` 在伺服器端交換 OIDC code；帳號與雜湊 session 分別存於 `google_users`、`google_sessions`，使用者資料仍隔離在 `runtime/users/<user-id>/`。Google 登入可建立並保存對話；沒有模型連線設定時，會在任何模型請求前回覆 `409`，絕不暗中使用全站金鑰。現有 OpenRouter PKCE 資料僅為舊帳號相容與未來供應商綁定保留，不能出現在目前登入 UI。

`ui/manifest.webmanifest`、`ui/icons/` 與 `ui/service-worker.js` 由同一個 FastAPI 靜態根路由提供，讓公開 HTTPS 入口能安裝為 PWA。Service Worker 的範圍只限靜態介面外殼：安裝時預取首頁、manifest 與圖示，使用時才快取同源的樣式、腳本、字型與圖片。`/api/`、帳號 session、OAuth、對話、角色、記憶與模型請求均維持 network-only，絕不放入 Cache Storage；因此離線只能重開既有的介面，不能登入或互動。

Android/Chromium 使用瀏覽器提供的安裝提示；iPhone/iPad 則由介面說明 Safari 的「分享 → 加入主畫面 → 以 Web App 開啟」流程。這是平台限制，而不是離線資料同步機制。

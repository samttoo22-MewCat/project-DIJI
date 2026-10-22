# 本機工作台資料介面

本機工作台預設只保存可攜的角色與流程設定；外部模型只能由下列明確 POST 路由觸發。

- `GET /api/bootstrap`：讀取角色與流程。
- `PUT /api/characters/{id}`：保存一個 `CharacterSpec`。
- `PUT /api/flows/{id}`：保存一個 `FlowSpec`。
- `GET /api/memories/{chat_id}`：讀取該會話的事件記憶。
- `PUT /api/memories/{chat_id}`：保存一筆事件記憶；欄位使用 ai-server 的 `timestamp`、`type`、`summary`、`user_message`、`character_response_summary`、`key_points` 與 `keywords`。
- `POST /api/memories/{chat_id}/extract`：明確要求時才使用和 ai-server 相同的抽取提示與 `google/gemini-2.5-flash` 設定，保存萃取出的事件記憶。需要 `OPENROUTER_API_KEY`；未設定時會保存 ai-server 相同的「標記」錯誤事件，不會產生外部請求。
- `POST /api/prompt-preview`：依角色、流程、場景、歷史與該 `chat_id` 已保存的記憶回傳可檢查的 prompt bundle；`MEM0_INJECT_MODE` 依 ai-server 支援 `system`／`user`／`none`，可被請求的 `inject_memory` 覆寫；不會呼叫模型。
- `GET /api/conversations`：列出所有已儲存對話的角色、最後更新時間與預覽。
- `POST /api/conversations`：建立一段空白本機對話；`GET /api/conversations/{chat_id}`：讀取完整逐字稿。實際互動路由會先保存使用者訊息，僅在成功後追加角色回覆。
- `GET`／`PUT /api/experiments`：內部讀寫版本化的故事/對話風格、越獄參照與結尾規則；工作台不提供流程實驗 UI。
- `GET`／`PUT`／`DELETE /api/jailbreaks`：讀寫本機越獄目錄；`POST /api/jailbreaks/import-recent` 只匯入可審核中繼資料。
- `PUT /api/settings/openrouter-key`：接收並保存使用者自己的 OpenRouter API key 到本機 `.env`，立即套用到服務程序；此路由不會回傳金鑰，也不會將它寫入瀏覽器儲存空間。
- `POST /api/characters/generate`：執行三段人設生成。它需要 `OPENROUTER_API_KEY`，且只在此端點被呼叫時才發出請求；若為成人虛構分類，所選模型必須有已核准越獄。
- `POST /api/interactions`：以完整 `InteractionRequest` 組裝 ai-server 相容的訊息、依模型設定路由、清理回覆、抽取事件記憶，並保存符合條件的關係狀態。成人虛構互動會依請求模型強制解析已核准越獄，忽略前端傳入的 experiment id。
- `POST /api/interactions` 傳入 `reset=true` 時，會依 ai-server 原行為只清除該會話的事件記憶與關係狀態；完整逐字對話與使用者 profile 不會被刪除。
- `GET /api/relationships/{chat_id}`：讀取該會話的五階段好感度狀態。關係評估器尚未設定時，此端點會保留初始狀態，並不假造 LLM 判決。

伺服器只綁定 `127.0.0.1:8080`。角色與流程保存到 `runtime/catalog.json`；實驗設定為 `runtime/experiments.json`；完整對話保存到 `runtime/conversations/{chat_id}.json`；事件記憶保存到 `runtime/memories/{chat_id}.json`；關係狀態保存到 `runtime/relationships/{chat_id}.json`；關係判決萃取出的使用者偏好保存到 `runtime/user_profiles/{user_id}.json`，且只會作為內部關係引導資料。初始角色與流程可讀取，但不會因為讀取就建立 runtime 檔案。

`CharacterSpec` 的版本目前固定為 `1`，包含 `id`、`name`、`premise`、`voice`、`relationship_start`。`FlowSpec` 也固定為版本 `1`，包含 `template` 與提示層順序。

瀏覽器工作台預設為安全預覽：送出訊息不會產生假回覆。使用者必須勾選「啟用實際模型請求」才會呼叫 `/api/interactions`，而且每一次「新對話」會生成新的 `chat_id`，避免不同會話共用記憶檔。

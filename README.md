# DIJI

DIJI 是一個非商業、可自架的 Python 角色扮演實驗框架。

它不是單純把一大段人設與聊天紀錄丟給模型，而是把角色生成、逐字對話、事件記憶、關係狀態、寫作模式與可審核的實驗設定拆開。它來自我做中文成人文字角色扮演時遇到的實際問題：角色太容易 OOC、聊久了忘記、寫作節奏崩壞，以及模型限制和實驗設定混在一起後完全無法維護。

DIJI 的目標不是宣稱造出有意識的角色，而是讓這些互動條件有清楚的資料邊界、可檢查的 prompt 組裝流程與可重現的測試。

> 成人虛構互動是此框架的使用情境之一。專案不包含真人私密資料、角色圖片、ComfyUI、訓練資料或任何未審核的外部提示詞；使用者仍須自行遵守模型供應商、部署平台與所在地法律規範。

## 功能與資料流

```text
創作簡報
  → 角色 JSON 草稿 → 對話風格 → 完整 prompt
  → 使用者審核並明確儲存角色

使用者訊息
  → 保存逐字對話
  → 角色／關係／記憶／場景／歷史組裝
  → 模型 adapter
  → 保存角色回覆
  → 事件記憶抽取
  → 選用：關係與偏好更新
```

核心模組：

- `character_generation/`：創作簡報到可審核角色草稿；只有 `POST /api/characters/generate` 會呼叫生成模型。
- `interaction/`：組裝上下文、呼叫模型、清理輸出、保存記憶與更新關係。
- `conversation_store`：保存完整逐字對話，供 UI 恢復聊天；不取代事件記憶。
- `memory_store`：保存事件記憶並提供近期、關鍵字與分類取回。
- `relationship`／`favorability_judge`：五階段關係、邊界、四維分數與關鍵事件規則。
- `prompt_assembly`：建立可檢查的 prompt bundle，不負責呼叫模型。
- `experiments/`：版本化流程設定與越獄實驗；不內嵌在核心互動層。

詳細架構請看 [docs/architecture.md](docs/architecture.md)。

## 快速開始

需要 Python 3.11 以上。

```bash
git clone https://github.com/samttoo22-MewCat/project-DIJI.git
cd project-DIJI
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
python ui_server.py
```

開啟 [http://127.0.0.1:8080](http://127.0.0.1:8080)。沒有 provider key 時，角色庫、資料結構與 UI 預覽仍可使用；實際模型請求會在送出前失敗，而不是偷偷改用共用金鑰。

若要呼叫 OpenRouter，編輯本機 `.env`：

```dotenv
OPENROUTER_API_KEY=請填入自己的金鑰
```

`.env` 不得提交。設定頁輸入的 key 只會寫入本機 `.env`，不會被 API 讀回，也不會儲存在瀏覽器 localStorage。

## 本機資料與隱私

預設資料皆在本機 `runtime/`：

```text
runtime/catalog.json                       # 角色與流程資料
runtime/conversations/{chat_id}.json      # 完整逐字對話
runtime/memories/{chat_id}.json           # 事件記憶
runtime/jailbreaks.json                   # 本機越獄工作台資料
runtime/users/{user-id}/                  # 公開部署時的使用者隔離資料
runtime/accounts.sqlite3                  # 公開部署時的帳號與 session
```

逐字對話、事件記憶與關係狀態是不同資料：重置互動只清除該對話的事件記憶與關係，不刪除逐字對話或使用者 profile。完整說明見 [docs/local-first.md](docs/local-first.md)。

## 寫作模式與記憶

每段對話會保存 `chat_mode`：

- `story`：小說體、分段，預設約 300–700 字。
- `dialog`：短訊息模式，目標約 50 字。

prompt 的固定組裝順序為：角色／風格 → 關係引導（啟用時）→ 記憶與相關記憶 → 時間 → 收尾規則 → 歷史 → 本回合 OOC。`<MEM>` 最多 1,200 字元，近期記憶最多 20 筆。

## 越獄實驗的邊界

DIJI 的越獄工作台是實驗與審核層，不是外部提示詞的自動套用器：

- 外部匯入只保存模型、來源、日期、指南路徑與審核狀態等中繼資料，預設為 `metadata_only`，不含外部 prompt。
- 只有人工填入且標記為 `approved` 的本機內容，才會被後端依選定模型解析並建立對應 experiment。
- 前端不能以自訂 experiment id 覆寫後端的模型對應；未啟用成人內容時不注入。

本專案不承諾繞過任何模型供應商或平台規範。

## 測試

```bash
python -m compileall -q src
pytest -q
```

測試涵蓋角色生成、互動資料流、prompt 組裝、記憶回填、角色匯入、越獄目錄、OAuth／帳號資料隔離與 UI 檔案契約。

## 部署

服務預設只綁定 `127.0.0.1:8080`，建議先以 SSH tunnel 使用：

```bash
ssh -N -L 127.0.0.1:8080:127.0.0.1:8080 user@your-host
```

Kali／systemd 使用者服務可執行：

```bash
./scripts/install-user-service
./scripts/diji-healthcheck
```

不要把服務直接改成 `0.0.0.0`，也不要把 `.env`、`runtime/`、OAuth 憑證、provider key 或 Tunnel token 放進 repository。公開部署的 Google OAuth 與供應商綁定是獨立流程，請先閱讀 `AGENTS.md` 的部署約束後再開放外網。

## 文件

- [架構](docs/architecture.md)
- [遷移地圖](docs/migration-map.md)
- [本機資料介面](docs/local-first.md)
- [原始 ai-server 行為對照](docs/ai-server-parity-audit.md)

## License

[MIT License](LICENSE) © 2026 張芮綾（MewCat）。允許商用、修改、散布與再授權；所有副本或實質部分都必須保留此姓名標示與 MIT 授權文字。

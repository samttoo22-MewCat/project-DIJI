# DIJI

DIJI 是一個可自架的 Python 角色互動應用程式。它將角色定義、逐字對話、事件記憶、關係狀態、prompt 組裝與模型呼叫拆為可獨立檢查的模組。

## 架構

```text
創作簡報
  → 角色生成 pipeline
  → 已審核的角色紀錄

使用者訊息
  → 保存逐字對話
  → 組裝上下文
       角色／風格 + 關係 + 記憶 + 時間 + 歷史 + OOC
  → 模型 adapter
  → 保存回覆
  → 抽取事件記憶
  → 選用：更新關係狀態
```

| 模組 | 職責 |
| --- | --- |
| `src/diji/local_app.py` | FastAPI 路由、請求驗證與應用程式組裝 |
| `character_generation/` | 產生與修訂結構化角色草稿 |
| `conversation_store.py` | 保存每段對話的完整逐字紀錄 |
| `memory_store.py`／`memory_extraction.py` | 將事件記憶與逐字對話分開保存、取回 |
| `relationship.py`／`favorability_judge.py` | 維護關係階段、界線與選用好感度狀態 |
| `prompt_assembly.py` | 建立可檢查的 prompt bundle，不直接呼叫 provider |
| `model_adapter.py` | 呼叫模型 provider 並正規化回應 |
| `experiments/` | 版本化互動設定與已審核越獄中繼資料 |
| `runtime/` | 僅供執行期使用的資料；禁止提交 |

互動 prompt 的固定順序為：角色／風格、選用關係引導、記憶與相關記憶、時間、收尾規則、歷史、當回合 OOC。`story` 與 `dialog` 是持久化對話模式；UI 分別顯示為長對話與短對話。

## 需求

- Python 3.11 以上
- 只有發送實際模型請求時才需要 OpenRouter API key

## 安裝

```bash
git clone https://github.com/samttoo22-MewCat/project-DIJI.git
cd project-DIJI
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
```

## 設定

只在 `.env` 設定目前部署模式需要的變數。

| 變數 | 用途 |
| --- | --- |
| `OPENROUTER_API_KEY` | 啟用模型 provider 請求 |
| `DIJI_AUTH_REQUIRED` | 啟用公開部署的帳號驗證 |
| `DIJI_GOOGLE_CLIENT_ID` | Google OAuth 用戶端識別 |
| `DIJI_GOOGLE_CLIENT_SECRET` | Google OAuth 用戶端密鑰 |
| `DIJI_GOOGLE_OAUTH_CALLBACK_URL` | Google OAuth 公開回呼網址 |
| `DIJI_CREDENTIAL_ENCRYPTION_KEY` | 加密帳號保存的 provider 憑證 |

不得提交 `.env`、`runtime/`、OAuth 憑證、provider key 或 tunnel token。

## 本機執行

```bash
python ui_server.py
```

服務只監聽 `127.0.0.1:8080`。使用瀏覽器開啟 `http://127.0.0.1:8080`。未設定 provider key 時，UI 與本機資料結構仍可使用；需要模型的請求會明確失敗。

## 執行期資料

```text
runtime/catalog.json                       # 角色與流程目錄
runtime/conversations/{chat_id}.json       # 完整逐字對話
runtime/memories/{chat_id}.json            # 抽取後的事件記憶
runtime/jailbreaks.json                    # 已審核的本機越獄目錄
runtime/users/{user-id}/                   # 帳號隔離的執行期資料
runtime/accounts.sqlite3                   # 帳號與 session
```

重置互動只會刪除該 `chat_id` 的事件記憶與關係狀態，不會刪除逐字對話或使用者 profile。

## 測試

```bash
python -m compileall -q src
pytest -q
./scripts/diji-healthcheck
```

## 部署

使用隨附的使用者層級 systemd service 讓服務持續執行：

```bash
./scripts/install-user-service
systemctl --user restart diji-ui.service
./scripts/diji-healthcheck
```

服務應維持 loopback-only。公開存取應透過已驗證的反向代理或 tunnel。只透過 SSH 使用遠端服務時：

```bash
ssh -N -L 127.0.0.1:8080:127.0.0.1:8080 user@your-host
```

## 技術文件

- [架構](docs/architecture.md)
- [遷移地圖](docs/migration-map.md)
- [本機資料介面](docs/local-first.md)
- [ai-server 行為對照](docs/ai-server-parity-audit.md)

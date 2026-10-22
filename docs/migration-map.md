# ai-server 遷移地圖

| ai-server 邏輯 | DIJI 模組 | 驗證重點 |
| --- | --- | --- |
| `OC_creator.py`、`style_creator.py`、`full_prompt_creator.py` | `character_generation/service.py` | 三段呼叫順序、JSON 人設、搜尋模型後綴 |
| 主互動請求與上下文組裝 | `domain.py`、`interaction/service.py` | 記憶模式、歷史、時間、OOC、實驗設定順序 |
| provider 路由 | `model_adapter.py` | DIGI、ORPO、Skylark、OpenRouter payload |
| 回覆清理 | `postprocess.py` | 時間、標籤、MEM 洩漏、標點處理順序 |
| `mem0_creator.py` | `memory_extraction.py`、`memory_store.py` | JSON 抽取、容錯記憶、關鍵字/分類檢索 |
| `favorability_judge.py` | `favorability_judge.py`、`relationship.py`、`user_profile.py` | 五階段、四維分數、關鍵事件、原始 judge 模型與完整評分欄位、容錯回退、使用者 profile 持久化 |
| 主互動的 `reset` 分支與對話模式 | `local_app.py`、`interaction/service.py` | reset 只清記憶／關係；對話模式保留短訊息與自然資訊分享層 |
| 前端設定與本機調試 | `local_app.py`、`ui/` | 僅 loopback、明確 POST 才觸發模型 |

此表是行為對照，不是將 ai-server 中的私有資料、模型權限或任何 generated output 搬進 DIJI。

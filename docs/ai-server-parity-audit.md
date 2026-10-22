# ai-server 架構逐項對照

本文件的基準是本機可讀原始副本 `rpdev/rp_llm_api/nsfw_llm_api_server_dev.py`，SHA-256 為 `10db2567bd6105a360075441f313abd3130d825bdafcbde04481ebd5c571f2a5`。Kali 的 SSH 重新驗證不可用前，不可把此 hash 宣稱為遠端目前版本。

## 已等價的執行結構

| 原始層 | DIJI 實作 | 驗證 |
| --- | --- | --- |
| story / dialog 分流 | `interaction/service.py` 依 `chat_mode` 選 `DEFAULT_STORY_STYLE` 或 `DEFAULT_DIALOG_STYLE` | `test_story_and_dialog_keep_separate_ai_server_format_rules` |
| 共通格式、小說體／短訊息規則 | `experiments/models.py` 的 `DEFAULT_COMMON_WRITING_RULES`、`DEFAULT_STORY_STYLE`、`DEFAULT_DIALOG_STYLE` | 同上 |
| OC 建立、風格指南、完整角色 prompt | `character_generation/service.py` 的四段生成流程 | `test_character_pipeline_keeps_the_ai_server_creator_stages` |
| 角色、使用者、場景、範例對話組裝 | `interaction/service.py::_base_prompt` | `test_interaction_turn_matches_the_architecture_and_persists_outputs` |
| 好感度啟用、階段狀態、角色專屬設定、profile、低分防禦 | `relationship.py`、`user_profile.py`、`interaction/service.py::_favorability_guidance` | `test_favorability_keeps_stage_config_and_low_score_defense` |
| `<MEM>`、`<RELEVANT_MEM>`、時間、結尾規則、歷史、OOC 的順序 | `interaction/service.py::build_messages`、`prompt_assembly.py` | `test_interaction_*`、`test_prompt_assembly.py` |
| DIGI/vLLM、ORPO、Skylark、OpenRouter 路由 | `model_adapter.py` | adapter unit coverage |
| 角色前綴、時間、字面換行、內部標籤、MEM 洩漏、meta 清理 | `postprocess.py` | `test_interaction_turn_matches_the_architecture_and_persists_outputs` |
| reset 僅清事件記憶與好感度 | `local_app.py` | `test_reset_matches_ai_server_by_clearing_memory_and_relationship_only` |
| 回合後事件記憶保存 | `interaction/service.py` 先使用結構化抽取；空結果時保存同回合的相容事件回退 | `test_interaction_persists_a_turn_memory_when_extraction_returns_nothing` |
| 已有逐字對話的事件記憶補建 | `memory_backfill.py` 只由登入者明確觸發，單一 chat 最多 80 則、每 8 則抽取，全部成功後才寫入 | `test_memory_backfill.py`、`test_backfill_builds_memories_only_for_the_saved_conversation` |

## 刻意的可開源化差異

| 原始行為 | DIJI 行為 | 原因 |
| --- | --- | --- |
| 固定硬編碼的模型越獄文字 | 已核准、可編輯、依模型選取的 `runtime/jailbreaks.json` | 使用者要求越獄可命名、可修改且不要重複硬寫。 |
| `request.memory.list` 可強制覆蓋記憶來源 | 只採用該 `chat_id` 的本機事件記憶；請求只控制注入模式 | 避免前端任意偽造或污染永久記憶。 |
| `/sessions` 回傳空 placeholder，`/session` 從摘要嘗試還原 metadata | `conversation_store` 保存完整逐字對話，提供可用的列出／讀回 API | 這是為了使用者要求的永久聊天記錄。 |
| debug 手動設定好感度 HTTP 路由與大量 stdout 日誌 | 不公開 debug 寫入路由；錯誤由 HTTP 回應與服務日誌處理 | 避免公開部署時任意改寫關係狀態或洩漏內容。 |
| 好感度一律隨角色設定啟動 | `enable_favorability` 可由使用者按對話開關，UI 預設關閉 | 使用者明確要求可切換；關閉時沒有隱性評分或 profile 寫入。 |
| 抽取器未回傳 JSON 時不新增事件 | 保存同回合的最小結構相容事件，並在對話右側可直接查看 | 避免成功對話無記憶，仍保留 `memory_store` 的 ai-server 事件格式。 |
| 角色圖片 prompt、資料集生成、命令列聊天與舊資料轉換 | 不遷移 | 使用者明確排除角色圖片；其餘為訓練／開發輔助工具，不屬於本機角色互動網站。 |

## 原始規則中的衝突及採用順序

原始 `RULES_COMMON` 一度要求訊息帶時間戳，但同一條 prompt 後段的 `<TIME_CONTEXT>`、`<ENDING_RULES>`、OOC 和輸出後處理又明確禁止／移除時間文字。DIJI 保留原始的最後有效行為：把時間當內部情境資訊，不在角色回答輸出日期或時間戳。

## 驗證要求

每次變更後至少執行：

```bash
python -m pytest -q tests
```

重新取得 Kali 連線後，先讀取遠端 `api_server/nsfw_llm_api_server_dev.py` 的 SHA-256；若與本文件基準不同，必須重新做逐段差異對照，不能把本文件當成遠端現況。

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
  -> relationship（符合設定時的狀態保存；判決器需沿用原始規則）
```

## 不可改變的行為

- 記憶注入模式使用 `MEM0_INJECT_MODE` 的 `system`、`user`、`none`；請求的 `inject_memory` 覆寫此設定。
- 常規記憶以 `<MEM>` 放入最近 20 筆；目前使用者訊息會以提取後的 `keywords` 值搜尋，另放入 `<RELEVANT_MEM>`。分類搜尋命中數只作 metadata，排序仍依時間新到舊。
- 模型路由順序為 DIGI/Joi 的 vLLM、ORPO 遠端 `/api/generate`、Skylark、其餘 OpenRouter 相容端點。未設定必要金鑰時必須在網路請求前失敗。
- 輸出清理先移除時間、處理文字換行與內部標籤，再正規化標點；不可將提示詞內部標籤輸出給使用者。
- 關係狀態只有五階：陌生、熟識、親近、親密、靈魂。分數門檻依序是 40、80、120、180；第一階可單憑分數進入第二階，其後必須同時出現對應關鍵事件。`relationship.py` 已保存這個狀態轉換；要啟用 LLM 判決器前，必須以原始 `favorability_judge.py` 驗證其 prompt 與錯誤回退規則。
- 越獄是 `PromptExperiment` 的資料，不是程式常數；只有明確 `is_nsfw` 的互動才會放入上下文。`/api/interactions` 會依所選模型解析同一筆已核准越獄，前端不得指定或覆寫此對應。

## 明確不遷移

角色圖片生成、ComfyUI、訓練資料集、使用者既有記憶檔與運行日誌都不進入 repository，也不作為預設執行路徑。

## API 邊界

`POST /api/prompt-preview` 僅檢查 prompt，不呼叫模型。`POST /api/characters/generate`、`POST /api/interactions`、`POST /api/memories/{chat_id}/extract` 是唯一可能發送模型請求的路由；它們都需要使用者自行配置 provider 金鑰。

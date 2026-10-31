# 記憶系統實測：2026-11-01

## 方法與結果

在已登入的 Edge 建立獨立測試對話，以虛構姓名、茶飲偏好、隨機暗號與書店約定測試；未讀取或修改其他對話內容。

1. 原抽取請求的 1000-token 預算被推理耗盡：`finish_reason=length`、正文長度 0、推理長度 1735。服務保存了回退事件，其 `keywords` 為空。
2. 相同抽取輸入停用推理後回傳正常 JSON：`finish_reason=stop`、正文長度 547、309 completion tokens。保留既有模型、提示、JSON 格式與 token 上限。
3. 修正部署後，Edge 的第二輪實際對話產生帶 `key_points` 與 `keywords` 的事件。右側與完整記憶頁皆能顯示，重新載入後仍在；記憶頁會保存並驗證帳號所屬的查看範圍。
4. 伺服器檢索：完整關鍵字命中 1 筆、人物分類命中 1 筆。prompt 組裝確認 `<MEM>` 與對應查詢的 `<RELEVANT_MEM>` 存在。
5. 另以實際模型執行一次 **零逐字歷史** 驗證：只從保存記憶組裝 prompt，沒有在問題重述茶名、暗號或書店，三項答案皆正確。這與 Edge 的對話歷史回放分開驗證，避免把歷史誤認成事件記憶。

## 修正

- 抽取請求加入 `reasoning.enabled=false`。OpenRouter 文件說明低輸出上限可能被推理耗盡，造成空正文；此處已以實際 A/B 回應確認。[Reasoning Tokens](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens)
- 記憶頁在 sessionStorage 僅保存帳號 ID、對話 ID 與角色名稱；重新載入時比對登入帳號，登出清除。記憶正文仍由伺服器授權 API 讀取。
- `tests/test_memory_reasoning.py` 透過 OpenAI 相容 HTTP adapter 重現空正文，修正前失敗、修正後通過。完整 pytest 為 84 項通過，服務健康檢查通過。

## 保留的限制

- 檢索沿用 ai-server 的字串包含比對，不是語意搜尋。假設 keyword 值為「甲、乙」，問題只有「甲」不會命中整個值；本次有觀察到此限制。近期記憶仍會依既有模式注入。
- 舊的回退事件不會自動重抽取；本次保留原事件以供比較，沒有刪除或改寫使用者既有記憶。
- 本次結果只證明所測情境，不保證每個模型供應商、所有問題與所有輸出都正確。

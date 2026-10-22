"""ai-server-compatible LLM event extraction, isolated behind an explicit adapter."""

from __future__ import annotations

import json
import os
import re
import traceback
from datetime import datetime, timedelta, timezone
from typing import Protocol

from openai import AsyncOpenAI

from .memory_store import MemoryRecord


TZ_TAIPEI = timezone(timedelta(hours=8))
EXTRACTION_MODEL = "deepseek/deepseek-v4.1-flash"


class CompletionClient(Protocol):
    async def create(self, **kwargs: object) -> str: ...


class OpenRouterExtractionClient:
    """The same OpenAI-compatible OpenRouter adapter used by ai-server."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY", "")
        self.client: AsyncOpenAI | None = None

    async def create(self, **kwargs: object) -> str:
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not configured")
        if self.client is None:
            self.client = AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=self.api_key)
        response = await self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""


class MemoryExtractor:
    """Extract one ai-server memory event from a conversation through a small interface."""

    def __init__(self, client: CompletionClient) -> None:
        self.client = client

    async def extract(self, conversation: str) -> list[MemoryRecord]:
        prompt = f"""請分析以下對話，提取重要資訊。重點關注：
1. 用戶和角色之間的重要互動
2. 情感表達和態度變化
3. 場景和環境的改變
4. 重要的約定或承諾
5. 角色的性格特徵展現

請以JSON格式輸出，包含以下欄位：
- timestamp: 時間戳記（YYYY-MM-DD HH:MM格式）
- type: 記憶類型（事實|偏好|事件|標記）
- summary: 單句摘要（不超過60字，不含人名以外敏感資訊）
- user_message: 用戶訊息
- key_points: 關鍵點列表（例如：情感表達、場景變化、重要約定等，不超過5個）
- character_response_summary: 角色回覆的簡短總結（50字以內）
- keywords: 關鍵字字典，包含分類的關鍵詞（例如：{{"物品": "手作飾品", "地點": "後山", "活動": "散步", "情緒": "開心"}}）
  可用的分類：物品、地點、活動、情緒、人物、時間、事件、其他

對話內容：
{conversation}"""
        try:
            content = await self.client.create(
                model=EXTRACTION_MODEL,
                temperature=0.3,
                max_tokens=1000,
                top_p=0.6,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if not match:
                return []
            event = json.loads(match.group(0))
            event["timestamp"] = datetime.now(TZ_TAIPEI).strftime("%Y-%m-%d %H:%M")
            if event.get("type") not in {"事實", "偏好", "事件", "標記"}:
                event["type"] = "event"
            event["summary"] = (event.get("summary") or event.get("character_response_summary") or event.get("user_message") or "對話記憶")[:60]
            if not isinstance(event.get("keywords"), dict):
                event["keywords"] = {}
            return [MemoryRecord.model_validate(event)]
        except Exception as error:
            return [MemoryRecord.model_validate({
                "timestamp": datetime.now(TZ_TAIPEI).strftime("%Y-%m-%d %H:%M"),
                "type": "標記",
                "summary": "錯誤：LLM提取事件失敗",
                "error": True,
                "error_message": f"LLM提取關鍵事件時出錯：{error}",
                "traceback": traceback.format_exc(),
            })]

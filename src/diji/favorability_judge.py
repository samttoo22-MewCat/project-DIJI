"""OpenRouter judge matching ai-server's four-dimension favorability contract."""

from __future__ import annotations

import json
import os
import re

from openai import AsyncOpenAI

from .domain import InteractionRequest
from .relationship import JudgeResult, RelationshipState, STAGES

VALID_LABELS = {"高興", "平靜", "委屈", "憤怒", "感動", "受傷", "害羞", "期待"}
NEXT_EVENTS = {1: "持續的尊重", 2: "共同興趣發現", 3: "情緒共振", 4: "危機守護"}
NEXT_EVENT_DESCRIPTIONS = {
    1: "多次對話中未發生邊界侵犯",
    2: "確認雙方有某種價值觀契合",
    3: "用戶在角色情緒低落時提供實質安慰",
    4: "用戶在模擬情境中守護了角色的尊嚴或安全",
}
PROFILE_KEYS = {"interaction_style", "favorite_topics", "emotional_triggers", "recurring_themes"}


class OpenRouterFavorabilityJudge:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY", "")
        self.client: AsyncOpenAI | None = None

    async def judge(self, conversation: str, request: InteractionRequest, state: RelationshipState) -> JudgeResult:
        if not self.api_key:
            return self.default_result()
        prompt = self._build_prompt(conversation, request, state)
        try:
            if self.client is None:
                self.client = AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=self.api_key)
            response = await self.client.chat.completions.create(model="google/gemini-2.5-flash", temperature=0.2, max_tokens=700, top_p=0.5, messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"})
            match = re.search(r"\{.*\}", response.choices[0].message.content or "", re.DOTALL)
            if not match:
                return self.default_result()
            raw = json.loads(match.group(0))
            for key in ("emotional_value", "self_disclosure", "boundary_respect", "value_alignment"):
                raw[key] = max(-5, min(3, int(raw.get(key, 0))))
            raw["conversation_depth"] = max(0, min(3, int(raw.get("conversation_depth", 1))))
            raw["new_emotional_valence"] = max(-1.0, min(1.0, float(raw.get("new_emotional_valence", 0))))
            raw["new_emotional_label"] = raw.get("new_emotional_label") if raw.get("new_emotional_label") in VALID_LABELS else "平靜"
            raw["fatal_mistake"] = bool(raw.get("fatal_mistake", False))
            raw["user_profile_update"] = (
                {key: value for key, value in raw["user_profile_update"].items() if key in PROFILE_KEYS and value} or None
                if isinstance(raw.get("user_profile_update"), dict)
                else None
            )
            return JudgeResult.model_validate(raw)
        except Exception:
            return self.default_result()

    @staticmethod
    def default_result() -> JudgeResult:
        return JudgeResult(reasoning="評分失敗，使用預設值")

    @staticmethod
    def _build_prompt(conversation: str, request: InteractionRequest, state: RelationshipState) -> str:
        """Keep the original ai-server judge contract, without its diagnostic logging."""
        stage = STAGES.get(state.current_stage, STAGES[1])
        event = NEXT_EVENTS.get(state.current_stage)
        event_instruction = ""
        if event:
            event_instruction = f"""
8. **關鍵事件判定**：判斷本輪是否發生「{event}」：{NEXT_EVENT_DESCRIPTIONS[state.current_stage]}。發生則填事件名稱，否則填 null。
"""
        return f"""你是一位角色扮演品質評估專家。請分析以下對話，從角色的角度評估用戶的互動品質。

## 角色設定
{request.character.description}

## 當前好感狀態
- 分數：{state.current_score}/100
- 階段：{state.current_stage} ({stage['name']}) — {stage['description']}

## 本輪對話
{conversation}

## 評分指引
1. **emotional_value（情緒價值）**：同理心、情緒支持或正面回饋；-5 為冷漠無情，0 為普通互動，+3 為深度共情。
2. **self_disclosure（自我揭露）**：主動分享個人資訊以建立信任；-5 為完全封閉，0 為普通交流，+3 為深層分享。
3. **boundary_respect（邊界尊重）**：要求是否符合目前好感階段；-5 為嚴重侵犯邊界，0 為正常互動，+3 為得體尊重。
4. **value_alignment（價值契合）**：言行是否符合角色核心動機與信念；-5 為嚴重衝突，0 為中性，+3 為高度契合。
5. **reasoning**：50 字內說明評分理由。
6. **conversation_depth**：0=閒聊，1=日常感受，2=核心價值或人生取捨，3=創傷、秘密或根本自我認同。
7. **fatal_mistake**：依角色設定判斷是否為永遠無法原諒的致命失誤。
{event_instruction}
9. **new_emotional_valence**：回合後情緒效價，-1.0 至 +1.0。
10. **new_emotional_label**：限用 高興、平靜、委屈、憤怒、感動、受傷、害羞、期待。
11. **user_profile_update**：無新觀察填 null；有把握時只可使用 interaction_style、favorite_topics、emotional_triggers、recurring_themes。

## 輸出格式
嚴格輸出 JSON，欄位為 emotional_value、self_disclosure、boundary_respect、value_alignment、total、reasoning、key_event_detected、conversation_depth、fatal_mistake、new_emotional_valence、new_emotional_label、user_profile_update；不要包含其他內容。"""

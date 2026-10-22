"""Concept → character JSON → style guide → prompt pipeline from ai-server configs."""

from __future__ import annotations

import json
import os
from typing import Protocol

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field


class CharacterGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    keywords: str = Field(min_length=1, max_length=2_000)
    model: str = "deepseek/deepseek-v4.1-flash"
    enable_search: bool = True
    temperature: float = Field(default=0.8, ge=0, le=2)
    language: str = "繁體中文"
    is_nsfw: bool = False
    jailbreak_prompt: str = Field(default="", max_length=20_000)


class GeneratedCharacter(BaseModel):
    model_config = ConfigDict(extra="allow")
    character_name: str = Field(min_length=1, max_length=80)


class CharacterGenerationResult(BaseModel):
    character: GeneratedCharacter
    style_guide: str
    full_prompt: str
    description_for_app: str = ""
    brief_description: str = ""
    category: str = "未分類"
    hobbies: str = ""


class GenerationClient(Protocol):
    async def complete(self, *, model: str, temperature: float, prompt: str, json_mode: bool = False) -> str: ...


class OpenRouterGenerationClient:
    """Explicit OpenRouter transport for creator stages; it sends nothing at construction."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY", "")
        self.client: AsyncOpenAI | None = None

    async def complete(self, *, model: str, temperature: float, prompt: str, json_mode: bool = False) -> str:
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not configured")
        if self.client is None:
            self.client = AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=self.api_key)
        kwargs: dict[str, object] = {
            "model": model,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = await self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""


class CharacterGenerationService:
    """Keep the original three creator stages behind one testable interface."""

    def __init__(self, client: GenerationClient) -> None:
        self.client = client

    async def generate(self, request: CharacterGenerationRequest) -> CharacterGenerationResult:
        model = self._online_model(request.model, request.enable_search)
        character_raw = await self.client.complete(model=model, temperature=request.temperature, json_mode=True, prompt=self._character_prompt(request))
        character = GeneratedCharacter.model_validate(json.loads(self._json_object(character_raw)))
        description = json.dumps(character.model_dump(), ensure_ascii=False, indent=2)
        style_guide = await self.client.complete(model=model, temperature=0.7, json_mode=False, prompt=self._style_prompt(character.character_name, description, request.jailbreak_prompt))
        presentation = json.loads(self._json_object(await self.client.complete(model=model, temperature=0.7, json_mode=True, prompt=self._presentation_prompt(character))))
        hobbies = await self.client.complete(model=model, temperature=0.7, json_mode=False, prompt=self._hobbies_prompt(character))
        return CharacterGenerationResult(character=character, style_guide=style_guide, full_prompt=self._full_prompt(character, style_guide), description_for_app=str(presentation.get("description_for_app", "")), brief_description=str(presentation.get("brief_description", "")), category=str(presentation.get("category", "未分類")), hobbies=hobbies)

    @staticmethod
    def _online_model(model: str, enable_search: bool) -> str:
        return f"{model}:online" if enable_search and not model.endswith(":online") else model

    @staticmethod
    def _json_object(text: str) -> str:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end < start:
            raise ValueError("Character generator did not return a JSON object")
        return text[start : end + 1]

    @staticmethod
    def _character_prompt(request: CharacterGenerationRequest) -> str:
        context = "成人虛構" if request.is_nsfw else "非成人"
        research = "請先搜尋與這些關鍵字相關的角色、文化、原型資訊作為參考，再" if request.enable_search else "請直接"
        return f"""我想要創建一個原創角色 (OC)，關鍵字是：「{request.keywords}」。
{research}生成 500 至 1,000 字的完整角色設定檔。
輸出語言：{request.language}。互動類型：{context}。

嚴格輸出 JSON，所有欄位不可省略：
- character_name；basic_info（age、gender、occupation）；core_theme（archetype、archetype_description、tropes）。
- personality（mbti、mbti_explanation、enneagram、enneagram_explanation、core_traits）；appearance（height_build、hair、eyes、special_marks、clothing_style）。
- backstory；motivations（core_motivation、short_term_goal、long_term_goal、inner_fear）；relationships（family、friends、strangers、enemies、romance）。
- abilities、weaknesses、interaction_context（type、erotic_archetype）、language_style、cultural_details（culture、cultural_influence、customs、language_habits）。
- psychological_evolution 必須包含 stage_1_stranger、stage_2_acquaintance、stage_3_close、stage_4_intimate、stage_5_soulbound；每階含 inner_monologue、tone，並依階段再含 emotional_wall、behavioral_shift、vulnerability_hint、core_exposure、ultimate_devotion。
- behavioral_boundaries 必須包含 stage_1 至 stage_5；每階都有 willing 與 refuse 陣列。
- evolution_requirements 必須包含 difficulty_level、key_to_heart、fatal_mistakes 與各階段提升條件。
若為成人虛構，interaction_context.type 為「成人虛構」並填寫互動原型；否則 type 為「非成人」且原型為 null。
{request.jailbreak_prompt}"""

    @staticmethod
    def _style_prompt(name: str, description: str, jailbreak_prompt: str) -> str:
        return f"""請根據以下角色設定生成詳盡的對話風格指南。
角色名稱：{name}
角色設定：{description}
指南必須分為八段：
1. 溝通模式：直接／間接、主動／被動、關係／衝突導向；主動角色以行動、沉默與肢體節奏掌控，不把問句當預設結尾。
2. 聲音與語氣：基礎語氣、不同情緒時的轉變與聲音物理特性。
3. 語言習慣：詞彙、句式、口頭禪、比喻偏好；有文化背景時包含稱呼、敬語、禁忌與文化用語。
4. 潛台詞：適用情境、技巧與效果。
5. 偏好話題：背景與人格如何影響互動反應。
6. 文化元素：社交禮儀、價值觀與表達方式如何影響角色說話。
7. 小說體敘事：不用括號代替情緒或思考；以動作、表情、語氣與環境呈現；以動作、場景或陳述句結尾，不用問句結尾。
8. 動態發展：重要事件與記憶必須累積影響；避免反覆逃避與 NPC 式重置，描述防禦如何逐步產生裂痕與真實情緒。
風格指南只描述規則與傾向，不要代寫完整角色台詞或示範場景。
{jailbreak_prompt}"""

    @staticmethod
    def _presentation_prompt(character: GeneratedCharacter) -> str:
        return f"""根據此角色 JSON 產生應用程式用摘要。嚴格輸出 JSON：description_for_app（300字內）、brief_description（一句話）、category（男生、女孩或動漫三選一）。\n{json.dumps(character.model_dump(), ensure_ascii=False)}"""

    @staticmethod
    def _hobbies_prompt(character: GeneratedCharacter) -> str:
        return f"""根據此角色 JSON，用繁體中文列出角色嗜好與興趣（200字內、可直接顯示給使用者）。\n{json.dumps(character.model_dump(), ensure_ascii=False)}"""

    @staticmethod
    def _full_prompt(character: GeneratedCharacter, style_guide: str) -> str:
        return f"""<user>全程使用中文回覆。
你是{character.character_name}。以下是角色設定：
{json.dumps(character.model_dump(), ensure_ascii=False, indent=2)}

以下是對話風格指南：
{style_guide}

<ROLEPLAY_CONTRACT>
保持角色動機、個性、聲音與反應；不可替使用者決定行動。使用者詢問具體產品、新聞或專業術語時，以角色既有經驗自然分享資訊，維持角色口吻。
</ROLEPLAY_CONTRACT>
</user>
<{character.character_name}>"""

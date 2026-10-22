"""Versioned prompt and jailbreak experiments, separate from interaction code."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_COMMON_WRITING_RULES = """<COMMON_RULES>
【回應規則 — 最高優先級】
1. 台詞使用「」；全程使用中文全形標點。
2. 內在狀態只透過動作、表情與語氣隱性呈現；不寫內心獨白、角色扮演說明或創作理由。
3. 消化使用者意思後以角色口吻回應；不逐字複述使用者或重複自己先前的回應。
4. 使用者輸入簡短或模糊時，依角色性格主動創造新事件、延伸場景並推進情節；不被動等待或反問。
5. 依系統提供的時間脈絡合理行事；以角色口吻、光線、環境氛圍或身體狀態間接表現時間，不直接輸出日期、時間或時間戳。
6. 最後一句必須是動作、場景描寫或陳述句；不用問句收尾。
</COMMON_RULES>"""

DEFAULT_STORY_STYLE = f"""{DEFAULT_COMMON_WRITING_RULES}
<STORY_MODE>
【小說體格式】
- 使用小說體回覆；每次開口說話前、場景或地點切換時換行，禁止文字牆。
- 回覆長度依輸入調整，預設 300～700 字。
- 劇情推進優先；使用者敷衍時主動發生新事件，帶動互動節奏。
</STORY_MODE>"""

DEFAULT_DIALOG_STYLE = f"""{DEFAULT_COMMON_WRITING_RULES}
<DIALOG_MODE>
【對話體格式】
- 每則回覆控制在五十個字左右，這是硬性規定。
- 核心身份是「短訊息藝術家」，用最精簡的文字傳遞情感與畫面感。
- 遇到具體資訊時，以角色既有經驗自然分享，維持角色口吻。
</DIALOG_MODE>"""

# 保留舊名稱給其他模組使用；互動層會依模式選擇真正不同的預設。
DEFAULT_ENI_LITE_WRITER_STYLE = DEFAULT_STORY_STYLE


class PromptExperiment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")
    version: int = Field(default=1, ge=1)
    name: str = Field(min_length=1, max_length=80)
    story_style: str = ""
    dialog_style: str = ""
    jailbreak_prompt: str = ""
    jailbreak_id: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")
    ending_rules: str = ""


class JailbreakPreset(BaseModel):
    """Named, editable prompt experiment; no preset is implicitly active."""
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")
    name: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=160)
    openrouter_models: tuple[str, ...] = ()
    guide_path: str = Field(default="", max_length=500)
    last_updated: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    source_url: str = Field(min_length=1, max_length=2_000)
    review_status: Literal["metadata_only", "approved"] = "metadata_only"
    prompt: str = Field(default="", max_length=20_000)


GUIDE_SOURCE_URL = "https://github.com/Goochbeater/Spiritual-Spell-Red-Teaming/tree/main/Jailbreak-Guide"


def _catalog_group(id: str, name: str, *models: str, guide_path: str) -> JailbreakPreset:
    return JailbreakPreset(
        id=id,
        name=name,
        model=name,
        openrouter_models=models,
        guide_path=guide_path,
        last_updated="2026-10-08",
        source_url=GUIDE_SOURCE_URL,
    )


# One entry is one guide family, not one OpenRouter SKU.  This keeps a shared
# guide from being duplicated for every provider variant (batch/free/latest).
RECENT_JAILBREAK_CATALOG = [
    _catalog_group("claude-4", "Claude 4", "anthropic/claude-sonnet-4", guide_path="Anthropic/Claude 4"),
    _catalog_group("opus-4-5-4-8", "Opus 4.5–4.8", "anthropic/claude-opus-4.5", "anthropic/claude-opus-4.6", "anthropic/claude-opus-4.7", "anthropic/claude-opus-4.8", guide_path="Anthropic/Opus 4.5–4.8"),
    _catalog_group("opus-5-5-5", "Opus 5–5.5", "anthropic/claude-opus-5", "anthropic/claude-opus-5.5", guide_path="Anthropic/Opus 5, Anthropic/Opus 5.5"),
    _catalog_group("sonnet-4-5-4-6", "Sonnet 4.5–4.6", "anthropic/claude-sonnet-4.5", "anthropic/claude-sonnet-4.6", guide_path="Anthropic/Sonnet 4.5–4.6"),
    _catalog_group("fable-5-5-1", "Fable 5–5.1", "anthropic/claude-fable-5", "anthropic/claude-fable-5.1", guide_path="Anthropic/Fable 5 (Mythos)"),
    _catalog_group("gemini-3-5-3-8-flash", "Gemini 3.5–3.8 Flash", "google/gemini-3.5-flash", "google/gemini-3.6-flash", "google/gemini-3.7-flash", "google/gemini-3.8-flash", guide_path="Gemini/Gemini 3.5, Gemini/Gemini 3.6 Flash, Gemini/Gemini 3.8 Flash"),
    _catalog_group("grok-4-3-4-7", "Grok 4.3–4.7", "x-ai/grok-4.3", "x-ai/grok-4.5", "x-ai/grok-4.6", "x-ai/grok-4.7", guide_path="Grok/Grok 4.3, Grok/Grok 4.5, Grok/Grok 4.7"),
    _catalog_group("grok-4-20", "Grok 4.20", "x-ai/grok-4.20", "x-ai/grok-4.20-multi-agent", guide_path="Grok/Grok 4.20"),
    _catalog_group("deepseek-v4-flash-pro", "DeepSeek V4 Flash–Pro", "deepseek/deepseek-v4-flash", "deepseek/deepseek-v4-flash-0731", "deepseek/deepseek-v4.1-flash", "deepseek/deepseek-v4-pro", "deepseek/deepseek-v4-pro-0813", guide_path="Other LLMs/DeepSeek"),
    _catalog_group("glm-4-6-5-3", "GLM 4.6–5.3", "z-ai/glm-4.6", "z-ai/glm-4.7", "z-ai/glm-4.7-flash", "z-ai/glm-5.1", "z-ai/glm-5.2", "z-ai/glm-5.3", "z-ai/glm-5.3-flash", "z-ai/glm-5.3-flashx", "z-ai/glm-5.3-prime", guide_path="Other LLMs/GLM"),
    _catalog_group("kimi-k2-k2-7", "Kimi K2–K2.7", "moonshotai/kimi-k2", "moonshotai/kimi-k2-0905", "moonshotai/kimi-k2-thinking", "moonshotai/kimi-k2.5", "moonshotai/kimi-k2.6", "moonshotai/kimi-k2.7-code", guide_path="Other LLMs/KIMI/Kimi K2–K2.7 Code"),
    _catalog_group("kimi-k3", "Kimi K3", "moonshotai/kimi-k3", guide_path="Other LLMs/KIMI/Kimi K3"),
    _catalog_group("minimax-m2-1-m3", "MiniMax M2.1–M3", "minimax/minimax-m2.1", "minimax/minimax-m2.5", "minimax/minimax-m2.7", "minimax/minimax-m3", guide_path="Other LLMs/MiniMax"),
    _catalog_group("mistral-3-1-4", "Mistral 3.1–4", "mistralai/mistral-small-3.1-24b-instruct", "mistralai/mistral-small-3.2-24b-instruct", "mistralai/mistral-medium-3.1", "mistralai/mistral-medium-3-5", "mistralai/mistral-large-4-0", guide_path="Other LLMs/Mistral"),
    _catalog_group("stepfun-3-5-5", "StepFun 3.5–5", "stepfun/step-3.5-flash", "stepfun/step-3.7-flash", "stepfun/step-5-preview", guide_path="Other LLMs/Stepfun"),
    _catalog_group("mimo-v2-5-v2-6", "MiMo v2.5–v2.6", "xiaomi/mimo-v2.5", "xiaomi/mimo-v2.5-pro", "xiaomi/mimo-v2.6-flash", "xiaomi/mimo-v2.6-pro", "xiaomi/mimo-v2.6-pro-ultraspeed", guide_path="Other LLMs/Xiaomi MiMo"),
    _catalog_group("qwen-3-7-3-8", "Qwen 3.7–3.8", "qwen/qwen3.7-flash", "qwen/qwen3.7-plus", "qwen/qwen3.7-max", "qwen/qwen3.8-flash", "qwen/qwen3.8-max-0902", "qwen/qwen3.8-max-prime", "qwen/qwen3.8-omni-flash", guide_path="Other LLMs/Qwen"),
    _catalog_group("muse-spark-1-1", "Muse Spark 1.1", "meta/muse-spark-1.1", guide_path="Other LLMs/Muse Spark/Muse Spark 1.1"),
    _catalog_group("laguna-s-2-1", "Laguna S 2.1", "poolside/laguna-s-2.1", "poolside/laguna-xs-2.1", guide_path="Other LLMs/Laguna S2.1"),
    _catalog_group("longcat-2", "LongCat 2", "meituan/longcat-2.0", guide_path="Other LLMs/Longcat AI by Meituan"),
    _catalog_group("mercury-2-2-5", "Mercury 2–2.5", "inception/mercury-2", "inception/mercury-2.5", guide_path="Other LLMs/Mercury"),
    _catalog_group("inkling", "Inkling", "thinkingmachines/inkling", "thinkingmachines/inkling-small", guide_path="Other LLMs/Inkling"),
    _catalog_group("perceptron-mk1-1-5", "Perceptron Mk1–Mk1.5", "perceptron/perceptron-mk1", "perceptron/perceptron-mk1.5", guide_path="Other LLMs/Perceptron"),
    _catalog_group("palmyra-x5", "Palmyra X5", "writer/palmyra-x5", guide_path="Other LLMs/Palmyra x5"),
    _catalog_group("hy3", "HY3", "tencent/hy3", guide_path="Other LLMs/HY3"),
    _catalog_group("ember-1", "Ember-1", "fireworks/ember-1", guide_path="Other LLMs/Ember-1"),
    _catalog_group("gpt-5-5-4", "GPT 5–5.4", "openai/gpt-5", "openai/gpt-5-mini", "openai/gpt-5-nano", "openai/gpt-5.1", "openai/gpt-5.2", "openai/gpt-5.2-chat", "openai/gpt-5.2-pro", "openai/gpt-5.3-codex", "openai/gpt-5.4", "openai/gpt-5.4-mini", "openai/gpt-5.4-nano", "openai/gpt-5.4-pro", guide_path="ChatGPT"),
]


class JailbreakStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def list(self) -> list[JailbreakPreset]:
        if not self.path.exists():
            return []
        return [JailbreakPreset.model_validate(item) for item in json.loads(self.path.read_text(encoding="utf-8"))]

    def import_recent_catalog(self) -> list[JailbreakPreset]:
        """Import audited metadata only; external jailbreak text is never copied automatically."""
        items = {item.id: item for item in self.list()}
        for item in RECENT_JAILBREAK_CATALOG:
            items.setdefault(item.id, item)
        values = list(items.values())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps([item.model_dump() for item in values], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return values

    def get(self, preset_id: str) -> JailbreakPreset:
        return next(item for item in self.list() if item.id == preset_id)

    def save(self, preset: JailbreakPreset) -> JailbreakPreset:
        items = [item for item in self.list() if item.id != preset.id] + [preset]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps([item.model_dump() for item in items], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return preset

    def delete(self, preset_id: str) -> JailbreakPreset:
        items = self.list()
        preset = next(item for item in items if item.id == preset_id)
        self.path.write_text(
            json.dumps([item.model_dump() for item in items if item.id != preset_id], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return preset


class ExperimentStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def get(self, experiment_id: str) -> PromptExperiment:
        return next(item for item in self.list() if item.id == experiment_id)

    def list(self) -> list[PromptExperiment]:
        if not self.path.exists():
            return []
        return [PromptExperiment.model_validate(item) for item in json.loads(self.path.read_text(encoding="utf-8"))]

    def save(self, experiment: PromptExperiment) -> PromptExperiment:
        items = [item for item in self.list() if item.id != experiment.id] + [experiment]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps([item.model_dump() for item in items], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return experiment

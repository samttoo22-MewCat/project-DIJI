"""Portable interaction domain models, based on ai-server's request contract."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class GenerationParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_tokens: int = Field(default=4000, ge=1, le=32_000)
    temperature: float = Field(default=0.75, ge=0, le=2)
    top_p: float = Field(default=0.6, gt=0, le=1)


class ModelConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = Field(min_length=1, max_length=256)
    url: str | None = Field(default=None, max_length=2_000)
    parameters: GenerationParameters = Field(default_factory=GenerationParameters)


class CategoryTag(BaseModel):
    id: int = 0
    name: str = "未分類"
    is_nsfw: bool = False


class SampleDialog(BaseModel):
    sender_type: Literal[1, 2]
    text: str = Field(min_length=1, max_length=8_000)


class InteractionCharacter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")
    name: str = Field(min_length=1, max_length=80)
    brief_description: str = ""
    description: str = Field(min_length=1, max_length=20_000)
    greeting_message: str = ""
    place_description: str = ""
    category: CategoryTag = Field(default_factory=CategoryTag)
    sample_dialog: list[SampleDialog] = Field(default_factory=list, max_length=100)
    psychological_evolution: dict[str, Any] | None = None
    behavioral_boundaries: dict[str, Any] | None = None
    evolution_requirements: dict[str, Any] | None = None


class UserPersona(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    chat_mode: Literal["story", "dialog"] = "story"
    sex: str = ""
    age: str = ""
    description: str = ""


class InteractionUser(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")
    persona: UserPersona


class InteractionMessage(BaseModel):
    id: int = 0
    sender_id: str
    sender_type: Literal[1, 2] = 1
    msg_type: int = 0
    text: str = Field(min_length=1, max_length=16_000)
    attachments: list[Any] = Field(default_factory=list)


class HistoryEntry(BaseModel):
    sender_type: Literal[1, 2]
    text: str = Field(min_length=1, max_length=16_000)
    timestamp: int | None = Field(default=None, ge=0)


class InteractionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chat_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")
    llm: ModelConfiguration
    character: InteractionCharacter
    user: InteractionUser
    message: InteractionMessage
    history: list[HistoryEntry] = Field(default_factory=list, max_length=500)
    reset: bool = False
    style_prompt: str | None = Field(default=None, max_length=20_000)
    experiment_id: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")
    is_nsfw: bool = False
    enable_favorability: bool = True
    inject_memory: bool | None = None


class InteractionResponse(BaseModel):
    chat_id: str
    character_id: str
    text: str
    messages: list[dict[str, str]]
    memory_saved: bool
    relationship_updated: bool

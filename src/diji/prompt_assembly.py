"""Inspect and assemble DIJI interaction context without calling a model."""

from __future__ import annotations

import os
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .local_catalog import CharacterSpec, FlowSpec
from .memory_store import MemoryRecord


class ConversationTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8_000)


class PromptPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    character_id: str
    flow_id: str
    chat_id: str = Field(default="preview", pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    inject_memory: bool | None = None
    scene: str = Field(default="", max_length=2_000)
    history: list[ConversationTurn] = Field(default_factory=list, max_length=100)


class PromptLayer(BaseModel):
    key: Literal["character", "template", "scene", "history", "memory"]
    title: str
    content: str


class PromptBundle(BaseModel):
    character_id: str
    flow_id: str
    layers: list[PromptLayer]
    rendered_text: str
    memory_injection_mode: Literal["system", "user", "none"]


TEMPLATE_TEXT = {
    "immersive": "以角色設定為準，維持敘事節奏與角色觀點。",
    "baseline": "以清楚、直接的方式回應，不加入額外的角色或場景指示。",
    "scene": "維持當前場景的時間、空間與角色動作線。",
}


def format_mem0_block(memories: list[MemoryRecord], max_chars: int = 1_200, count: int = 20) -> str:
    """Match ai-server's compact <MEM> formatting for model injection."""
    lines = []
    for memory in memories[-count:]:
        summary = " ".join(memory.summary.split())
        character_response = " ".join((memory.character_response_summary or "").split())
        if summary:
            line = f"- [{memory.timestamp}] ({memory.type}) {summary}"
            if character_response:
                line += f" | 回覆總結: {character_response}"
            if memory.keywords:
                line += " | 關鍵字: " + ", ".join(f"{key}: {value}" for key, value in memory.keywords.items())
            lines.append(line)
    return ("<MEM>\n" + "\n".join(lines) + "\n</MEM>")[:max_chars] if lines else ""


def format_relevant_memories(memories: list[MemoryRecord], max_chars: int = 600) -> str:
    """Render the separate relevant-keyword context block used by ai-server."""
    lines = []
    for memory in memories:
        if not memory.summary:
            continue
        line = f"- [{memory.timestamp}] ({memory.type}) {' '.join(memory.summary.split())}"
        if memory.character_response_summary:
            line += f" | 回覆總結: {' '.join(memory.character_response_summary.split())}"
        if memory.keywords:
            line += " | 關鍵字: " + ", ".join(f"{key}: {value}" for key, value in memory.keywords.items())
        lines.append(line)
    return ("<RELEVANT_MEM>\n" + "\n".join(lines) + "\n</RELEVANT_MEM>")[:max_chars] if lines else ""


def resolve_memory_injection_mode(inject_memory: bool | None) -> Literal["system", "user", "none"]:
    """Mirror ai-server: request bool overrides MEM0_INJECT_MODE."""
    if inject_memory is not None:
        return "system" if inject_memory else "none"
    mode = os.getenv("MEM0_INJECT_MODE", "system")
    return mode if mode in {"system", "user", "none"} else "system"


def assemble_prompt(
    character: CharacterSpec, flow: FlowSpec, request: PromptPreviewRequest, memories: list[MemoryRecord]
) -> PromptBundle:
    """Return every context layer in the same order a future model adapter will use."""

    injection_mode = resolve_memory_injection_mode(request.inject_memory)
    memory_block = format_mem0_block(memories) if injection_mode != "none" else ""
    layer_content = {
        "character": PromptLayer(
            key="character",
            title="角色設定",
            content=(
                f"名稱：{character.name}\n"
                f"定位：{character.premise}\n"
                f"說話方式：{character.voice}\n"
                f"關係起點：{character.relationship_start}"
                + (f"\n完整設定：\n{json.dumps(character.profile, ensure_ascii=False, indent=2)}" if character.profile else "")
                + (f"\n風格指南：\n{character.style_guide}" if character.style_guide else "")
            ),
        ),
        "template": PromptLayer(
            key="template",
            title="提示模板",
            content=TEMPLATE_TEXT[flow.template],
        ),
        "scene": PromptLayer(
            key="scene",
            title="場景",
            content=request.scene or "未指定場景。",
        ),
        "history": PromptLayer(
            key="history",
            title="對話歷史",
            content=(
                "\n".join(f"{turn.role}: {turn.content}" for turn in request.history)
                or "尚無歷史訊息。"
            ),
        ),
        "memory": PromptLayer(
            key="memory",
            title="長期記憶",
            content=memory_block or ("記憶注入已停用。" if injection_mode == "none" else "尚無可注入的記憶。"),
        ),
    }
    order = list(flow.layers)
    if "scene" not in order:
        order.insert(order.index("template") + 1, "scene")
    layers = [layer_content[key] for key in order]
    rendered_text = "\n\n".join(f"[{layer.title}]\n{layer.content}" for layer in layers)
    return PromptBundle(
        character_id=character.id,
        flow_id=flow.id,
        layers=layers,
        rendered_text=rendered_text,
        memory_injection_mode=injection_mode,
    )

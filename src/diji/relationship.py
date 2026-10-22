"""Favorability state and stage transitions preserved from ai-server."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


STAGES = {
    1: {"name": "陌生", "range": (0, 39), "description": "戒備防禦，維持基本禮儀以掩飾不安"},
    2: {"name": "熟識", "range": (40, 79), "description": "放鬆觀察，認可對方為對話夥伴"},
    3: {"name": "親近", "range": (80, 119), "description": "情感投射，產生情感連結"},
    4: {"name": "親密", "range": (120, 179), "description": "脆弱揭露，撤除心理防禦"},
    5: {"name": "靈魂", "range": (180, 9999), "description": "完全依附，價值契合與用戶融合"},
}
THRESHOLDS = {"1_to_2": 40, "2_to_3": 80, "3_to_4": 120, "4_to_5": 180}
KEY_EVENTS = {"2_to_3": "共同興趣發現", "3_to_4": "情緒共振", "4_to_5": "危機守護"}


class RelationshipState(BaseModel):
    model_config = ConfigDict(extra="allow")

    current_score: int = Field(default=0, ge=0)
    current_stage: int = Field(default=1, ge=1, le=5)
    stage_name: str = "陌生"
    emotional_valence: float = Field(default=0.0, ge=-1, le=1)
    emotional_label: str = "平靜"
    last_updated: str | None = None
    history: list[dict] = Field(default_factory=list)


class JudgeResult(BaseModel):
    emotional_value: int = Field(default=0, ge=-5, le=3)
    self_disclosure: int = Field(default=0, ge=-5, le=3)
    boundary_respect: int = Field(default=0, ge=-5, le=3)
    value_alignment: int = Field(default=0, ge=-5, le=3)
    key_event_detected: str | None = None
    new_emotional_valence: float = Field(default=0, ge=-1, le=1)
    new_emotional_label: str = "平靜"
    reasoning: str = "評分完成"
    conversation_depth: int = Field(default=1, ge=0, le=3)
    fatal_mistake: bool = False
    user_profile_update: dict | None = None

    @property
    def total(self) -> int:
        return self.emotional_value + self.self_disclosure + self.boundary_respect + self.value_alignment


class RelationshipStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def get(self, chat_id: str) -> RelationshipState:
        path = self._path(chat_id)
        if not path.exists():
            return RelationshipState()
        return RelationshipState.model_validate_json(path.read_text(encoding="utf-8"))

    def apply(self, chat_id: str, result: JudgeResult) -> RelationshipState:
        state = self.get(chat_id)
        multipliers = {0: 0.5, 1: 1.0, 2: 1.5, 3: 2.0}
        adjusted_total = round(result.total * multipliers[result.conversation_depth]) - (8 if result.fatal_mistake else 0)
        new_score = max(0, min(100, state.current_score + adjusted_total))
        if self._should_upgrade(state.current_stage, new_score, result.key_event_detected):
            stage = state.current_stage + 1
        else:
            stage = state.current_stage
        updated = state.model_copy(update={
            "current_score": new_score,
            "current_stage": stage,
            "stage_name": STAGES[stage]["name"],
            "emotional_valence": result.new_emotional_valence,
            "emotional_label": result.new_emotional_label,
            "last_updated": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M"),
            "history": state.history + [{"total": result.total, "adjusted_total": adjusted_total, "conversation_depth": result.conversation_depth, "fatal_mistake": result.fatal_mistake, "reasoning": result.reasoning, "score_before": state.current_score, "score_after": new_score, "stage_before": state.current_stage, "stage_after": stage, "key_event_detected": result.key_event_detected}],
        })
        self._save(chat_id, updated)
        return updated

    def ensure_character_config(self, chat_id: str, character) -> RelationshipState:
        """Persist the first complete character evolution config like ai-server does."""
        state = self.get(chat_id)
        existing = (state.model_extra or {}).get("character_config")
        if existing or not character.psychological_evolution:
            return state
        configured = state.model_copy(update={
            "character_config": {
                "psychological_evolution": character.psychological_evolution,
                "behavioral_boundaries": character.behavioral_boundaries or {},
                "evolution_requirements": character.evolution_requirements or {},
                "character_name": character.name,
            }
        })
        self._save(chat_id, configured)
        return configured

    def delete(self, chat_id: str) -> None:
        path = self._path(chat_id)
        if path.exists():
            path.unlink()

    def _save(self, chat_id: str, state: RelationshipState) -> None:
        path = self._path(chat_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.parent.chmod(0o700)
        path.write_text(state.model_dump_json(indent=2) + "\n", encoding="utf-8")
        path.chmod(0o600)

    @staticmethod
    def _should_upgrade(current_stage: int, new_score: int, key_event: str | None) -> bool:
        if current_stage >= 5 or new_score < THRESHOLDS[f"{current_stage}_to_{current_stage + 1}"]:
            return False
        return current_stage == 1 or key_event == KEY_EVENTS.get(f"{current_stage}_to_{current_stage + 1}")

    def _path(self, chat_id: str) -> Path:
        if not chat_id or any(value in chat_id for value in ("/", "\\", "..")):
            raise ValueError("Invalid chat id")
        return self.directory / f"{chat_id}.json"

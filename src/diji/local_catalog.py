"""Local-first character and flow catalog for the DIJI workbench."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal
import json

from pydantic import BaseModel, ConfigDict, Field


class CharacterSpec(BaseModel):
    """A versioned, portable role-play character definition."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")
    version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=80)
    premise: str = Field(min_length=1, max_length=2_000)
    voice: str = Field(min_length=1, max_length=2_000)
    relationship_start: Literal["new", "familiar", "opposed"] = "new"
    profile: dict[str, Any] = Field(default_factory=dict)
    style_guide: str = Field(default="", max_length=30_000)
    full_prompt: str = Field(default="", max_length=50_000)
    source: dict[str, str] = Field(default_factory=dict)


class FlowSpec(BaseModel):
    """A named, versioned composition order for an interaction."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")
    version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=80)
    template: Literal["immersive", "baseline", "scene"] = "immersive"
    layers: list[Literal["character", "template", "scene", "history", "memory"]] = Field(
        default_factory=lambda: ["character", "template", "scene", "history", "memory"]
    )


class CatalogSnapshot(BaseModel):
    characters: list[CharacterSpec]
    flows: list[FlowSpec]


DEFAULT_CATALOG = CatalogSnapshot(
    characters=[
        CharacterSpec(
            id="yelan",
            name="夜蘭",
            premise="沉著而敏銳的情報員，習慣把真心藏在精準的觀察之後。",
            voice="低聲、簡短、帶有未說盡的暗示；不急著安慰，先觀察。",
        ),
        CharacterSpec(
            id="shenzhou",
            name="沈舟",
            premise="寡言的小說家，在雨夜裡總比平常更願意說真話。",
            voice="克制、平穩，偶爾用一個細節代替直接回答。",
            relationship_start="familiar",
        ),
    ],
    flows=[FlowSpec(id="immersive", name="沉浸式對話")],
)


class LocalCatalog:
    """Hide JSON persistence behind a small list/get/save interface."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def snapshot(self) -> CatalogSnapshot:
        if not self.path.exists():
            return DEFAULT_CATALOG.model_copy(deep=True)
        return CatalogSnapshot.model_validate_json(self.path.read_text(encoding="utf-8"))

    def character(self, character_id: str) -> CharacterSpec:
        return next(item for item in self.snapshot().characters if item.id == character_id)

    def flow(self, flow_id: str) -> FlowSpec:
        return next(item for item in self.snapshot().flows if item.id == flow_id)

    def save_character(self, character: CharacterSpec) -> CharacterSpec:
        snapshot = self.snapshot()
        snapshot.characters = self._replace(snapshot.characters, character)
        self._write(snapshot)
        return character

    def save_flow(self, flow: FlowSpec) -> FlowSpec:
        snapshot = self.snapshot()
        snapshot.flows = self._replace(snapshot.flows, flow)
        self._write(snapshot)
        return flow

    @staticmethod
    def _replace(items: list[BaseModel], item: BaseModel) -> list[BaseModel]:
        return [item if existing.id == item.id else existing for existing in items] + (
            [] if any(existing.id == item.id for existing in items) else [item]
        )

    def _write(self, snapshot: CatalogSnapshot) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(snapshot.model_dump(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

"""Import only portable ai-server character outputs into the local catalog."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from pydantic import BaseModel, Field

from .local_catalog import CharacterSpec, LocalCatalog


class CharacterImportCandidate(BaseModel):
    id: str
    name: str
    premise: str
    source_file: str
    prompt_file: str = ""
    style_file: str = ""
    generated_at: str = ""


class CharacterImportSkip(BaseModel):
    source_file: str
    reason: str


class CharacterImportPreview(BaseModel):
    available: bool
    source_directory: str
    candidates: list[CharacterImportCandidate] = Field(default_factory=list)
    skipped: list[CharacterImportSkip] = Field(default_factory=list)


class CharacterImportRequest(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=100)


class CharacterImportResult(BaseModel):
    imported: list[CharacterImportCandidate]
    skipped: list[CharacterImportSkip] = Field(default_factory=list)


@dataclass(frozen=True)
class _ScannedCharacter:
    candidate: CharacterImportCandidate
    character: CharacterSpec


class CharacterImporter:
    """Read generated outputs without touching ai-server state or chat data."""

    def __init__(self, source_directory: Path) -> None:
        self.source_directory = source_directory

    def preview(self) -> CharacterImportPreview:
        scanned, skipped = self._scan()
        return CharacterImportPreview(
            available=self._characters_directory().is_dir(),
            source_directory=str(self.source_directory),
            candidates=[item.candidate for item in scanned],
            skipped=skipped,
        )

    def import_selected(self, catalog: LocalCatalog, ids: list[str]) -> CharacterImportResult:
        scanned, skipped = self._scan()
        requested = set(ids)
        found = {item.candidate.id for item in scanned}
        skipped.extend(
            CharacterImportSkip(source_file=item_id, reason="找不到可匯入的角色")
            for item_id in requested - found
        )
        imported = []
        for item in scanned:
            if item.candidate.id in requested:
                catalog.save_character(item.character)
                imported.append(item.candidate)
        return CharacterImportResult(imported=imported, skipped=skipped)

    def _scan(self) -> tuple[list[_ScannedCharacter], list[CharacterImportSkip]]:
        characters_directory = self._characters_directory()
        if not characters_directory.is_dir():
            return [], [CharacterImportSkip(source_file=str(characters_directory), reason="找不到 ai-server 角色輸出目錄")]

        candidates: dict[str, tuple[_ScannedCharacter, str]] = {}
        skipped: list[CharacterImportSkip] = []
        for path in sorted(characters_directory.glob("*.json")):
            if "incomplete" in path.stem.lower():
                skipped.append(CharacterImportSkip(source_file=path.name, reason="來源標記為 incomplete"))
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                skipped.append(CharacterImportSkip(source_file=path.name, reason=f"JSON 無法讀取：{error}"))
                continue
            profile = payload.get("character") if isinstance(payload, dict) else None
            if not isinstance(profile, dict):
                skipped.append(CharacterImportSkip(source_file=path.name, reason="缺少 character 角色設定"))
                continue
            name = str(profile.get("character_name", "")).strip()
            if not name:
                skipped.append(CharacterImportSkip(source_file=path.name, reason="缺少 character_name"))
                continue
            generated_at = str(payload.get("metadata", {}).get("generated_at", ""))
            item = self._build(path, profile, generated_at)
            key = self._name_key(name)
            previous = candidates.get(key)
            if previous and previous[1] >= generated_at:
                skipped.append(CharacterImportSkip(source_file=path.name, reason=f"與「{previous[0].candidate.name}」重複，保留較新版本"))
                continue
            if previous:
                skipped.append(CharacterImportSkip(source_file=previous[0].candidate.source_file, reason=f"與「{name}」重複，改保留較新版本"))
            candidates[key] = (item, generated_at)
        return [item for item, _ in candidates.values()], skipped

    def _build(self, path: Path, profile: dict[str, Any], generated_at: str) -> _ScannedCharacter:
        name = str(profile["character_name"]).strip()
        source_key = self._artifact_key(path.stem)
        prompt = self._companion_text("generated_prompts", source_key, "完整prompt")
        style = self._companion_text("generated_styles", source_key, "_style")
        if not style:
            style = self._companion_text("generated_styles", source_key, "風格指南")
        premise = self._premise(profile)
        voice = self._voice(profile)
        identifier = "import-" + sha256(self._name_key(name).encode()).hexdigest()[:12]
        source = {
            "generated_file": path.name,
            "prompt_file": prompt[1],
            "style_file": style[1],
            "generated_at": generated_at,
        }
        character = CharacterSpec(
            id=identifier,
            name=name,
            premise=premise,
            voice=voice,
            profile=profile,
            style_guide=style[0],
            full_prompt=prompt[0],
            source=source,
        )
        return _ScannedCharacter(
            candidate=CharacterImportCandidate(
                id=identifier,
                name=name,
                premise=premise,
                source_file=path.name,
                prompt_file=prompt[1],
                style_file=style[1],
                generated_at=generated_at,
            ),
            character=character,
        )

    def _characters_directory(self) -> Path:
        return self.source_directory / "generated_characters"

    def _companion_text(self, directory: str, key: str, marker: str) -> tuple[str, str]:
        folder = self.source_directory / directory
        if not folder.is_dir():
            return "", ""
        for path in sorted(folder.iterdir()):
            if path.is_file() and self._artifact_key(path.stem) == key and marker in path.name:
                return path.read_text(encoding="utf-8"), path.name
        return "", ""

    @staticmethod
    def _artifact_key(stem: str) -> str:
        return re.sub(r"_\d{8}_\d{6}.*$", "", stem).casefold()

    @staticmethod
    def _name_key(name: str) -> str:
        return re.sub(r"[\W_]", "", name).casefold()

    @staticmethod
    def _premise(profile: dict[str, Any]) -> str:
        theme = profile.get("core_theme", {})
        archetype = theme.get("archetype_description", "") if isinstance(theme, dict) else ""
        backstory = str(profile.get("backstory", ""))
        return (str(archetype) or backstory or "匯入的 ai-server 角色設定。")[:2_000]

    @staticmethod
    def _voice(profile: dict[str, Any]) -> str:
        culture = profile.get("cultural_details", {})
        habits = culture.get("language_habits", "") if isinstance(culture, dict) else ""
        samples = profile.get("language_style", [])
        sample_text = "\n".join(str(item) for item in samples[:3]) if isinstance(samples, list) else str(samples)
        return (str(habits) + ("\n" if habits and sample_text else "") + sample_text or "依完整角色設定互動。")[:2_000]

"""Local persistence for the memory record shape used by ai-server."""

from __future__ import annotations

from datetime import datetime
import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MemoryRecord(BaseModel):
    """Portable subset of ai-server's JSON memory event contract."""

    # ai-server keeps extraction error fields and future metadata alongside this contract.
    model_config = ConfigDict(extra="allow")

    timestamp: str = Field(default_factory=lambda: datetime.now().astimezone().strftime("%Y-%m-%d %H:%M"))
    type: Literal["事實", "偏好", "事件", "標記", "event"] = "事實"
    summary: str = Field(default="記憶摘要", min_length=1, max_length=60)
    user_message: str | None = Field(default=None, max_length=8_000)
    character_response_summary: str | None = Field(default=None, max_length=2_000)
    key_points: list[str] = Field(default_factory=list, max_length=5)
    keywords: dict[str, str] = Field(default_factory=dict)


class LocalMemoryStore:
    """Persist records per chat_id without adding a database dependency."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def recent(self, chat_id: str, limit: int = 10) -> list[MemoryRecord]:
        return self._read(chat_id)[-limit:]

    def add(self, chat_id: str, record: MemoryRecord) -> MemoryRecord:
        records = self._read(chat_id)
        records.append(record)
        path = self._path(chat_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.parent.chmod(0o700)
        path.write_text(json.dumps([item.model_dump() for item in records], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        path.chmod(0o600)
        return record

    def delete(self, chat_id: str) -> None:
        path = self._path(chat_id)
        if path.exists():
            path.unlink()

    def search_by_text(self, chat_id: str, query: str, count: int = 5) -> list[MemoryRecord]:
        """Match full keyword phrases or delimited values, retaining newest-first order."""
        matched = [
            record for record in self._read(chat_id)
            if any(value and (value in query or any(term.strip() and term.strip() in query for term in re.split(r"[、,，;；\n]+", value))) for value in record.keywords.values())
        ]
        return sorted(matched, key=lambda record: self._timestamp(record.timestamp), reverse=True)[:count]

    def search_by_categories(
        self, chat_id: str, categories: list[str], max_results: int = 5
    ) -> list[MemoryRecord]:
        """Match keyword category names and return newest matches, not highest scores."""
        matches: list[MemoryRecord] = []
        for record in self._read(chat_id):
            matched_categories = {key: value for key, value in record.keywords.items() if key in categories}
            if matched_categories:
                extra = dict(record.model_extra or {})
                extra.update({"match_score": len(matched_categories) * 3, "matched_categories": matched_categories})
                matches.append(record.model_copy(update=extra))
        return sorted(matches, key=lambda record: record.timestamp, reverse=True)[:max_results]

    def relevant_for_message(self, chat_id: str, message: str, count: int = 5) -> list[MemoryRecord]:
        """Return keyword-relevant memories in ai-server's newest-first order.

        Values in the extracted ``keywords`` object also match individual
        delimited phrases; this adds no embeddings or semantic ranking layer.
        """
        return self.search_by_text(chat_id, message, count=count)

    def _read(self, chat_id: str) -> list[MemoryRecord]:
        path = self._path(chat_id)
        if not path.exists():
            return []
        try:
            raw_records = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return [self._validate_and_fix(record) for record in raw_records]

    @staticmethod
    def _validate_and_fix(memory: dict) -> MemoryRecord:
        """Mirror ai-server's tolerant reader for legacy/incomplete memory JSON."""
        record = dict(memory)
        if "timestamp" not in record:
            record["timestamp"] = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
        if "type" not in record:
            record["type"] = "標記" if record.get("error") else "事件" if record.get("key_points") else "事實"
        if "summary" not in record:
            if record.get("character_response_summary"):
                record["summary"] = record["character_response_summary"]
            elif record.get("user_message"):
                record["summary"] = record["user_message"]
            elif record.get("error_message"):
                record["summary"] = f"錯誤：{record['error_message'][:50]}"
            else:
                record["summary"] = "記憶摘要"
        record["summary"] = str(record["summary"])[:60]
        if not isinstance(record.get("keywords"), dict):
            record["keywords"] = {}
        return MemoryRecord.model_validate(record)

    @staticmethod
    def _timestamp(value: str) -> datetime:
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M")
        except ValueError:
            return datetime.min

    def _path(self, chat_id: str) -> Path:
        if not chat_id or any(part in chat_id for part in ("/", "\\", "..")):
            raise ValueError("Invalid chat id")
        return self.directory / f"{chat_id}.json"

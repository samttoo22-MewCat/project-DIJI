"""Local persistence for the memory record shape used by ai-server."""

from __future__ import annotations

from datetime import datetime
import json
import re
import hashlib
import os
import tempfile
import fcntl
from contextlib import contextmanager
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
        with self._locked(chat_id):
            records = self._raw(chat_id)
            records.append(record.model_dump())
            self._write(chat_id, records)
        return record

    def delete(self, chat_id: str) -> None:
        with self._locked(chat_id):
            self._path(chat_id).unlink(missing_ok=True)

    @staticmethod
    def _record_id(index: int, record: dict, revision: str) -> str:
        value = f"{revision}:{index}:" + json.dumps(record, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(value.encode()).hexdigest()

    @staticmethod
    def _revision(records: list[dict]) -> str:
        return hashlib.sha256(json.dumps(records, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

    def entries(self, chat_id: str, limit: int = 100) -> list[dict]:
        records = self._raw(chat_id)
        start = max(0, len(records) - limit)
        revision = self._revision(records)
        return [{**self._validate_and_fix(record).model_dump(), "record_id": self._record_id(index, record, revision)} for index, record in enumerate(records) if index >= start]

    def update_entry(self, chat_id: str, record_id: str, changes: dict) -> dict:
        with self._locked(chat_id):
            records = self._raw(chat_id)
            index = self._entry_index(records, record_id)
            updated = {**records[index], **changes, "manually_edited": True}
            self._validate_and_fix(updated)
            records[index] = updated
            self._write(chat_id, records)
            return {**self._validate_and_fix(updated).model_dump(), "record_id": self._record_id(index, updated, self._revision(records))}

    def delete_entry(self, chat_id: str, record_id: str) -> None:
        with self._locked(chat_id):
            records = self._raw(chat_id)
            del records[self._entry_index(records, record_id)]
            self._write(chat_id, records)

    def _entry_index(self, records: list[dict], record_id: str) -> int:
        revision = self._revision(records)
        for index, record in enumerate(records):
            if self._record_id(index, record, revision) == record_id:
                return index
        raise LookupError("記憶已變更或不存在，請重新載入後再操作。")

    def _raw(self, chat_id: str) -> list[dict]:
        path = self._path(chat_id)
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []

    @contextmanager
    def _locked(self, chat_id: str):
        path = self._path(chat_id)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.parent.chmod(0o700)
        with path.with_suffix('.lock').open('a') as lock:
            os.chmod(lock.name, 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _write(self, chat_id: str, records: list[dict]) -> None:
        path = self._path(chat_id)
        with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, encoding='utf-8', delete=False) as temporary:
            try:
                json.dump(records, temporary, ensure_ascii=False, indent=2)
                temporary.write('\n')
                temporary.flush()
                os.fsync(temporary.fileno())
                os.replace(temporary.name, path)
            finally:
                Path(temporary.name).unlink(missing_ok=True)

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

"""Local, full-fidelity conversation transcripts kept separate from event memory."""

from __future__ import annotations

from datetime import datetime
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import tempfile
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


def _now() -> int:
    return int(datetime.now().timestamp() * 1000)


class ConversationMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sender_type: Literal[1, 2]
    text: str = Field(min_length=1, max_length=16_000)
    timestamp: int = Field(default_factory=_now, ge=0)


class ConversationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chat_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    character_id: str = Field(min_length=1, max_length=64)
    character_name: str = Field(min_length=1, max_length=80)
    chat_mode: Literal["story", "dialog"] = "story"
    created_at: int = Field(default_factory=_now, ge=0)
    updated_at: int = Field(default_factory=_now, ge=0)
    messages: list[ConversationMessage] = Field(default_factory=list, max_length=5_000)


class ConversationSummary(BaseModel):
    chat_id: str
    character_id: str
    character_name: str
    chat_mode: Literal["story", "dialog"]
    updated_at: int
    message_count: int
    preview: str = ""


class ConversationStore:
    """Persist complete local transcripts without changing ai-server memory semantics."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def list(self) -> list[ConversationSummary]:
        if not self.directory.exists():
            return []
        records = [self.get(path.stem) for path in self.directory.glob("*.json")]
        return sorted((self._summary(record) for record in records), key=lambda item: item.updated_at, reverse=True)

    def get(self, chat_id: str) -> ConversationRecord:
        path = self._path(chat_id)
        if not path.exists():
            raise StopIteration(chat_id)
        return ConversationRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def start(self, chat_id: str, character_id: str, character_name: str, chat_mode: Literal["story", "dialog"] = "story") -> ConversationRecord:
        with self._lock(chat_id):
            return self._start(chat_id, character_id, character_name, chat_mode)

    def _start(self, chat_id, character_id, character_name, chat_mode="story"):
        try:
            return self.get(chat_id)
        except StopIteration:
            record = ConversationRecord(chat_id=chat_id, character_id=character_id, character_name=character_name, chat_mode=chat_mode)
            self._write(record)
            return record

    def append(self, chat_id: str, character_id: str, character_name: str, message: ConversationMessage) -> ConversationRecord:
        with self._lock(chat_id):
            record = self._start(chat_id, character_id, character_name)
            record.messages.append(message)
            record.updated_at = _now()
            self._write(record)
            return record

    def set_mode(self, chat_id: str, chat_mode: Literal["story", "dialog"]) -> ConversationRecord:
        with self._lock(chat_id):
            record = self.get(chat_id)
            record.chat_mode = chat_mode
            record.updated_at = _now()
            self._write(record)
            return record

    @contextmanager
    def _lock(self, chat_id):
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

    def _write(self, record: ConversationRecord) -> None:
        path = self._path(record.chat_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.parent.chmod(0o700)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as output:
            temporary = Path(output.name)
            try:
                output.write(record.model_dump_json(indent=2) + '\n')
                output.flush()
                os.fsync(output.fileno())
            except BaseException:
                temporary.unlink(missing_ok=True)
                raise
        try:
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        path.chmod(0o600)

    @staticmethod
    def _summary(record: ConversationRecord) -> ConversationSummary:
        latest = record.messages[-1].text if record.messages else "尚未開始對話"
        return ConversationSummary(
            chat_id=record.chat_id,
            character_id=record.character_id,
            character_name=record.character_name,
            chat_mode=record.chat_mode,
            updated_at=record.updated_at,
            message_count=len(record.messages),
            preview=" ".join(latest.split())[:80],
        )

    def _path(self, chat_id: str) -> Path:
        if not chat_id or any(part in chat_id for part in ("/", "\\", "..")):
            raise ValueError("Invalid chat id")
        return self.directory / f"{chat_id}.json"

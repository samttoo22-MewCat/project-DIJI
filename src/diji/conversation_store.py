"""Local, full-fidelity conversation transcripts kept separate from event memory."""

from __future__ import annotations

from datetime import datetime
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


def _now() -> int:
    return int(datetime.now().timestamp() * 1000)


class ConversationBusy(Exception):
    pass


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
    parent_chat_id: str | None = None
    edited_message_index: int | None = None
    state_checkpoint_available: bool | None = None
    revision: str = ''


class ConversationSummary(BaseModel):
    chat_id: str
    character_id: str
    character_name: str
    chat_mode: Literal["story", "dialog"]
    updated_at: int
    message_count: int
    preview: str = ""
    parent_chat_id: str | None = None


class ConversationStore:
    """Persist complete local transcripts without changing ai-server memory semantics."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    @contextmanager
    def turn(self, chat_id):
        path = self._path(chat_id).with_suffix('.turn.lock')
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with path.open('a') as lock:
            os.chmod(lock.name, 0o600)
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ConversationBusy('此對話正在生成，請等候本回合完成後再送出') from error
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def list(self) -> list[ConversationSummary]:
        if not self.directory.exists():
            return []
        records = [self.get(path.stem) for path in self.directory.glob("*.json")]
        return sorted((self._summary(record) for record in records), key=lambda item: item.updated_at, reverse=True)

    def get(self, chat_id: str) -> ConversationRecord:
        path = self._path(chat_id)
        if not path.exists():
            raise StopIteration(chat_id)
        record = ConversationRecord.model_validate_json(path.read_text(encoding="utf-8"))
        record.revision = self.fingerprint(record)
        return record

    @staticmethod
    def fingerprint(record):
        return hashlib.sha256(record.model_dump_json(exclude={'revision'}).encode()).hexdigest()

    @staticmethod
    def prefix_fingerprint(messages):
        return hashlib.sha256(json.dumps([m.model_dump() for m in messages],sort_keys=True,ensure_ascii=False).encode()).hexdigest()

    def fork_edit(self, chat_id, index, expected_revision, new_id, *, checkpoint_available=None):
        with self._lock(chat_id):
            record = self.get(chat_id)
            if record.revision != expected_revision:
                raise ValueError('對話已變更，請重新載入後再編輯')
            if index < 0 or index >= len(record.messages) or record.messages[index].sender_type != 1:
                raise ValueError('只能編輯自己已送出的訊息')
            branch = ConversationRecord(chat_id=new_id,character_id=record.character_id,character_name=record.character_name,
                chat_mode=record.chat_mode,messages=[m.model_copy(deep=True) for m in record.messages[:index]],
                parent_chat_id=chat_id,edited_message_index=index,state_checkpoint_available=checkpoint_available)
            with self._lock(new_id):
                if self._path(new_id).exists():
                    raise ValueError('新對話識別碼已使用')
                self._write(branch)
            return branch

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
        record.revision = self.fingerprint(record)
        path = self._path(record.chat_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.parent.chmod(0o700)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as output:
            temporary = Path(output.name)
            try:
                output.write(record.model_dump_json(indent=2,exclude={'revision'}) + '\n')
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
            parent_chat_id=record.parent_chat_id,
        )

    def _path(self, chat_id: str) -> Path:
        if not chat_id or any(part in chat_id for part in ("/", "\\", "..")):
            raise ValueError("Invalid chat id")
        return self.directory / f"{chat_id}.json"

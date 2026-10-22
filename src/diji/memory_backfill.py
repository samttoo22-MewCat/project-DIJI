"""Explicit, atomic event-memory backfill for one saved conversation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .conversation_store import ConversationMessage, ConversationRecord
from .memory_extraction import MemoryExtractor
from .memory_store import LocalMemoryStore, MemoryRecord


MAX_BACKFILL_MESSAGES = 80
BACKFILL_BATCH_SIZE = 8


@dataclass(frozen=True)
class MemoryBackfillResult:
    created: int
    skipped: bool
    records: list[MemoryRecord]


def _chunks(messages: list[ConversationMessage]) -> Iterable[list[ConversationMessage]]:
    for start in range(0, len(messages), BACKFILL_BATCH_SIZE):
        yield messages[start:start + BACKFILL_BATCH_SIZE]


def _conversation_text(character_name: str, messages: list[ConversationMessage]) -> str:
    lines = []
    for message in messages:
        speaker = "使用者" if message.sender_type == 1 else character_name
        lines.append(f"<{speaker}>{message.text}</{speaker}>")
    return "\n".join(lines)


async def backfill_conversation(
    conversation: ConversationRecord,
    memories: LocalMemoryStore,
    extractor: MemoryExtractor,
) -> MemoryBackfillResult:
    """Backfill a saved transcript without duplicating or partially saving events."""
    if memories.recent(conversation.chat_id, limit=1):
        return MemoryBackfillResult(created=0, skipped=True, records=[])
    if not conversation.messages:
        raise ValueError("這段對話尚未有可建立記憶的訊息")

    extracted: list[MemoryRecord] = []
    messages = conversation.messages[-MAX_BACKFILL_MESSAGES:]
    for batch in _chunks(messages):
        records = await extractor.extract(_conversation_text(conversation.character_name, batch))
        if not records:
            raise RuntimeError("記憶抽取未回傳結構化結果，尚未寫入任何記憶")
        if any((record.model_extra or {}).get("error") for record in records):
            raise RuntimeError("記憶抽取失敗，尚未寫入任何記憶")
        extracted.extend(records)

    for record in extracted:
        memories.add(conversation.chat_id, record)
    return MemoryBackfillResult(created=len(extracted), skipped=False, records=extracted)

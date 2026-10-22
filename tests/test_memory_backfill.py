import asyncio
from pathlib import Path

import pytest

from diji.conversation_store import ConversationMessage, ConversationRecord
from diji.memory_backfill import backfill_conversation
from diji.memory_store import LocalMemoryStore, MemoryRecord


class RecordingExtractor:
    def __init__(self, fail_on_call: int | None = None) -> None:
        self.calls: list[str] = []
        self.fail_on_call = fail_on_call

    async def extract(self, conversation: str) -> list[MemoryRecord]:
        self.calls.append(conversation)
        if self.fail_on_call == len(self.calls):
            return [MemoryRecord(type="標記", summary="錯誤：LLM提取事件失敗", error=True)]
        return [MemoryRecord(type="事件", summary=f"第 {len(self.calls)} 段事件", keywords={"地點": "咖啡館"})]


def _conversation(count: int = 9) -> ConversationRecord:
    return ConversationRecord(
        chat_id="saved-chat",
        character_id="yelan",
        character_name="夜蘭",
        messages=[ConversationMessage(sender_type=1 if index % 2 == 0 else 2, text=f"第 {index} 則") for index in range(count)],
    )


def test_backfill_saves_only_after_every_batch_extracts_and_never_duplicates(tmp_path: Path) -> None:
    memories = LocalMemoryStore(tmp_path / "memories")
    extractor = RecordingExtractor()

    result = asyncio.run(backfill_conversation(_conversation(), memories, extractor))
    repeated = asyncio.run(backfill_conversation(_conversation(), memories, extractor))

    assert result.created == 2
    assert "<使用者>第 0 則</使用者>" in extractor.calls[0]
    assert "<夜蘭>第 1 則</夜蘭>" in extractor.calls[0]
    assert len(memories.recent("saved-chat", limit=10)) == 2
    assert repeated.skipped is True
    assert len(extractor.calls) == 2


def test_backfill_is_atomic_when_an_extraction_batch_fails(tmp_path: Path) -> None:
    memories = LocalMemoryStore(tmp_path / "memories")

    with pytest.raises(RuntimeError, match="尚未寫入"):
        asyncio.run(backfill_conversation(_conversation(), memories, RecordingExtractor(fail_on_call=2)))

    assert memories.recent("saved-chat") == []

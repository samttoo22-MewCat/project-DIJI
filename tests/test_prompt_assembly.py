from fastapi.testclient import TestClient

from diji.local_app import create_app
from diji.local_catalog import CharacterSpec, FlowSpec, LocalCatalog
from diji.memory_extraction import MemoryExtractor
from diji.memory_store import LocalMemoryStore, MemoryRecord
from diji.prompt_assembly import PromptPreviewRequest, assemble_prompt


def test_prompt_bundle_follows_the_flow_order_and_inserts_scene() -> None:
    character = CharacterSpec(id="test", name="測試", premise="定位", voice="語氣")
    flow = FlowSpec(
        id="legacy", name="舊流程", template="immersive", layers=["character", "template", "history", "memory"]
    )
    bundle = assemble_prompt(
        character,
        flow,
        PromptPreviewRequest(
            character_id="test", flow_id="legacy", scene="雨夜的車站", history=[{"role": "user", "content": "我到了。"}]
        ),
        [MemoryRecord(type="事實", summary="角色害怕雷聲")],
    )

    assert [layer.key for layer in bundle.layers] == ["character", "template", "scene", "history", "memory"]
    assert "雨夜的車站" in bundle.rendered_text
    assert "<MEM>" in bundle.rendered_text
    assert "角色害怕雷聲" in bundle.rendered_text
    assert bundle.memory_injection_mode == "system"


def test_prompt_preview_endpoint_reads_the_catalog(tmp_path) -> None:
    catalog = LocalCatalog(tmp_path / "catalog.json")
    memories = LocalMemoryStore(tmp_path / "memories")
    catalog.save_character(CharacterSpec(id="test", name="測試", premise="定位", voice="語氣"))
    catalog.save_flow(FlowSpec(id="test-flow", name="測試流程"))
    client = TestClient(create_app(catalog, memories))
    stored = client.put("/api/memories/test-chat", json={"type": "偏好", "summary": "偏好雨天散步"})
    assert stored.status_code == 200

    response = client.post(
        "/api/prompt-preview",
        json={"character_id": "test", "flow_id": "test-flow", "chat_id": "test-chat", "scene": "圖書館"},
    )

    assert response.status_code == 200
    assert "圖書館" in response.json()["rendered_text"]
    assert "偏好雨天散步" in response.json()["rendered_text"]


class FakeExtractionClient:
    async def create(self, **kwargs: object) -> str:
        assert kwargs["model"] == "deepseek/deepseek-v4.1-flash"
        assert kwargs["temperature"] == 0.3
        return '{"type":"偏好","summary":"喜歡雨天","keywords":{"天氣":"雨天"}}'


def test_extract_endpoint_uses_ai_server_prompt_contract_and_persists(tmp_path) -> None:
    catalog = LocalCatalog(tmp_path / "catalog.json")
    memories = LocalMemoryStore(tmp_path / "memories")
    client = TestClient(create_app(catalog, memories, MemoryExtractor(FakeExtractionClient())))

    response = client.post("/api/memories/test-chat/extract", json={"conversation": "<user>我喜歡雨天</user>"})

    assert response.status_code == 200
    assert response.json()[0]["summary"] == "喜歡雨天"
    assert memories.recent("test-chat")[0].keywords == {"天氣": "雨天"}


def test_memory_search_matches_ai_server_category_and_keyword_behavior(tmp_path) -> None:
    memories = LocalMemoryStore(tmp_path / "memories")
    memories.add("test-chat", MemoryRecord(timestamp="2026-01-01 10:00", summary="舊車站", keywords={"地點": "車站"}))
    memories.add("test-chat", MemoryRecord(timestamp="2026-01-02 10:00", summary="新車站", keywords={"地點": "車站", "活動": "散步"}))

    assert [item.summary for item in memories.search_by_text("test-chat", "去車站嗎")] == ["新車站", "舊車站"]
    category_results = memories.search_by_categories("test-chat", ["地點"])
    assert [item.summary for item in category_results] == ["新車站", "舊車站"]
    assert category_results[0].model_extra["match_score"] == 3


def test_reading_legacy_memory_repairs_missing_fields_like_ai_server(tmp_path) -> None:
    path = tmp_path / "memories" / "test-chat.json"
    path.parent.mkdir()
    path.write_text('[{"error": true, "error_message": "failed"}, {"key_points": ["約定"], "user_message": "明天見"}]')

    records = LocalMemoryStore(path.parent).recent("test-chat")

    assert [(record.type, record.summary) for record in records] == [("標記", "錯誤：failed"), ("事件", "明天見")]


def test_request_can_disable_memory_injection_without_changing_persisted_data() -> None:
    character = CharacterSpec(id="test", name="測試", premise="定位", voice="語氣")
    flow = FlowSpec(id="test-flow", name="測試流程")

    bundle = assemble_prompt(
        character,
        flow,
        PromptPreviewRequest(character_id="test", flow_id="test-flow", inject_memory=False),
        [MemoryRecord(summary="不應注入")],
    )

    assert bundle.memory_injection_mode == "none"
    assert "不應注入" not in bundle.rendered_text

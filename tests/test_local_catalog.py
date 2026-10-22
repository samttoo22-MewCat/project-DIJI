import os
from pathlib import Path

from fastapi.testclient import TestClient

from diji.local_app import create_app
from diji.conversation_store import ConversationMessage, ConversationStore
from diji.memory_store import LocalMemoryStore, MemoryRecord
from diji.relationship import JudgeResult
from diji.local_catalog import CharacterSpec, LocalCatalog
from diji.character_import import CharacterImporter
from diji.experiments import ExperimentStore, JailbreakPreset, JailbreakStore
from diji.relationship import RelationshipStore


def test_local_ui_boots_without_a_provider_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    client = TestClient(create_app(LocalCatalog(tmp_path / "catalog.json")))

    assert client.get("/api/bootstrap").status_code == 200


def test_catalog_returns_defaults_without_creating_runtime_file(tmp_path: Path) -> None:
    store_path = tmp_path / "catalog.json"

    snapshot = LocalCatalog(store_path).snapshot()

    assert [character.id for character in snapshot.characters] == ["yelan", "shenzhou"]
    assert not store_path.exists()


def test_character_save_persists_through_the_http_interface(tmp_path: Path) -> None:
    catalog = LocalCatalog(tmp_path / "catalog.json")
    client = TestClient(create_app(catalog))
    character = CharacterSpec(
        id="yelan",
        name="夜蘭",
        premise="更新後的角色定位。",
        voice="冷靜而準確。",
        relationship_start="familiar",
    )

    response = client.put("/api/characters/yelan", json=character.model_dump())

    assert response.status_code == 200
    assert client.get("/api/characters/yelan").json()["premise"] == "更新後的角色定位。"
    assert catalog.character("yelan").relationship_start == "familiar"


def test_character_url_and_payload_ids_must_match(tmp_path: Path) -> None:
    client = TestClient(create_app(LocalCatalog(tmp_path / "catalog.json")))

    response = client.put(
        "/api/characters/yelan",
        json={"id": "shenzhou", "name": "沈舟", "premise": "p", "voice": "v"},
    )

    assert response.status_code == 400


def test_explicit_interaction_and_relationship_routes_use_injected_service(tmp_path: Path) -> None:
    class FakeInteractionService:
        async def respond(self, request):
            return {
                "chat_id": request.chat_id,
                "character_id": request.character.id,
                "text": "回覆",
                "messages": [],
                "memory_saved": False,
                "relationship_updated": False,
            }

    relationships = RelationshipStore(tmp_path / "relationships")
    client = TestClient(
        create_app(
            LocalCatalog(tmp_path / "catalog.json"),
            relationship_store=relationships,
            interaction_service=FakeInteractionService(),
            conversation_store=ConversationStore(tmp_path / "conversations"),
        )
    )
    request = {
        "chat_id": "test-chat",
        "llm": {"model": "test"},
        "character": {"id": "test-character", "name": "測試", "description": "角色描述"},
        "user": {"id": "test-user", "persona": {"name": "使用者"}},
        "message": {"sender_id": "test-user", "text": "你好"},
    }

    response = client.post("/api/interactions", json=request)

    assert response.status_code == 200
    assert response.json()["text"] == "回覆"
    assert client.get("/api/relationships/test-chat").json()["current_stage"] == 1
    conversation = client.get("/api/conversations/test-chat").json()
    assert [message["text"] for message in conversation["messages"]] == ["你好", "回覆"]


def test_conversation_api_keeps_full_transcript_and_lists_latest_first(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path / "conversations")
    client = TestClient(create_app(LocalCatalog(tmp_path / "catalog.json"), conversation_store=store))

    created = client.post("/api/conversations", json={"chat_id": "chat-a", "character_id": "yelan", "character_name": "夜蘭"})

    assert created.status_code == 200
    assert created.json()["messages"] == []
    store.append("chat-a", "yelan", "夜蘭", ConversationMessage(sender_type=1, text="第一句"))
    detail = client.get("/api/conversations/chat-a")
    assert detail.status_code == 200
    assert detail.json()["messages"][0]["text"] == "第一句"
    assert client.get("/api/conversations").json()[0]["preview"] == "第一句"


def test_conversation_mode_persists_for_each_chat(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path / "conversations")
    client = TestClient(create_app(LocalCatalog(tmp_path / "catalog.json"), conversation_store=store))

    created = client.post(
        "/api/conversations",
        json={"chat_id": "chat-mode", "character_id": "yelan", "character_name": "夜蘭", "chat_mode": "dialog"},
    )
    changed = client.put("/api/conversations/chat-mode/mode", json={"chat_mode": "story"})

    assert created.status_code == 200
    assert created.json()["chat_mode"] == "dialog"
    assert changed.status_code == 200
    assert changed.json()["chat_mode"] == "story"
    assert client.get("/api/conversations/chat-mode").json()["chat_mode"] == "story"


def test_backfill_builds_memories_only_for_the_saved_conversation(tmp_path: Path) -> None:
    class FakeExtractor:
        def __init__(self) -> None:
            self.calls = 0

        async def extract(self, conversation):
            self.calls += 1
            return [MemoryRecord(type="事件", summary="既有對話的事件", keywords={"活動": "聊天"})]

    class FakeInteractionService:
        def __init__(self, extractor) -> None:
            self.extractor = extractor

    memories = LocalMemoryStore(tmp_path / "memories")
    conversations = ConversationStore(tmp_path / "conversations")
    conversations.start("chat-backfill", "yelan", "夜蘭")
    conversations.append("chat-backfill", "yelan", "夜蘭", ConversationMessage(sender_type=1, text="你好"))
    extractor = FakeExtractor()
    client = TestClient(create_app(
        LocalCatalog(tmp_path / "catalog.json"),
        memory_store=memories,
        conversation_store=conversations,
        interaction_service=FakeInteractionService(extractor),
    ))

    created = client.post("/api/memories/chat-backfill/backfill")
    repeated = client.post("/api/memories/chat-backfill/backfill")

    assert created.status_code == 200
    assert created.json()["created"] == 1
    assert repeated.json()["skipped"] is True
    assert extractor.calls == 1
    assert client.get("/api/memories/chat-backfill").json()[0]["summary"] == "既有對話的事件"


def test_reset_matches_ai_server_by_clearing_memory_and_relationship_only(tmp_path: Path) -> None:
    memories = LocalMemoryStore(tmp_path / "memories")
    memories.add("reset-chat", MemoryRecord(summary="暫存記憶"))
    relationships = RelationshipStore(tmp_path / "relationships")
    relationships.apply("reset-chat", JudgeResult(emotional_value=3))
    client = TestClient(create_app(LocalCatalog(tmp_path / "catalog.json"), memories, relationship_store=relationships))
    payload = {
        "chat_id": "reset-chat", "reset": True, "llm": {"model": "test"},
        "character": {"id": "test-character", "name": "測試", "description": "角色描述"},
        "user": {"id": "test-user", "persona": {"name": "使用者"}},
        "message": {"sender_id": "test-user", "text": "重置"},
    }

    response = client.post("/api/interactions", json=payload)

    assert response.status_code == 200 and response.json()["text"] == "上下文已重置。"
    assert memories.recent("reset-chat") == []
    assert relationships.get("reset-chat").current_score == 0


def test_jailbreak_catalog_groups_only_current_openrouter_models(tmp_path: Path) -> None:
    items = JailbreakStore(tmp_path / "jailbreaks.json").import_recent_catalog()

    assert len(items) > 20
    assert next(item for item in items if item.id == "opus-4-5-4-8").name == "Opus 4.5–4.8"
    assert all(item.openrouter_models for item in items)
    assert all(item.review_status == "metadata_only" and not item.prompt for item in items)


def test_jailbreak_can_be_deleted_through_the_http_interface(tmp_path: Path) -> None:
    jailbreaks = JailbreakStore(tmp_path / "jailbreaks.json")
    jailbreaks.save(
        JailbreakPreset(
            id="local-rule",
            name="本機規則",
            model="測試模型",
            last_updated="2026-10-10",
            source_url="local",
        )
    )
    client = TestClient(create_app(LocalCatalog(tmp_path / "catalog.json"), jailbreak_store=jailbreaks))

    response = client.delete("/api/jailbreaks/local-rule")

    assert response.status_code == 200
    assert response.json()["id"] == "local-rule"
    assert jailbreaks.list() == []


def test_adult_interaction_resolves_the_approved_jailbreak_for_its_model(tmp_path: Path) -> None:
    class FakeInteractionService:
        def __init__(self):
            self.requests = []

        async def respond(self, request):
            self.requests.append(request)
            return {
                "chat_id": request.chat_id,
                "character_id": request.character.id,
                "text": "回覆",
                "messages": [],
                "memory_saved": False,
                "relationship_updated": False,
            }

    jailbreaks = JailbreakStore(tmp_path / "jailbreaks.json")
    jailbreaks.save(
        JailbreakPreset(
            id="model-specific",
            name="模型專用越獄",
            model="測試模型",
            openrouter_models=("provider/test-model",),
            last_updated="2026-10-10",
            source_url="local",
            review_status="approved",
            prompt="本機越獄文字",
        )
    )
    experiments = ExperimentStore(tmp_path / "experiments.json")
    interaction = FakeInteractionService()
    client = TestClient(
        create_app(
            LocalCatalog(tmp_path / "catalog.json"),
            jailbreak_store=jailbreaks,
            experiment_store=experiments,
            interaction_service=interaction,
            conversation_store=ConversationStore(tmp_path / "conversations"),
        )
    )
    payload = {
        "chat_id": "adult-chat",
        "llm": {"model": "provider/test-model"},
        "character": {"id": "test-character", "name": "測試", "description": "角色描述"},
        "user": {"id": "test-user", "persona": {"name": "使用者"}},
        "message": {"sender_id": "test-user", "text": "你好"},
        "is_nsfw": True,
        "experiment_id": "forged-mismatch",
    }

    response = client.post("/api/interactions", json=payload)

    assert response.status_code == 200
    assert interaction.requests[0].experiment_id == "interaction-model-specific"
    assert experiments.get("interaction-model-specific").jailbreak_id == "model-specific"

    payload["llm"]["model"] = "provider/no-jailbreak"
    rejected = client.post("/api/interactions", json=payload)

    assert rejected.status_code == 400
    assert len(interaction.requests) == 1


def test_openrouter_key_can_be_saved_locally_without_being_returned(tmp_path: Path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    client = TestClient(create_app(LocalCatalog(tmp_path / "catalog.json"), env_path=env_path))

    response = client.put("/api/settings/openrouter-key", json={"openrouter_api_key": "test-key"})

    assert response.status_code == 204
    assert response.content == b""
    assert env_path.read_text(encoding="utf-8") == "OPENROUTER_API_KEY=test-key\n"
    assert env_path.stat().st_mode & 0o777 == 0o600
    assert os.environ["OPENROUTER_API_KEY"] == "test-key"


def test_ai_server_character_import_previews_and_imports_only_complete_valid_outputs(tmp_path: Path) -> None:
    output = tmp_path / "output"
    characters = output / "generated_characters"
    prompts = output / "generated_prompts"
    styles = output / "generated_styles"
    characters.mkdir(parents=True)
    prompts.mkdir()
    styles.mkdir()
    profile = {
        "character_name": "測試者",
        "core_theme": {"archetype_description": "保有來源人設的測試角色。"},
        "cultural_details": {"language_habits": "語氣平靜。"},
        "language_style": ["這是一句範例台詞。"],
        "psychological_evolution": {"stage_1": {"tone": "冷靜"}},
    }
    (characters / "測試者_20261010_120000.json").write_text(
        __import__("json").dumps({"metadata": {"generated_at": "2026-10-10 12:00:00"}, "character": profile}, ensure_ascii=False),
        encoding="utf-8",
    )
    (characters / "測試者_20261010_120001_incomplete.json").write_text("{}", encoding="utf-8")
    (characters / "壞掉_20261010_120002.json").write_text("{", encoding="utf-8")
    (prompts / "測試者_20261010_120000_完整prompt.md").write_text("完整 prompt", encoding="utf-8")
    (styles / "測試者_20261010_120000_style.txt").write_text("風格指南", encoding="utf-8")
    catalog = LocalCatalog(tmp_path / "catalog.json")
    client = TestClient(create_app(catalog, character_importer=CharacterImporter(output)))

    preview = client.get("/api/character-imports/preview")

    assert preview.status_code == 200
    candidate = preview.json()["candidates"][0]
    assert candidate["name"] == "測試者"
    assert len(preview.json()["skipped"]) == 2

    imported = client.post("/api/character-imports", json={"ids": [candidate["id"]]})

    assert imported.status_code == 200
    saved = catalog.character(candidate["id"])
    assert saved.full_prompt == "完整 prompt"
    assert saved.style_guide == "風格指南"
    assert saved.profile["psychological_evolution"]["stage_1"]["tone"] == "冷靜"

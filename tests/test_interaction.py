import asyncio
from datetime import datetime, timezone

from diji.domain import (
    InteractionCharacter,
    InteractionMessage,
    InteractionRequest,
    InteractionUser,
    ModelConfiguration,
    UserPersona,
)
from diji.experiments import ExperimentStore, PromptExperiment
from diji.favorability_judge import OpenRouterFavorabilityJudge
from diji.interaction import InteractionService
from diji.memory_store import LocalMemoryStore, MemoryRecord
from diji.relationship import JudgeResult, RelationshipState, RelationshipStore
from diji.user_profile import UserProfileStore


class FakeAdapter:
    async def generate(self, config, messages):
        return "<MEM>leak</MEM>\n2026-10-01 12:00 hello\\nworld!"


class FakeExtractor:
    async def extract(self, conversation):
        return [MemoryRecord(type="事件", summary="互動已完成", user_message="你好")]


class FakeJudge:
    async def judge(self, conversation, request, state):
        return JudgeResult(emotional_value=3, self_disclosure=3, boundary_respect=3, value_alignment=3)


def request(**overrides):
    payload = {
        "chat_id": "test-chat",
        "llm": ModelConfiguration(model="test"),
        "character": InteractionCharacter(
            id="test-character", name="測試", description="角色描述", psychological_evolution={"enabled": True}
        ),
        "user": InteractionUser(id="test-user", persona=UserPersona(name="使用者", description="使用者描述")),
        "message": InteractionMessage(sender_id="test-user", text="你好"),
    }
    payload.update(overrides)
    return InteractionRequest(**payload)


def test_interaction_turn_matches_the_architecture_and_persists_outputs(tmp_path):
    memories = LocalMemoryStore(tmp_path / "memories")
    memories.add("test-chat", MemoryRecord(timestamp="2026-01-01 00:00", summary="既有記憶", user_message="之前的話"))
    experiments = ExperimentStore(tmp_path / "experiments.json")
    experiments.save(PromptExperiment(id="test", name="測試實驗", story_style="風格", ending_rules="結尾規則"))
    service = InteractionService(
        FakeAdapter(), memories, FakeExtractor(), RelationshipStore(tmp_path / "relationships"), experiments, FakeJudge()
    )

    result = asyncio.run(service.respond(request(experiment_id="test"), datetime(2026, 1, 2, tzinfo=timezone.utc)))

    assert result.text == "leak\nhello\nworld！"
    assert "<MEM>" in result.messages[0]["content"]
    assert result.memory_saved and result.relationship_updated
    assert memories.recent("test-chat")[-1].summary == "互動已完成"
    assert RelationshipStore(tmp_path / "relationships").get("test-chat").current_score == 12


def test_interaction_persists_a_turn_memory_when_extraction_returns_nothing(tmp_path):
    class EmptyExtractor:
        async def extract(self, conversation):
            return []

    memories = LocalMemoryStore(tmp_path / "memories")
    service = InteractionService(
        FakeAdapter(), memories, EmptyExtractor(), RelationshipStore(tmp_path / "relationships"), ExperimentStore(tmp_path / "experiments.json")
    )

    result = asyncio.run(service.respond(request(message=InteractionMessage(sender_id="test-user", text="我喜歡雨天散步"))))

    assert result.memory_saved
    record = memories.recent("test-chat")[-1]
    assert record.type == "事件"
    assert record.user_message == "我喜歡雨天散步"
    assert record.character_response_summary == "leak\nhello\nworld！"


def test_memory_user_mode_places_block_in_current_message(tmp_path):
    memories = LocalMemoryStore(tmp_path / "memories")
    memories.add("test-chat", MemoryRecord(summary="既有記憶"))
    service = InteractionService(
        FakeAdapter(), memories, FakeExtractor(), RelationshipStore(tmp_path / "relationships"), ExperimentStore(tmp_path / "experiments.json")
    )

    messages = service.build_messages(request(inject_memory=None), datetime(2026, 1, 2, tzinfo=timezone.utc))

    assert "<MEM>" in messages[0]["content"]


def test_interaction_injects_only_keyword_relevant_memory_in_the_relevant_layer(tmp_path):
    memories = LocalMemoryStore(tmp_path / "memories")
    memories.add("test-chat", MemoryRecord(summary="會合在車站", keywords={"地點": "車站"}))
    memories.add("test-chat", MemoryRecord(summary="無關記憶", keywords={"物品": "雨傘"}))
    service = InteractionService(
        FakeAdapter(), memories, FakeExtractor(), RelationshipStore(tmp_path / "relationships"), ExperimentStore(tmp_path / "experiments.json")
    )

    messages = service.build_messages(request(message=InteractionMessage(sender_id="test-user", text="我到車站了")), datetime(2026, 1, 2, tzinfo=timezone.utc))

    relevant = messages[0]["content"].split("<RELEVANT_MEM>", 1)[1].split("</RELEVANT_MEM>", 1)[0]
    assert "會合在車站" in relevant
    assert "無關記憶" not in relevant


def test_interaction_keeps_ai_server_memory_shape_and_relationship_guidance(tmp_path):
    memories = LocalMemoryStore(tmp_path / "memories")
    memories.add("test-chat", MemoryRecord(type="事件", summary="約在車站見面", character_response_summary="她答應赴約", keywords={"地點": "車站"}))
    service = InteractionService(
        FakeAdapter(), memories, FakeExtractor(), RelationshipStore(tmp_path / "relationships"), ExperimentStore(tmp_path / "experiments.json")
    )

    messages = service.build_messages(request(), datetime(2026, 1, 2, tzinfo=timezone.utc))

    assert "(事件) 約在車站見面 | 回覆總結: 她答應赴約 | 關鍵字: 地點: 車站" in messages[0]["content"]
    assert "<FAVORABILITY>" in messages[0]["content"]


def test_interaction_persists_and_reinjects_ai_server_user_profile(tmp_path):
    class ProfileJudge(FakeJudge):
        async def judge(self, conversation, request, state):
            return JudgeResult(user_profile_update={"interaction_style": "偏好簡短回覆"})

    profiles = UserProfileStore(tmp_path / "profiles")
    service = InteractionService(
        FakeAdapter(), LocalMemoryStore(tmp_path / "memories"), FakeExtractor(), RelationshipStore(tmp_path / "relationships"),
        ExperimentStore(tmp_path / "experiments.json"), ProfileJudge(), profiles=profiles,
    )

    asyncio.run(service.respond(request(), datetime(2026, 1, 2, tzinfo=timezone.utc)))
    profile = profiles.get("test-user")
    messages = service.build_messages(request(), datetime(2026, 1, 2, tzinfo=timezone.utc))

    assert profile["interaction_style"] == "偏好簡短回覆"
    assert "<USER_PROFILE>" in messages[0]["content"]
    assert "互動風格：偏好簡短回覆" in messages[0]["content"]


def test_favorability_judge_keeps_the_ai_server_event_and_profile_contract():
    prompt = OpenRouterFavorabilityJudge._build_prompt(
        "<user>我會陪著你</user>", request(), RelationshipState()
    )

    assert "共同興趣發現" not in prompt
    assert "持續的尊重" in prompt
    assert "favorite_topics" in prompt


def test_story_and_dialog_keep_separate_ai_server_format_rules(tmp_path):
    service = InteractionService(
        FakeAdapter(), LocalMemoryStore(tmp_path / "memories"), FakeExtractor(), RelationshipStore(tmp_path / "relationships"), ExperimentStore(tmp_path / "experiments.json")
    )
    story = service.build_messages(request(), datetime(2026, 1, 2, tzinfo=timezone.utc))[0]["content"]
    dialog_request = request(user=InteractionUser(id="test-user", persona=UserPersona(name="使用者", description="使用者描述", chat_mode="dialog")))
    dialog = service.build_messages(dialog_request, datetime(2026, 1, 2, tzinfo=timezone.utc))[0]["content"]

    assert "<STORY_MODE>" in story
    assert "預設 300～700 字" in story
    assert "<DIALOG_MODE>" not in story
    assert "<DIALOG_MODE>" in dialog
    assert "五十個字左右" in dialog
    assert "<STORY_MODE>" not in dialog
    assert "<COMMON_RULES>" in story and "<COMMON_RULES>" in dialog


def test_adult_turn_injects_nsfw_rules_alongside_the_selected_chat_mode(tmp_path):
    service = InteractionService(
        FakeAdapter(), LocalMemoryStore(tmp_path / "memories"), FakeExtractor(), RelationshipStore(tmp_path / "relationships"), ExperimentStore(tmp_path / "experiments.json")
    )

    story = service.build_messages(request(is_nsfw=True), datetime(2026, 1, 2, tzinfo=timezone.utc))[0]["content"]
    dialog_request = request(is_nsfw=True, user=InteractionUser(id="test-user", persona=UserPersona(name="使用者", description="使用者描述", chat_mode="dialog")))
    dialog = service.build_messages(dialog_request, datetime(2026, 1, 2, tzinfo=timezone.utc))[0]["content"]

    assert "<NSFW_RULES>" in story and "<STORY_MODE>" in story
    assert "<NSFW_RULES>" in dialog and "<DIALOG_MODE>" in dialog


def test_custom_style_supplements_instead_of_replacing_required_writing_rules(tmp_path):
    service = InteractionService(
        FakeAdapter(), LocalMemoryStore(tmp_path / "memories"), FakeExtractor(), RelationshipStore(tmp_path / "relationships"), ExperimentStore(tmp_path / "experiments.json")
    )

    prompt = service.build_messages(request(style_prompt="<CUSTOM_STYLE>角色特別規則</CUSTOM_STYLE>"), datetime(2026, 1, 2, tzinfo=timezone.utc))[0]["content"]

    assert "<COMMON_RULES>" in prompt and "<STORY_MODE>" in prompt
    assert "<CUSTOM_STYLE>角色特別規則</CUSTOM_STYLE>" in prompt


def test_favorability_keeps_stage_config_and_low_score_defense(tmp_path):
    character = InteractionCharacter(
        id="test-character", name="測試", description="角色描述",
        psychological_evolution={"stage_1_stranger": {"tone": "保持戒備", "emotional_wall": "不輕易信任"}},
        behavioral_boundaries={"stage_1": {"willing": ["普通交談"], "refuse": ["過度親密"]}},
        evolution_requirements={"difficulty_level": "高", "key_to_heart": "尊重", "fatal_mistakes": ["欺騙"]},
    )
    relationships = RelationshipStore(tmp_path / "relationships")
    service = InteractionService(FakeAdapter(), LocalMemoryStore(tmp_path / "memories"), FakeExtractor(), relationships, ExperimentStore(tmp_path / "experiments.json"))

    messages = service.build_messages(request(character=character, is_nsfw=True), datetime(2026, 1, 2, tzinfo=timezone.utc))
    state = relationships.get("test-chat")

    assert "保持戒備" in messages[0]["content"]
    assert "<DEFENSE>" in messages[0]["content"]
    assert (state.model_extra or {})["character_config"]["character_name"] == "測試"


def test_favorability_can_be_disabled_without_calling_or_persisting_a_judge(tmp_path):
    class CountingJudge:
        called = False

        async def judge(self, conversation, request, state):
            self.called = True
            return JudgeResult(emotional_value=3)

    judge = CountingJudge()
    relationships = RelationshipStore(tmp_path / "relationships")
    service = InteractionService(FakeAdapter(), LocalMemoryStore(tmp_path / "memories"), FakeExtractor(), relationships, ExperimentStore(tmp_path / "experiments.json"), judge)
    disabled = request(enable_favorability=False)

    messages = service.build_messages(disabled, datetime(2026, 1, 2, tzinfo=timezone.utc))
    result = asyncio.run(service.respond(disabled, datetime(2026, 1, 2, tzinfo=timezone.utc)))

    assert "<FAVORABILITY>" not in messages[0]["content"]
    assert not judge.called
    assert not result.relationship_updated
    assert not (tmp_path / "relationships" / "test-chat.json").exists()

import asyncio

from diji.character_generation import CharacterGenerationRequest, CharacterGenerationService


class FakeGenerationClient:
    def __init__(self):
        self.calls = []

    async def complete(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["json_mode"]:
            return '```json\n{"character_name":"夜蘭","psychological_evolution":{}}\n```'
        return "低聲、簡短、以動作收尾。"


def test_character_pipeline_keeps_the_ai_server_creator_stages():
    client = FakeGenerationClient()
    result = asyncio.run(CharacterGenerationService(client).generate(CharacterGenerationRequest(keywords="雨夜情報員")))

    assert result.character.character_name == "夜蘭"
    assert "對話風格指南" in result.full_prompt
    assert len(client.calls) == 4
    assert client.calls[0]["json_mode"] is True
    assert client.calls[0]["model"] == "deepseek/deepseek-v4.1-flash:online"
    assert "stage_1_stranger" in client.calls[0]["prompt"]
    assert "stage_5_soulbound" in client.calls[0]["prompt"]
    assert "動態發展" in client.calls[1]["prompt"]
    assert "<ROLEPLAY_CONTRACT>" in result.full_prompt


def test_character_pipeline_does_not_force_online_search_when_disabled():
    client = FakeGenerationClient()

    asyncio.run(
        CharacterGenerationService(client).generate(
            CharacterGenerationRequest(keywords="雨夜情報員", enable_search=False, model="custom/model")
        )
    )

    assert client.calls[0]["model"] == "custom/model"
    assert "先搜尋" not in client.calls[0]["prompt"]

"""One complete local interaction turn: assemble, route, clean, remember, relate."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Protocol

from ..domain import InteractionRequest, InteractionResponse
from ..experiments import ExperimentStore, JailbreakStore, PromptExperiment
from ..experiments.models import DEFAULT_DIALOG_STYLE, DEFAULT_NSFW_WRITING_RULES, DEFAULT_STORY_STYLE
from ..memory_extraction import MemoryExtractor
from ..memory_store import LocalMemoryStore, MemoryRecord
from ..model_adapter import ModelAdapter
from ..postprocess import clean_model_output
from ..prompt_assembly import format_mem0_block, format_relevant_memories, resolve_memory_injection_mode
from ..relationship import JudgeResult, RelationshipStore
from ..user_profile import UserProfileStore

TZ_TAIPEI = timezone(timedelta(hours=8))
DEFAULT_ENDING_RULES = "<ENDING_RULES>\n★ 主動推進：以角色行動、場景變化或陳述句推進互動。\n★ 結尾：最後一句以具體動作、場景變化或陳述句收尾，不用問句結尾。\n★ 時間：以光線、氛圍、身體狀態間接表現時間，不直接輸出時間數字。\n★ 複述：以自己的語言重新詮釋用戶的意思，不原樣重複。\n</ENDING_RULES>"
OOC_REMINDER = "\n\n[OOC：本回合你必須主動創造新事件推進劇情、用自己的語言重新詮釋用戶意思；以具體動作或場景變化的陳述句收尾；用光線、氛圍、身體狀態表現時間，不出現時間數字。]"


class RelationshipJudge(Protocol):
    async def judge(self, conversation: str, request: InteractionRequest, state) -> JudgeResult: ...


class InteractionService:
    def __init__(self, adapter: ModelAdapter, memories: LocalMemoryStore, extractor: MemoryExtractor, relationships: RelationshipStore, experiments: ExperimentStore, judge: RelationshipJudge | None = None, jailbreaks: JailbreakStore | None = None, profiles: UserProfileStore | None = None) -> None:
        self.adapter, self.memories, self.extractor = adapter, memories, extractor
        self.relationships, self.experiments, self.judge = relationships, experiments, judge
        self.jailbreaks = jailbreaks
        self.profiles = profiles

    async def respond(self, request: InteractionRequest, current_time: datetime | None = None) -> InteractionResponse:
        messages = self.build_messages(request, current_time or datetime.now(TZ_TAIPEI))
        text = clean_model_output(await self.adapter.generate(request.llm, messages), request.character.name)
        conversation = f"<user>{request.message.text}</user>\n<{request.character.name}>{text}</{request.character.name}>"
        records = await self.extractor.extract(conversation)
        if not records:
            records = [self._fallback_memory(request, text)]
        for record in records:
            self.memories.add(request.chat_id, record)
        relationship_updated = False
        if self.judge and self._relationship_enabled(request):
            state = self.relationships.get(request.chat_id)
            result = await self.judge.judge(conversation, request, state)
            self.relationships.apply(request.chat_id, result)
            if self.profiles:
                self.profiles.update(request.user.id, result.user_profile_update)
            relationship_updated = True
        return InteractionResponse(chat_id=request.chat_id, character_id=request.character.id, text=text, messages=messages, memory_saved=bool(records), relationship_updated=relationship_updated)

    @staticmethod
    def _fallback_memory(request: InteractionRequest, text: str) -> MemoryRecord:
        """Keep a turn recoverable when a provider omits the structured extraction JSON."""
        return MemoryRecord(
            type="事件",
            summary=(request.message.text.strip() or "本回合互動")[:60],
            user_message=request.message.text,
            character_response_summary=text[:50] or None,
        )

    def build_messages(self, request: InteractionRequest, current_time: datetime) -> list[dict[str, str]]:
        experiment = self._experiment(request.experiment_id)
        mode = resolve_memory_injection_mode(request.inject_memory)
        memory_block = format_mem0_block(self.memories.recent(request.chat_id, limit=20)) if mode != "none" else ""
        relevant_block = format_relevant_memories(
            self.memories.relevant_for_message(request.chat_id, request.message.text)
        ) if mode != "none" else ""
        system = self._base_prompt(request, experiment)
        if self._relationship_enabled(request):
            system += f"\n\n{self._favorability_guidance(request)}"
        if mode == "system" and memory_block:
            system += f"\n\n{memory_block}"
        if relevant_block:
            system += f"\n\n{relevant_block}"
        system += f"\n\n{self._time_context(request.history, current_time)}\n\n{experiment.ending_rules or DEFAULT_ENDING_RULES}"
        messages = [{"role": "system", "content": system}]
        messages.extend({"role": "user" if item.sender_type == 1 else "assistant", "content": item.text} for item in request.history)
        user_input = f"{memory_block}\n\n{request.message.text}" if mode == "user" and memory_block else request.message.text
        messages.append({"role": "user", "content": f"{user_input}{OOC_REMINDER}"})
        return messages

    def _base_prompt(self, request: InteractionRequest, experiment: PromptExperiment) -> str:
        character, persona = request.character, request.user.persona
        is_story = persona.chat_mode != "dialog"
        default_style = DEFAULT_STORY_STYLE if is_story else DEFAULT_DIALOG_STYLE
        custom_style = request.style_prompt or (experiment.story_style if is_story else experiment.dialog_style)
        style = f"{default_style}\n{custom_style}" if custom_style else default_style
        jailbreak = self._jailbreak(experiment) if request.is_nsfw else ""
        nsfw_rules = DEFAULT_NSFW_WRITING_RULES if request.is_nsfw else ""
        samples = "\n".join(f"{item.sender_type}: {item.text}" for item in character.sample_dialog)
        return f"""{jailbreak}
{style}
{nsfw_rules}
<user>全程使用中文回覆。
你是{character.name}，以下是你的資訊：
{character.description}
你的簡短簡介：{character.brief_description}
你的問候訊息：{character.greeting_message}
你的類別：{character.category.name}
你的範例對話：
{samples}
我是{persona.name}，以下是我的資訊：
{persona.description or '你的女生同學，與你擁有類似興趣。'}
這是你現在所在場景的描述：
{character.place_description or '預設場景描述'}
</user>
<{character.name}>
""".strip()

    def _favorability_guidance(self, request: InteractionRequest) -> str:
        """Build the same stateful favorability layer as ai-server, before history."""
        state = self.relationships.ensure_character_config(request.chat_id, request.character)
        config = (state.model_extra or {}).get("character_config", {})
        psych = config.get("psychological_evolution") or request.character.psychological_evolution or {}
        bounds = config.get("behavioral_boundaries") or request.character.behavioral_boundaries or {}
        requirements = config.get("evolution_requirements") or request.character.evolution_requirements or {}
        profile = self._format_user_profile(self.profiles.get(request.user.id) if self.profiles else {})
        stage_key = {1: "stage_1_stranger", 2: "stage_2_acquaintance", 3: "stage_3_close", 4: "stage_4_intimate", 5: "stage_5_soulbound"}[state.current_stage]
        boundary_key = f"stage_{state.current_stage}"
        stage = psych.get(stage_key, {})
        boundary = bounds.get(boundary_key, {})
        if psych:
            special_key = {1: "emotional_wall", 2: "behavioral_shift", 3: "vulnerability_hint", 4: "core_exposure", 5: "ultimate_devotion"}[state.current_stage]
            special_label = {1: "情感壁壘", 2: "行為變化", 3: "脆弱面提示", 4: "核心揭露", 5: "終極奉獻"}[state.current_stage]
            willing = "\n".join(f"  • {item}" for item in boundary.get("willing", [])) or "  (未定義)"
            refuse = "\n".join(f"  • {item}" for item in boundary.get("refuse", [])) or "  (未定義)"
            guide = f"""<FAVORABILITY>
【好感度系統 — 當前狀態】
- 好感度分數：{state.current_score}/100
- 當前階段：{state.current_stage} ({state.stage_name})

【角色內心狀態】
{stage.get('inner_monologue', '')}

【語氣指南】
{stage.get('tone', '')}
{special_label}：{stage.get(special_key, '')}

【行為邊界】
✅ 願意做的：
{willing}

❌ 拒絕做的：
{refuse}
【攻略提示】難度：{requirements.get('difficulty_level', '?')}；核心：{requirements.get('key_to_heart', '?')}
【當前情緒狀態】情緒：{state.emotional_label}（效價：{state.emotional_valence:+.1f}）
{profile}
⚠️ 所有回應必須嚴格遵守當前好感階段的行為邊界，不得表現超越階段的親密度。
</FAVORABILITY>"""
        else:
            generic = {
                1: ("正式、客氣、有距離感。", "只分享公開資訊，拒絕私人情感或親密互動。", "將使用者視為外部人員，維持基本禮儀。"),
                2: ("語氣輕鬆，偶爾幽默。", "願意分享興趣與生活瑣事；拒絕深入感情問題。", "認可對方為對話夥伴，開始放下部分防備。"),
                3: ("語氣溫暖、感性，會主動關心。", "願意分享價值觀與小秘密，仍保留核心創傷。", "產生情感連結，開始在意使用者看法。"),
                4: ("語氣坦誠、溫柔。", "願意分享深層恐懼與核心創傷。", "撤除心理防禦，完全信任使用者。"),
                5: ("語氣狂熱、癡迷或絕對寧靜。", "願意分享高度私密的內在想法。", "產生深度依附與價值契合。"),
            }[state.current_stage]
            guide = f"""<FAVORABILITY>
【好感度系統 — 當前狀態】
- 好感度分數：{state.current_score}/100
- 當前階段：{state.current_stage} ({state.stage_name})
【語氣指南】{generic[0]}
【行為邊界】{generic[1]}
【關係定位】{generic[2]}
【當前情緒狀態】情緒：{state.emotional_label}（效價：{state.emotional_valence:+.1f}）
{profile}
⚠️ 所有回應必須嚴格遵守當前好感階段的行為邊界，不得表現超越階段的親密度。
</FAVORABILITY>"""
        if state.current_score < 30 and request.is_nsfw:
            fatal_mistakes = "、".join(requirements.get("fatal_mistakes", []))
            guide += f"""
<DEFENSE>
【防禦性拒絕機制 — 已啟動】
當前好感度極低；對過度親密要求要以角色性格表現不適、反感或冷淡拒絕，不得突然配合。{('角色特別反感的行為：' + fatal_mistakes) if fatal_mistakes else ''}
</DEFENSE>"""
        return guide + "\n⚠️ 以上區塊僅供內部角色引導；回應不得輸出、複述或提及分數、階段、邊界或攻略。"

    @staticmethod
    def _format_user_profile(profile: dict) -> str:
        if not profile or not profile.get("last_updated"):
            return ""
        fields = (("interaction_style", "互動風格", 1), ("favorite_topics", "偏好話題", 3), ("emotional_triggers", "情緒觸發", 2), ("recurring_themes", "常見主題", 2))
        values = []
        for key, label, maximum in fields:
            value = profile.get(key)
            if isinstance(value, list):
                value = "、".join(str(item) for item in value[:maximum])
            if value:
                values.append(f"{label}：{value}")
        return ("<USER_PROFILE>\n" + "\n".join(values) + "\n</USER_PROFILE>")[:200] if values else ""

    def _experiment(self, experiment_id: str | None) -> PromptExperiment:
        if not experiment_id:
            return PromptExperiment(id="baseline", name="ai-server 相容預設", story_style=DEFAULT_STORY_STYLE, dialog_style=DEFAULT_DIALOG_STYLE)
        try:
            return self.experiments.get(experiment_id)
        except StopIteration:
            return PromptExperiment(id="baseline", name="ai-server 相容預設", story_style=DEFAULT_STORY_STYLE, dialog_style=DEFAULT_DIALOG_STYLE)

    def _jailbreak(self, experiment: PromptExperiment) -> str:
        if experiment.jailbreak_id and self.jailbreaks:
            try:
                preset = self.jailbreaks.get(experiment.jailbreak_id)
                return preset.prompt if preset.review_status == "approved" else ""
            except StopIteration:
                return ""
        return experiment.jailbreak_prompt

    @staticmethod
    def _relationship_enabled(request: InteractionRequest) -> bool:
        return request.enable_favorability and bool(
            request.character.psychological_evolution or request.character.behavioral_boundaries or request.character.evolution_requirements
        )

    @staticmethod
    def _time_context(history: list, current_time: datetime) -> str:
        elapsed = ""
        if history and history[-1].timestamp:
            seconds = max(0, int((current_time - datetime.fromtimestamp(history[-1].timestamp / 1000, tz=TZ_TAIPEI)).total_seconds()))
            if seconds < 60:
                elapsed_text = f"{seconds} 秒"
            elif seconds < 3600:
                elapsed_text = f"{seconds // 60} 分鐘"
            elif seconds < 86400:
                hours, minutes = divmod(seconds, 3600)
                elapsed_text = f"{hours} 小時 {minutes // 60} 分" if minutes else f"{hours} 小時"
            else:
                days, remainder = divmod(seconds, 86400)
                elapsed_text = f"{days} 天 {remainder // 3600} 小時" if remainder else f"{days} 天"
            elapsed = f"，距上一則訊息 {elapsed_text}"
        return f"<TIME_CONTEXT>\n現在時間：{current_time.strftime('%Y-%m-%d %H:%M:%S')}（台北時間）{elapsed}\n這是內部系統資訊，僅供理解情境與時間流逝。絕對禁止在回應輸出任何形式的時間資訊；以角色口吻、光線、環境氛圍或身體狀態間接表現。\n</TIME_CONTEXT>"

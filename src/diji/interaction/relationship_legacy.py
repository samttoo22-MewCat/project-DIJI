"""
好感度 LLM Judge 評分模組 (Favorability Judge)
透過 LLM 對每輪對話進行四維度評分，決定好感度變動。

四維度：
- emotional_value (Ev)：情緒價值 — 用戶是否展現同理心、情緒支持
- self_disclosure (Sd)：自我揭露 — 用戶是否主動分享個人資訊
- boundary_respect (Br)：邊界尊重 — 用戶的要求是否符合當前好感階段
- value_alignment (Va)：價值契合 — 用戶言行是否符合角色的核心動機

每維度範圍：-5 ~ +3
"""

import json
import re
import traceback
from typing import Dict, Optional
from openai import AsyncOpenAI
from dotenv import load_dotenv
import os

load_dotenv()

# 階段定義
STAGES = {
    1: {"name": "陌生", "range": (0, 39), "description": "戒備防禦，維持基本禮儀以掩飾不安"},
    2: {"name": "熟識", "range": (40, 79), "description": "放鬆觀察，認可對方為對話夥伴"},
    3: {"name": "親近", "range": (80, 119), "description": "情感投射，產生情感連結"},
    4: {"name": "親密", "range": (120, 179), "description": "脆弱揭露，撤除心理防禦"},
    5: {"name": "靈魂", "range": (180, 9999), "description": "完全依附，價值契合與用戶融合"},
}

# 階段升級門檻
STAGE_THRESHOLDS = {
    "1_to_2": 40,
    "2_to_3": 80,
    "3_to_4": 120,
    "4_to_5": 180,
}

# 關鍵事件類型定義
KEY_EVENTS = {
    "1_to_2": {
        "type": "持續的尊重",
        "description": "多次對話中未發生邊界侵犯",
    },
    "2_to_3": {
        "type": "共同興趣發現",
        "description": "確認雙方有某種價值觀契合",
    },
    "3_to_4": {
        "type": "情緒共振",
        "description": "用戶在角色情緒低落時提供實質安慰",
    },
    "4_to_5": {
        "type": "危機守護",
        "description": "用戶在模擬情境中守護了角色的尊嚴或安全",
    },
}


class FavorabilityJudge:
    """LLM Judge 好感度評分器"""

    def __init__(self):
        print(f"\n🔧 [FavorabilityJudge.__init__] 初始化好感度評分器...")
        api_key = os.getenv("OPENROUTER_API_KEY", "")
        print(f"   API Key: {'已設定 (' + api_key[:8] + '...)' if api_key else '⚠️ 未設定!'}")
        self.client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
        print(f"   ✅ FavorabilityJudge 初始化完成")

    async def judge_conversation(
        self,
        conversation: str,
        character_description: str,
        current_score: int,
        current_stage: int,
    ) -> Dict:
        """
        對一輪對話進行好感度評分

        Args:
            conversation: 當前對話內容（包含 user 和 character 的訊息）
            character_description: 角色設定描述
            current_score: 當前好感度分數
            current_stage: 當前好感階段 (1-5)

        Returns:
            評分結果字典，包含四維度分數與關鍵事件判定
        """
        stage_info = STAGES.get(current_stage, STAGES[1])
        next_stage = current_stage + 1
        next_key_event = KEY_EVENTS.get(f"{current_stage}_to_{next_stage}")

        # 構建關鍵事件判定指引
        key_event_instruction = ""
        if next_key_event:
            key_event_instruction = f"""
8. **關鍵事件判定**：請判斷此輪對話是否發生了以下關鍵事件：
   - 事件類型：「{next_key_event['type']}」
   - 事件描述：{next_key_event['description']}
   - 若發生，請在 `key_event_detected` 填入事件類型名稱；若未發生，填入 null。
"""

        prompt = f"""你是一位角色扮演品質評估專家。請分析以下對話，從角色的角度評估用戶的互動品質。

## 角色設定
{character_description}

## 當前好感狀態
- 分數：{current_score}/100
- 階段：{current_stage} ({stage_info['name']}) — {stage_info['description']}

## 本輪對話
{conversation}

## 評分指引

請從以下四個維度評分，每個維度的分數範圍為 **-5 到 +3**：

1. **emotional_value（情緒價值）**：用戶是否展現同理心、情緒支持或正面情緒回饋。
   - -5：冷漠無情、忽視角色情緒
   - 0：普通互動
   - +3：深度共情、精準的情緒支持

2. **self_disclosure（自我揭露）**：用戶是否主動分享個人資訊或秘密，誘發「互惠揭露」。
   - -5：完全封閉
   - 0：普通交流
   - +3：深層分享、建立信任

3. **boundary_respect（邊界尊重）**：用戶的要求是否符合當前好感階段。
   - -5：嚴重侵犯邊界（如在階段1強行要求親密行為）
   - 0：正常互動
   - +3：得體禮儀、展現尊重

4. **value_alignment（價值契合）**：用戶言行是否符合角色的核心動機與信念。
   - -5：嚴重理念衝突
   - 0：中性
   - +3：高度觀念契合

5. **reasoning**：簡短說明評分理由（50字以內）。

6. **conversation_depth（對話深度）**：評估本輪用戶發言的深度等級：
   - 0：閒聊、打招呼、無實質內容
   - 1：分享個人感受、日常生活事件
   - 2：討論核心價值觀、人生選擇、具衝突性的取捨
   - 3：極深度自我揭露，涉及創傷、最隱密的秘密、根本性的自我認同
   請填入 0、1、2 或 3。

7. **fatal_mistake**：依據角色設定，判斷本輪用戶是否犯下角色永遠無法原諒的致命失誤。填入 true 或 false。

{key_event_instruction}

9. **new_emotional_valence**：此輪對話結束後，角色情緒的整體效價，範圍 -1.0 到 +1.0（負值=負面，正值=正面）。

10. **new_emotional_label**：從以下 8 種標籤中選出最符合當前角色心情的一種：高興、平靜、委屈、憤怒、感動、受傷、害羞、期待。

11. **user_profile_update**：根據本輪對話對「這個用戶」的行為模式做出觀察。若本輪無有意義的新觀察，填入 null。若有，提供以下欄位（只填有把握的，其餘省略）：
    - interaction_style：用戶的互動風格（簡短描述）
    - favorite_topics：用戶喜好的話題列表
    - emotional_triggers：讓用戶情緒波動的觸發因素列表
    - recurring_themes：用戶反覆提及的主題列表

## 輸出格式（JSON）
```json
{{
  "emotional_value": <int>,
  "self_disclosure": <int>,
  "boundary_respect": <int>,
  "value_alignment": <int>,
  "total": <int>,
  "reasoning": "<評分理由>",
  "key_event_detected": null 或 "<事件類型>",
  "conversation_depth": <0|1|2|3>,
  "fatal_mistake": <true|false>,
  "new_emotional_valence": <-1.0 到 +1.0>,
  "new_emotional_label": "<高興|平靜|委屈|憤怒|感動|受傷|害羞|期待>",
  "user_profile_update": null 或 {{"interaction_style": "...", "favorite_topics": ["..."], "emotional_triggers": ["..."], "recurring_themes": ["..."]}}
}}
```

請嚴格按照 JSON 格式輸出，不要包含其他內容。"""

        try:
            print(f"\n{'='*60}")
            print(f"💕 [FavorabilityJudge.judge_conversation] 開始評估對話...")
            print(f"   當前分數: {current_score}, 階段: {current_stage} ({stage_info['name']})")
            print(f"   角色描述長度: {len(character_description)} 字元")
            print(f"   對話內容長度: {len(conversation)} 字元")
            print(f"   對話前 100 字: {conversation[:100]}...")
            print(f"   Prompt 總長度: {len(prompt)} 字元")
            print(f"   使用模型: google/gemini-2.5-flash (temp=0.2)")
            print(f"{'='*60}")
            print(f"📤 [FavorabilityJudge] 發送評分請求到 OpenRouter...")

            response = await self.client.chat.completions.create(
                model="google/gemini-2.5-flash",
                temperature=0.2,  # 低溫度確保評分穩定
                max_tokens=700,
                top_p=0.5,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )

            result_text = response.choices[0].message.content.strip()
            print(f"📥 [FavorabilityJudge] 收到回應，長度: {len(result_text)} 字元")
            print(f"📥 [FavorabilityJudge] 原始回應內容: {result_text[:300]}")

            # 解析 JSON
            json_match = re.search(r"\{.*\}", result_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(0))

                # 驗證並修正每個維度的範圍
                for dim in ["emotional_value", "self_disclosure", "boundary_respect", "value_alignment"]:
                    if dim not in result:
                        result[dim] = 0
                    result[dim] = max(-5, min(3, int(result[dim])))

                # 重新計算 total
                result["total"] = (
                    result["emotional_value"]
                    + result["self_disclosure"]
                    + result["boundary_respect"]
                    + result["value_alignment"]
                )

                # 確保有 reasoning
                if "reasoning" not in result:
                    result["reasoning"] = "評分完成"

                # 確保有 key_event_detected
                if "key_event_detected" not in result:
                    result["key_event_detected"] = None

                # 驗證 conversation_depth
                if "conversation_depth" not in result:
                    result["conversation_depth"] = 1
                result["conversation_depth"] = max(0, min(3, int(result["conversation_depth"])))

                # 驗證 fatal_mistake
                if "fatal_mistake" not in result:
                    result["fatal_mistake"] = False
                result["fatal_mistake"] = bool(result["fatal_mistake"])

                # 驗證情緒效價
                if "new_emotional_valence" not in result:
                    result["new_emotional_valence"] = 0.0
                result["new_emotional_valence"] = max(-1.0, min(1.0, float(result["new_emotional_valence"])))

                # 驗證情緒標籤
                _VALID_LABELS = {"高興", "平靜", "委屈", "憤怒", "感動", "受傷", "害羞", "期待"}
                if result.get("new_emotional_label") not in _VALID_LABELS:
                    result["new_emotional_label"] = "平靜"

                # 驗證 user_profile_update
                if "user_profile_update" not in result:
                    result["user_profile_update"] = None
                elif result["user_profile_update"] is not None:
                    if not isinstance(result["user_profile_update"], dict):
                        result["user_profile_update"] = None
                    else:
                        _valid_keys = {"interaction_style", "favorite_topics", "emotional_triggers", "recurring_themes"}
                        result["user_profile_update"] = {
                            k: v for k, v in result["user_profile_update"].items()
                            if k in _valid_keys and v
                        } or None

                print(f"\n✅ 好感度評分結果：")
                print(f"   情緒價值 (Ev): {result['emotional_value']:+d}")
                print(f"   自我揭露 (Sd): {result['self_disclosure']:+d}")
                print(f"   邊界尊重 (Br): {result['boundary_respect']:+d}")
                print(f"   價值契合 (Va): {result['value_alignment']:+d}")
                print(f"   ─────────────")
                print(f"   總計: {result['total']:+d}")
                print(f"   理由: {result['reasoning']}")
                if result["key_event_detected"]:
                    print(f"   🎯 關鍵事件: {result['key_event_detected']}")
                print(f"{'='*60}\n")

                return result

            print(f"⚠️ [FavorabilityJudge] 無法解析 Judge 回應，找不到 JSON")
            print(f"   原始內容: {result_text}")
            return self._default_result()

        except Exception as e:
            print(f"❌ 好感度評分失敗: {str(e)}")
            print(traceback.format_exc())
            return self._default_result()

    def _default_result(self) -> Dict:
        """返回預設評分結果（用於錯誤情況）"""
        return {
            "emotional_value": 0,
            "self_disclosure": 0,
            "boundary_respect": 0,
            "value_alignment": 0,
            "total": 0,
            "reasoning": "評分失敗，使用預設值",
            "key_event_detected": None,
            "conversation_depth": 1,
            "fatal_mistake": False,
            "new_emotional_valence": 0.0,
            "new_emotional_label": "平靜",
            "user_profile_update": None,
        }

    @staticmethod
    def get_stage_for_score(score: int) -> int:
        """根據分數返回對應的階段"""
        score = max(0, score)
        for stage_num, stage_info in STAGES.items():
            low, high = stage_info["range"]
            if low <= score <= high:
                return stage_num
        return 5  # 分數 >= 85

    @staticmethod
    def get_stage_info(stage: int) -> Dict:
        """取得階段資訊"""
        return STAGES.get(stage, STAGES[1])

    @staticmethod
    def check_stage_upgrade(
        current_stage: int,
        new_score: int,
        key_event_detected: Optional[str],
    ) -> bool:
        print(f"\n🔍 [check_stage_upgrade] 檢查升級條件...")
        print(f"   current_stage={current_stage}, new_score={new_score}, key_event={key_event_detected}")
        """
        檢查是否滿足升級條件：分值達標 + 關鍵事件

        Args:
            current_stage: 當前階段
            new_score: 新分數
            key_event_detected: 本輪偵測到的關鍵事件

        Returns:
            是否升級
        """
        if current_stage >= 5:
            return False

        threshold_key = f"{current_stage}_to_{current_stage + 1}"
        threshold = STAGE_THRESHOLDS.get(threshold_key)

        if threshold is None:
            return False

        # 分值必須達標
        if new_score < threshold:
            return False

        # 階段 1→2 只需分值達標（持續的尊重由分數累積體現）
        if current_stage == 1:
            return True

        # 其他階段需要關鍵事件
        expected_event = KEY_EVENTS.get(threshold_key)
        if expected_event and key_event_detected:
            return key_event_detected == expected_event["type"]

        return False

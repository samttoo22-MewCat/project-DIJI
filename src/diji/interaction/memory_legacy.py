import json
import os
from datetime import datetime, timezone, timedelta

TZ_TAIPEI = timezone(timedelta(hours=8))
import re
from typing import Dict, List, Optional
from openai import AsyncOpenAI
from dotenv import load_dotenv
import traceback
# from google.genai import types  # 暂时注释掉，避免模块缺失问题

from .relationship_legacy import (
    FavorabilityJudge,
    STAGES,
    STAGE_THRESHOLDS,
)

# 載入環境變數
load_dotenv()

class Mem0Creator:
    def __init__(self, storage_dir: str = "memories"):
        """
        初始化記憶濃縮器
        
        Args:
            storage_dir: 儲存記憶的目錄
        """
        # 获取当前文件所在的目录
        base_dir = os.path.dirname(__file__)
        self.storage_dir = os.path.join(base_dir, storage_dir)
        if not os.path.exists(self.storage_dir):
            os.makedirs(self.storage_dir)
            
        # 好感度存儲目錄
        self.favorability_dir = os.path.join(base_dir, "favorability")
        if not os.path.exists(self.favorability_dir):
            os.makedirs(self.favorability_dir)

        # User Profile 存儲目錄
        self.user_profiles_dir = os.path.join(base_dir, "user_profiles")
        os.makedirs(self.user_profiles_dir, exist_ok=True)

        # 初始化好感度評分器
        self.favorability_judge = FavorabilityJudge()

        # 初始化OpenAI用戶端
        self.client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY", "")
        )
    
    async def _extract_key_events(self, conversation: str) -> List[Dict]:
        """
        使用LLM從對話中提取關鍵事件
        
        Args:
            conversation: 對話內容
            
        Returns:
            關鍵事件列表
        """
        # 建構提示詞
        prompt = f"""請分析以下對話，提取重要資訊。重點關注：
1. 用戶和角色之間的重要互動
2. 情感表達和態度變化
3. 場景和環境的改變
4. 重要的約定或承諾
5. 角色的性格特徵展現

請以JSON格式輸出，包含以下欄位：
- timestamp: 時間戳記（YYYY-MM-DD HH:MM格式）
- type: 記憶類型（事實|偏好|事件|標記）
- summary: 單句摘要（不超過60字，不含人名以外敏感資訊）
- user_message: 用戶訊息
- key_points: 關鍵點列表（例如：情感表達、場景變化、重要約定等，不超過5個）
- character_response_summary: 角色回覆的簡短總結（50字以內）
- keywords: 關鍵字字典，包含分類的關鍵詞（例如：{{"物品": "手作飾品", "地點": "後山", "活動": "散步", "情緒": "開心"}}）
  可用的分類：物品、地點、活動、情緒、人物、時間、事件、其他

對話內容：
{conversation}"""

        try:
            print(f"\n{'='*60}")
            print(f"🧠 [記憶提取] 開始分析對話...")
            print(f"{'='*60}")
            
            # 呼叫LLM
            response = await self.client.chat.completions.create(
                model="google/gemini-2.5-flash",
                temperature=0.3,
                max_tokens=1000,
                top_p=0.6,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )

            # 解析回應
            result = response.choices[0].message.content.strip()
            print(f"📥 LLM 原始回應長度: {len(result)} 字元")

            # 提取JSON部分
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                event = json.loads(json_match.group(0))
                print(f"\n✅ 成功提取記憶事件")
                print(f"   → 類型: {event.get('type', 'N/A')}")
                print(f"   → 摘要: {event.get('summary', 'N/A')[:50]}...")
                print(f"   → 用戶訊息: {event.get('user_message', 'N/A')[:50]}...")
                event['timestamp'] = datetime.now(TZ_TAIPEI).strftime("%Y-%m-%d %H:%M")
                if 'type' not in event or event['type'] not in ['事實', '偏好', '事件', '標記']:
                    event['type'] = 'event'
                if 'summary' not in event:
                    if event.get('character_response_summary'):
                        event['summary'] = event['character_response_summary'][:60]
                    elif event.get('user_message'):
                        event['summary'] = event['user_message'][:60]
                    else:
                        event['summary'] = "對話記憶"
                if len(event['summary']) > 60:
                    event['summary'] = event['summary'][:60]
                if 'keywords' not in event or not isinstance(event['keywords'], dict):
                    print(f"   ⚠️  未提取到關鍵字，設為空字典")
                    event['keywords'] = {}
                else:
                    kw_str = ', '.join([f"{k}:{v}" for k, v in event['keywords'].items()])
                    print(f"   → 關鍵字 ({len(event['keywords'])} 個): {kw_str}")
                print(f"{'='*60}\n")
                return [event]

            print(f"⚠️  無法從回應中提取 JSON")
            print(f"原始回應: {result[:200]}...")
            print(f"{'='*60}\n")
            return []
            
        except Exception as e:
            error_event = {
                "timestamp": datetime.now(TZ_TAIPEI).strftime("%Y-%m-%d %H:%M"),
                "type": "標記",
                "summary": f"錯誤：LLM提取事件失敗",
                "error": True,
                "error_message": f"LLM提取關鍵事件時出錯：{str(e)}",
                "traceback": traceback.format_exc()
            }
            print(error_event["error_message"])
            print(error_event["traceback"])
            return [error_event]
    
    def _validate_and_fix_memory(self, memory: dict) -> bool:
        """
        驗證並修復記憶格式
        
        Args:
            memory: 記憶字典
            
        Returns:
            是否為有效記憶（修復後）
        """
        try:
            # 確保有 timestamp 欄位
            if 'timestamp' not in memory:
                memory['timestamp'] = datetime.now(TZ_TAIPEI).strftime("%Y-%m-%d %H:%M")
            
            # 確保有 type 欄位
            if 'type' not in memory:
                if memory.get('error'):
                    memory['type'] = '標記'
                elif memory.get('key_points'):
                    memory['type'] = '事件'
                else:
                    memory['type'] = '事實'
            
            # 確保有 summary 欄位
            if 'summary' not in memory:
                if memory.get('character_response_summary'):
                    memory['summary'] = memory['character_response_summary'][:60]
                elif memory.get('user_message'):
                    memory['summary'] = memory['user_message'][:60]
                elif memory.get('error_message'):
                    memory['summary'] = f"錯誤：{memory['error_message'][:50]}"
                else:
                    memory['summary'] = "記憶摘要"
            
            # 確保 summary 不超過60字並移除敏感資訊
            if len(memory['summary']) > 60:
                memory['summary'] = memory['summary'][:60]
            
            return True
            
        except Exception as e:
            print(f"修復記憶時出錯：{str(e)}")
            return False
    
    def create_event(self, conversation_id: str, event_type: str, summary: str, 
                    additional_data: dict = None) -> dict:
        """
        創建事件記憶
        
        Args:
            conversation_id: 對話ID
            event_type: 事件類型 (事實|偏好|事件|標記)
            summary: 事件摘要（<60字）
            additional_data: 額外資料
            
        Returns:
            格式化的事件記憶
        """
        event = {
            "timestamp": datetime.now(TZ_TAIPEI).strftime("%Y-%m-%d %H:%M"),
            "type": event_type if event_type in ['事實', '偏好', '事件', '標記'] else '事實',
            "summary": summary[:60] if summary else "事件摘要"
        }
        
        # 添加額外資料
        if additional_data:
            event.update(additional_data)
        
        return event
    
    def get_favorability(self, conversation_id: str) -> Dict:
        """
        取得當前好感度狀態
        
        Args:
            conversation_id: 對話ID
            
        Returns:
            好感度狀態字典
        """
        print(f"\n📚 [get_favorability] 讀取好感度...")
        print(f"   conversation_id: {conversation_id}")
        fav_file = os.path.join(self.favorability_dir, f"{conversation_id}.json")
        print(f"   檔案路徑: {fav_file}")
        print(f"   檔案存在: {os.path.exists(fav_file)}")
        
        if os.path.exists(fav_file):
            try:
                with open(fav_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                print(f"   ✅ 讀取成功: 分數={data.get('current_score', '?')}, 階段={data.get('current_stage', '?')} ({data.get('stage_name', '?')})")
                print(f"   歷史記錄數: {len(data.get('history', []))}")
                return data
            except Exception as e:
                print(f"   ⚠️ 讀取好感度檔案失敗: {str(e)}")
        
        # 返回初始狀態
        print(f"   🆕 返回初始狀態 (分數=0, 階段=1 陌生)")
        return {
            "current_score": 0,
            "current_stage": 1,
            "stage_name": "陌生",
            "emotional_valence": 0.0,
            "emotional_label": "平靜",
            "last_updated": None,
            "history": [],
            "stage_thresholds": STAGE_THRESHOLDS,
        }

    def _save_favorability(self, conversation_id: str, fav_data: Dict) -> None:
        """
        寫入好感度狀態到檔案
        """
        fav_file = os.path.join(self.favorability_dir, f"{conversation_id}.json")
        print(f"\n💾 [_save_favorability] 寫入好感度檔案...")
        print(f"   檔案: {fav_file}")
        print(f"   分數: {fav_data.get('current_score')}, 階段: {fav_data.get('current_stage')} ({fav_data.get('stage_name')})")
        with open(fav_file, 'w', encoding='utf-8') as f:
            json.dump(fav_data, f, ensure_ascii=False, indent=2)
        print(f"   ✅ 寫入成功")

    def get_user_profile(self, user_id: str) -> Dict:
        """取得用戶 Profile，不存在則返回初始結構"""
        profile_file = os.path.join(self.user_profiles_dir, f"{user_id}.json")
        if os.path.exists(profile_file):
            try:
                with open(profile_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ 讀取 user profile 失敗: {e}")
        return {
            "user_id": user_id,
            "last_updated": None,
            "interaction_style": "",
            "favorite_topics": [],
            "emotional_triggers": [],
            "recurring_themes": [],
        }

    def update_user_profile(self, user_id: str, update: Dict) -> None:
        """合併更新用戶 Profile（list 欄位採 union 去重，string 欄位直接覆蓋）"""
        if not update:
            return
        profile = self.get_user_profile(user_id)
        if update.get("interaction_style"):
            profile["interaction_style"] = update["interaction_style"]
        for list_field in ["favorite_topics", "emotional_triggers", "recurring_themes"]:
            if update.get(list_field):
                existing = set(profile.get(list_field, []))
                existing.update(update[list_field])
                profile[list_field] = list(existing)[:10]
        profile["last_updated"] = datetime.now(TZ_TAIPEI).strftime("%Y-%m-%d %H:%M")
        profile_file = os.path.join(self.user_profiles_dir, f"{user_id}.json")
        with open(profile_file, 'w', encoding='utf-8') as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
        print(f"✅ user profile 已更新: {user_id}")

    async def update_favorability(
        self,
        conversation_id: str,
        conversation: str,
        character_description: str = "",
        user_id: str = "",
    ) -> Dict:
        """
        更新好感度：調用 LLM Judge 評分並更新狀態

        Args:
            conversation_id: 對話ID
            conversation: 本輪對話內容
            character_description: 角色設定描述
            user_id: 用戶ID（用於更新 user profile）

        Returns:
            更新後的好感度狀態
        """
        print(f"\n{'='*60}")
        print(f"💕 [update_favorability] 開始更新好感度...")
        print(f"   conversation_id: {conversation_id}")
        print(f"   對話內容長度: {len(conversation)} 字元")
        print(f"   角色描述長度: {len(character_description)} 字元")
        print(f"{'='*60}")
        
        # 取得當前好感度
        fav_data = self.get_favorability(conversation_id)
        current_score = fav_data["current_score"]
        current_stage = fav_data["current_stage"]
        print(f"   當前狀態: 分數={current_score}, 階段={current_stage}")

        # 調用 LLM Judge 評分
        print(f"\n🧠 [update_favorability] 調用 LLM Judge 評分...")
        score_result = await self.favorability_judge.judge_conversation(
            conversation=conversation,
            character_description=character_description,
            current_score=current_score,
            current_stage=current_stage,
        )
        print(f"   評分結果: {json.dumps(score_result, ensure_ascii=False)}")

        # 套用對話深度乘數
        _DEPTH_MULTIPLIERS = {0: 0.5, 1: 1.0, 2: 1.5, 3: 2.0}
        depth = score_result.get("conversation_depth", 1)
        adjusted_total = round(score_result["total"] * _DEPTH_MULTIPLIERS.get(depth, 1.0))
        if score_result.get("fatal_mistake", False):
            adjusted_total -= 8
        print(f"   深度乘數: depth={depth}, ×{_DEPTH_MULTIPLIERS.get(depth, 1.0)}, fatal={score_result.get('fatal_mistake')}")
        print(f"   分數調整: raw={score_result['total']} → adjusted={adjusted_total}")

        # 計算新分數（clamp 0~100）
        score_before = current_score
        new_score = max(0, min(100, current_score + adjusted_total))
        stage_before = current_stage
        print(f"   分數變化: {score_before} + ({adjusted_total}) = {new_score}")

        # 檢查是否升級
        key_event = score_result.get("key_event_detected")
        print(f"\n🔍 [update_favorability] 檢查升級條件...")
        print(f"   key_event: {key_event}")
        should_upgrade = FavorabilityJudge.check_stage_upgrade(
            current_stage, new_score, key_event
        )
        print(f"   should_upgrade: {should_upgrade}")

        if should_upgrade:
            new_stage = current_stage + 1
            print(f"   🎉 升級! {current_stage} → {new_stage}")
        else:
            # 即使分數夠了但沒有關鍵事件，也不降級
            new_stage = current_stage
            print(f"   • 維持階段 {current_stage}")

        # 取得新階段資訊
        stage_info = FavorabilityJudge.get_stage_info(new_stage)

        # 構建歷史記錄
        history_entry = {
            "timestamp": datetime.now(TZ_TAIPEI).strftime("%Y-%m-%d %H:%M"),
            "score_delta": {
                "emotional_value": score_result["emotional_value"],
                "self_disclosure": score_result["self_disclosure"],
                "boundary_respect": score_result["boundary_respect"],
                "value_alignment": score_result["value_alignment"],
                "total": score_result["total"],
                "conversation_depth": depth,
                "adjusted_total": adjusted_total,
                "fatal_mistake": score_result.get("fatal_mistake", False),
            },
            "reasoning": score_result.get("reasoning", ""),
            "score_before": score_before,
            "score_after": new_score,
            "stage_before": stage_before,
            "stage_after": new_stage,
            "key_event_detected": key_event,
            "emotional_label_after": score_result.get("new_emotional_label", "平靜"),
        }

        # 更新狀態
        fav_data["current_score"] = new_score
        fav_data["current_stage"] = new_stage
        fav_data["stage_name"] = stage_info["name"]
        fav_data["emotional_valence"] = score_result.get("new_emotional_valence", fav_data.get("emotional_valence", 0.0))
        fav_data["emotional_label"] = score_result.get("new_emotional_label", fav_data.get("emotional_label", "平靜"))
        fav_data["last_updated"] = datetime.now(TZ_TAIPEI).strftime("%Y-%m-%d %H:%M")
        fav_data["history"].append(history_entry)

        # 寫入檔案
        self._save_favorability(conversation_id, fav_data)

        # 更新 user profile
        if user_id and score_result.get("user_profile_update"):
            self.update_user_profile(user_id, score_result["user_profile_update"])

        # 日誌輸出
        if should_upgrade:
            print(f"🎉 好感度升級！{STAGES[stage_before]['name']} → {stage_info['name']}")
        print(f"💕 好感度更新: {score_before} → {new_score} (階段 {new_stage}: {stage_info['name']})")

        return fav_data

    async def save_memory(self, conversation_id: str, conversation: str, **kwargs) -> Optional[Dict]:
        """
        儲存對話記憶，同時更新好感度

        Args:
            conversation_id: 對話ID
            conversation: 對話內容
            **kwargs: 額外的會話資訊

        Returns:
            好感度更新結果 (Dict) 或 None 如果沒有提取到事件
        """
        print(f"\n{'='*60}")
        print(f"💾 [記憶保存] 開始保存記憶...")
        print(f"   對話 ID: {conversation_id}")
        print(f"   對話內容長度: {len(conversation)} 字元")
        print(f"{'='*60}")
        
        # 提取關鍵事件
        events = await self._extract_key_events(conversation)
        
        if not events:
            print(f"⚠️  未提取到任何事件，不保存記憶")
            print(f"{'='*60}\n")
            return None
        
        print(f"✅ 提取到 {len(events)} 個事件")
        
        # 建構記憶檔案路徑
        memory_file = os.path.join(self.storage_dir, f"{conversation_id}.json")
        
        # 讀取現有記憶（如果存在）
        existing_memories = []
        if os.path.exists(memory_file):
            with open(memory_file, 'r', encoding='utf-8') as f:
                existing_memories = json.load(f)
            print(f"📂 讀取現有記憶: {len(existing_memories)} 條")
        else:
            print(f"📝 創建新記憶檔案")
        
        # 新增新記憶
        existing_memories.extend(events)

        # 儲存更新後的記憶
        with open(memory_file, 'w', encoding='utf-8') as f:
            json.dump(existing_memories, f, ensure_ascii=False, indent=2)
        
        print(f"💾 保存成功！總記憶數: {len(existing_memories)} 條")
        print(f"   檔案路徑: {memory_file}")
        print(f"{'='*60}\n")

        # === 好感度更新 ===
        # 若該角色未啟用好感度系統，直接略過評分（不呼叫 LLM Judge、不寫好感度檔案）
        if not kwargs.get("enable_favorability", True):
            print(f"\nℹ️ [save_memory] 好感度系統未啟用，略過評分流程")
            return None

        print(f"\n{'='*60}")
        print(f"💕 [save_memory] 開始好感度更新流程...")
        print(f"   kwargs keys: {list(kwargs.keys())}")
        character_description = kwargs.get("character_description", "")
        user_id = kwargs.get("user_id", "")
        print(f"   character_description 長度: {len(character_description)} 字元")
        print(f"   character_description 前 80 字: {character_description[:80]}..." if character_description else "   character_description: (空)")
        print(f"   user_id: {user_id}")
        print(f"{'='*60}")
        try:
            fav_result = await self.update_favorability(
                conversation_id=conversation_id,
                conversation=conversation,
                character_description=character_description,
                user_id=user_id,
            )
            print(f"\n✅ [save_memory] 好感度更新完成!")
            print(f"   分數: {fav_result['current_score']}, 階段: {fav_result['current_stage']} ({fav_result['stage_name']})")
            print(f"   歷史記錄數: {len(fav_result.get('history', []))}")
            return fav_result
        except Exception as e:
            print(f"⚠️ [save_memory] 好感度更新失敗（不影響記憶保存）: {str(e)}")
            traceback.print_exc()
            return None
    
    def get_memory_summary(self, conversation_id: str) -> str:
        """
        取得記憶摘要
        """
        memory_file = os.path.join(self.storage_dir, f"{conversation_id}.json")
        
        if not os.path.exists(memory_file):
            return ""
            
        with open(memory_file, 'r', encoding='utf-8') as f:
            memories = json.load(f)
            
        # 生成摘要
        summary = "重要記憶：\n"
        for memory in memories[-20:]:
            summary += f"用戶：{memory.get('user_message', '')}\n"
            summary += f"\n時間：{memory.get('timestamp', '')}\n"
            if memory.get('key_points'):
                summary += f"關鍵點：{', '.join(memory['key_points'])}\n"
            # 這裡改成 character_response_summary
            if memory.get('character_response_summary'):
                summary += f"角色回應摘要：{memory['character_response_summary']}\n"
            
            # 不再存取不存在的 key
            # summary += f"角色：{memory['character_message']}\n"
            
        return summary

    def get_recent_memories(self, conversation_id: str, count: int = 5) -> list[dict]:
        """
        取得最近的記憶（完整版本）
        
        Args:
            conversation_id: 對話ID
            count: 需要取得的記憶數量
            
        Returns:
            最近的記憶列表（包含所有欄位）
        """
        memory_file = os.path.join(self.storage_dir, f"{conversation_id}.json")
        
        if not os.path.exists(memory_file):
            return []
            
        try:
            with open(memory_file, 'r', encoding='utf-8') as f:
                memories = json.load(f)
            
            # 篩選並補充必要欄位
            valid_memories = []
            for memory in memories[-count:]:
                if self._validate_and_fix_memory(memory):
                    valid_memories.append(memory)
            return valid_memories
            
        except Exception as e:
            print(f"讀取記憶檔案時出錯：{str(e)}")
            return []

    def search_memories_by_text(self, conversation_id: str, query: str, count: int = 5) -> list[dict]:
        """
        以查詢文字中出現的詞搜尋記憶。
        命中條件：memory 的任一 keyword 值出現在 query 中。
        返回最新的 count 筆，按 timestamp 降序排列。
        """
        memory_file = os.path.join(self.storage_dir, f"{conversation_id}.json")
        if not os.path.exists(memory_file):
            return []
        try:
            with open(memory_file, 'r', encoding='utf-8') as f:
                memories = json.load(f)
        except Exception:
            return []

        matched = []
        for m in memories:
            kws = m.get("keywords", {})
            if isinstance(kws, dict) and any(v and v in query for v in kws.values()):
                matched.append(m)

        def _ts(m):
            try:
                return datetime.strptime(m.get("timestamp", ""), "%Y-%m-%d %H:%M")
            except Exception:
                return datetime.min

        matched.sort(key=_ts, reverse=True)
        return matched[:count]

    def delete_memory_file(self, conversation_id: str) -> None:
        """
        刪除指定對話ID的記憶檔案
        """
        memory_file = os.path.join(self.storage_dir, f"{conversation_id}.json")
        if os.path.exists(memory_file):
            os.remove(memory_file)

    def delete_favorability_file(self, conversation_id: str) -> None:
        """
        刪除指定對話ID的好感度檔案
        """
        fav_file = os.path.join(self.favorability_dir, f"{conversation_id}.json")
        if os.path.exists(fav_file):
            os.remove(fav_file)
    
    def search_memories_by_categories(self, conversation_id: str, search_categories: List[str], 
                                     max_results: int = 5) -> List[Dict]:
        """
        根據分類搜尋記憶，返回最接近現在時間的匹配結果
        
        Args:
            conversation_id: 對話ID
            search_categories: 搜尋分類列表，例如 ["物品", "地點"]
            max_results: 最多返回的結果數量
            
        Returns:
            匹配的記憶列表，按時間倒序排列
        """
        print(f"\n{'='*60}")
        print(f"🔍 [記憶搜尋] 開始搜尋...")
        print(f"   對話 ID: {conversation_id}")
        print(f"   搜尋分類: {search_categories}")
        print(f"   最多返回: {max_results} 個結果")
        print(f"{'='*60}")
        
        memory_file = os.path.join(self.storage_dir, f"{conversation_id}.json")
        
        if not os.path.exists(memory_file):
            print(f"⚠️  記憶檔案不存在: {memory_file}")
            print(f"{'='*60}\n")
            return []
        
        try:
            with open(memory_file, 'r', encoding='utf-8') as f:
                memories = json.load(f)
            
            print(f"📂 讀取記憶檔案成功，共 {len(memories)} 條記憶")
            
            # 搜尋匹配的記憶
            matched_memories = []
            invalid_count = 0
            no_keywords_count = 0
            
            for idx, memory in enumerate(memories):
                # 確保記憶格式正確
                if not self._validate_and_fix_memory(memory):
                    invalid_count += 1
                    continue
                
                # 取得記憶中的關鍵字（兼容舊格式列表和新格式字典）
                memory_keywords = memory.get('keywords', {})
                if isinstance(memory_keywords, list):
                    # 舊格式：列表轉為字典，將每個關鍵字都放入"其他"分類
                    if memory_keywords:
                        memory_keywords = {"其他": ", ".join(memory_keywords)}
                    else:
                        memory_keywords = {}
                
                if not memory_keywords:
                    no_keywords_count += 1
                
                # 計算匹配分數
                match_score = 0
                matched_categories = {}
                match_details = []
                
                # 遍歷搜尋分類列表
                for search_category in search_categories:
                    # 檢查記憶是否包含此分類
                    if search_category in memory_keywords:
                        mem_value = memory_keywords[search_category]
                        match_score += 3
                        matched_categories[search_category] = mem_value
                        match_details.append(f"分類匹配: {search_category} -> '{mem_value}' (+3)")
                
                # 如果有匹配，加入結果
                if match_score > 0:
                    matched_memories.append({
                        'memory': memory,
                        'score': match_score,
                        'matched_categories': matched_categories,
                        'match_details': match_details
                    })
                    print(f"\n   ✅ 記憶 #{idx+1} 匹配 (分數: {match_score})")
                    print(f"      時間: {memory.get('timestamp', 'N/A')}")
                    print(f"      摘要: {memory.get('summary', 'N/A')[:50]}...")
                    for detail in match_details:
                        print(f"      → {detail}")
            
            print(f"\n📊 搜尋統計:")
            print(f"   總記憶數: {len(memories)}")
            print(f"   無效記憶數: {invalid_count}")
            print(f"   無關鍵字記憶數: {no_keywords_count}")
            print(f"   匹配記憶數: {len(matched_memories)}")
            
            # 只按時間排序（取最近的記憶）
            matched_memories.sort(key=lambda x: x['memory'].get('timestamp', ''), reverse=True)
            
            # 返回最近的 N 個結果（不考慮分數）
            results = []
            for item in matched_memories[:max_results]:
                result = item['memory'].copy()
                result['match_score'] = item['score']
                result['matched_categories'] = item['matched_categories']
                results.append(result)
            
            print(f"\n✅ 返回前 {len(results)} 個結果")
            for i, res in enumerate(results, 1):
                print(f"   {i}. [{res.get('timestamp')}] 分數: {res['match_score']}")
                print(f"      {res.get('summary', 'N/A')[:50]}...")
            
            print(f"{'='*60}\n")
            return results
            
        except Exception as e:
            print(f"❌ 搜尋記憶時出錯：{str(e)}")
            traceback.print_exc()
            print(f"{'='*60}\n")
            return []

"""Apply explicit model-proposed leaf edits without replacing unrelated character fields."""
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .service import CharacterGenerationResult, CharacterGenerationService
from ..local_catalog import CharacterSpec


class DraftRevisionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=0)
    model: str = Field(min_length=1, max_length=256)
    instruction: str = Field(min_length=1, max_length=4000)
    is_nsfw: bool = False
    base_revision: int | None = Field(default=None,ge=0)


class Change(BaseModel):
    model_config = ConfigDict(extra='forbid')
    path: list[str] = Field(min_length=1, max_length=20)
    value: Any


class Proposal(BaseModel):
    model_config = ConfigDict(extra='forbid')
    summary: str = Field(min_length=1, max_length=2000)
    changes: list[Change] = Field(min_length=1, max_length=40)


def revision_prompt(draft, instruction, jailbreak, is_nsfw=False):
    content = draft.model_dump(exclude={'full_prompt','generation_id','revision'})
    return f'''依照使用者要求修改以下角色草稿，使用繁體中文。只修改必要欄位，保留其他設定。
內容設定：{'包含色情內容的成人虛構' if is_nsfw else '非成人，不主動加入色情設定'}。
相關設定（例如風格、簡介）若因本次修改產生矛盾，也要一併調整。
不得重生整份角色、刪除欄位或變更未被要求的細節。
嚴格輸出 JSON：{{"summary":"簡短說明實際修改", "changes":[{{"path":["character","backstory"],"value":"修改後的完整背景內容"}}]}}
summary 請使用白話繁體中文，不要出現 JSON key、path 或程式欄位名稱。
path 只能指向草稿既有的末端欄位，不可指向整個物件。字串陣列視為單一末端欄位；value 必須提供該欄位的完整新內容。
可修改 character 下的既有末端欄位，以及 style_guide、description_for_app、brief_description、category、hobbies。
不可修改 generation_id、revision 或 full_prompt。新增資訊請放到適合的既有欄位。
使用者要求：{instruction}
目前草稿：{json.dumps(content, ensure_ascii=False)}
{jailbreak}'''


def apply_proposal(draft: CharacterGenerationResult, raw: str):
    proposal = Proposal.model_validate_json(CharacterGenerationService._json_object(raw))
    data = draft.model_dump()
    seen = set()
    for change in proposal.changes:
        path = tuple(change.path)
        if path in seen or path[0] not in {'character','style_guide','description_for_app','brief_description','category','hobbies'}:
            raise ValueError('模型回傳重複或不允許的修改欄位')
        seen.add(path)
        parent = data
        for key in path[:-1]:
            if not isinstance(parent,dict) or key not in parent:
                raise ValueError('模型修改了不存在的欄位')
            parent = parent[key]
        if not isinstance(parent,dict) or path[-1] not in parent:
            raise ValueError('模型修改了不存在的欄位')
        previous = parent[path[-1]]
        if isinstance(previous,dict) or (isinstance(previous,list) and not all(isinstance(v,str) for v in previous)):
            raise ValueError('模型必須修改末端欄位，不可取代整份設定')
        value = change.value
        valid = (isinstance(value,list) and all(isinstance(v,str) for v in value)) if isinstance(previous,list) else (type(value) is type(previous) if previous is not None else isinstance(value,(str,int,float,bool)) or value is None)
        if not valid:
            raise ValueError('模型回傳的欄位型態不符')
        parent[path[-1]] = value
    result = CharacterGenerationResult.model_validate(data)
    result.full_prompt = CharacterGenerationService._full_prompt(result.character,result.style_guide)
    CharacterSpec(id=result.generation_id, name=result.character.character_name,
        premise=result.description_for_app or result.brief_description, voice=(result.style_guide or '依角色設定互動。')[:2000],
        profile=result.character.model_dump(), style_guide=result.style_guide, full_prompt=result.full_prompt)
    return result, proposal.summary, [change.path for change in proposal.changes]

"""Response cleanup stages preserved from ai-server's interaction pipeline."""

from __future__ import annotations

import re

try:
    import opencc
except ImportError:  # Keep local-only startup possible when the optional converter is absent.
    opencc = None


def strip_mem_leak(text: str) -> str:
    text = re.sub(r"</?MEM>", "", text)
    return re.sub(r"(?m)^\s*-\s*\[\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\].*$", "", text).strip()


def strip_timestamps(text: str) -> str:
    return re.sub(r"(?m)^\s*(?:\[)?\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?(?:\])?\s*", "", text)


def fix_literal_newlines(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text.replace("\\n", "\n"))


def remove_tags(text: str) -> str:
    for tag in ("reflection", "TIME_CONTEXT", "REMINDER", "ENDING_RULES", "MEM", "RELEVANT_MEM", "FAVORABILITY", "USER_PROFILE"):
        text = re.sub(rf"<{tag}>.*?</{tag}>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"\[OOC[：:][^\]]*\]", "", text, flags=re.IGNORECASE)
    return re.sub(r"<.*?>", "", text).strip()


def strip_meta_commentary(text: str) -> str:
    patterns = (
        r"用戶(?:詢問|問了|說了|表示|提到)", r"我以.{1,10}(?:身份|的角度|的立場)",
        r"這(?:符合|體現|反映|展現|呈現|維持)", r"在這(?:個)?(?:回應|回覆|對話|場景)",
        r"作為.{1,10}(?:我|角色)", r"根據(?:角色|設定|好感度|當前)",
        r"本(?:次|輪)(?:回應|回覆|對話)", r"(?:角色|我的)(?:設定|特質|性格|行為)",
    )
    match = re.search(r"(?:^|\n)\s*(?:" + "|".join(patterns) + r")", text, flags=re.MULTILINE)
    return text[:match.start()].rstrip() if match and text[:match.start()].strip() else text


def strip_character_prefix(text: str, character_name: str) -> str:
    return text.split(f"{character_name}:")[-1].strip()


def clean_model_output(text: str, character_name: str = "") -> str:
    """Keep ai-server's cleanup order as a single reusable pipeline."""
    if character_name:
        text = strip_character_prefix(text, character_name)
    text = strip_timestamps(text)
    text = strip_timestamps(text)
    if opencc:
        text = opencc.OpenCC("s2tw").convert(text)
    text = strip_meta_commentary(fix_literal_newlines(remove_tags(strip_mem_leak(text))))
    text = text.replace("**", "").replace(",", "，").replace("!", "！").replace("?", "？").strip()
    return text or "他沒有說話。"

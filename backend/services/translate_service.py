"""Translate a transcribed voice answer into the traveler's chosen UI language."""

from __future__ import annotations

import json

from llm.deepseek_client import chat_json

TARGET_LANGUAGE_NAMES = {"en": "English", "zh": "Chinese"}

TRANSLATE_PROMPT = (
    "Translate the traveler's spoken trip-planning answer into {target}. "
    "Preserve the meaning exactly: never add, remove, or guess a fact, date, "
    "number, currency, or place name. If the text is already in {target}, "
    'return it unchanged. Return ONLY JSON: {{"translation": "..."}}.'
)


def translate_text(text: str, target_language_code: str) -> str:
    """Best-effort translation via DeepSeek. Returns the original text on any failure."""
    target = TARGET_LANGUAGE_NAMES.get(target_language_code, "English")
    prompt = TRANSLATE_PROMPT.format(target=target)
    try:
        result = chat_json(prompt, json.dumps({"text": text}, ensure_ascii=False), 0.2)
    except Exception:
        return text
    translated = str((result or {}).get("translation") or "").strip()
    return translated or text

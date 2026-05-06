from __future__ import annotations

import re
from hashlib import sha256
from html import unescape

from app.config import load_style_guide

WHITESPACE_RE = re.compile(r"\s+")
PAYWALL_HINTS = (
    "로그인 후 이용",
    "회원 전용",
    "구독 후",
    "유료회원",
    "paywall",
    "subscribe to continue",
    "sign in to continue",
)


def clean_text(text: str | None) -> str:
    if not text:
        return ""
    text = unescape(text)
    text = text.replace("\u200b", " ").replace("\ufeff", " ")
    return WHITESPACE_RE.sub(" ", text).strip()


def make_excerpt(text: str | None, max_chars: int | None = None) -> str:
    guide = load_style_guide()
    limit = max_chars or guide.max_excerpt_chars
    cleaned = clean_text(text)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def stable_hash(text: str | None) -> str:
    normalized = clean_text(text).lower()
    return sha256(normalized.encode("utf-8")).hexdigest()


def contains_paywall_hint(text: str | None) -> bool:
    lowered = clean_text(text).lower()
    return any(hint.lower() in lowered for hint in PAYWALL_HINTS)


def find_forbidden_phrases(text: str) -> list[str]:
    guide = load_style_guide()
    return [phrase for phrase in guide.forbidden_phrases if phrase and phrase in text]


def find_ai_phrases(text: str) -> list[str]:
    guide = load_style_guide()
    return [phrase for phrase in guide.ai_phrases if phrase and phrase in text]


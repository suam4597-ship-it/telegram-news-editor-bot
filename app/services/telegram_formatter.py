from __future__ import annotations

import html
import re

from app.schemas.editorial import FormatResult, MarketBrief

TELEGRAM_EDITORIAL_LIMIT = 3500
HASHTAG_RE = re.compile(r"#[0-9A-Za-z가-힣_-]+")


def format_telegram_html(brief: MarketBrief) -> str:
    result = format_telegram_html_result(brief)
    if not result.passed:
        raise ValueError(result.reason or "telegram formatting failed")
    return result.telegram_html


def format_telegram_html_result(brief: MarketBrief, *, limit: int = TELEGRAM_EDITORIAL_LIMIT) -> FormatResult:
    if not brief.source_url.strip():
        raise ValueError("source_url is required")

    current = brief
    message = _render(current)
    if len(message) <= limit:
        return FormatResult(telegram_html=message, passed=True)

    for field_name in ("korean_context", "risk_note", "why_it_matters", "what_to_watch"):
        current = _shorten_field(current, field_name)
        message = _render(current)
        if len(message) <= limit:
            return FormatResult(telegram_html=message, passed=True)

    return FormatResult(
        telegram_html=message[:limit].rstrip(),
        passed=False,
        needs_review=True,
        reason="telegram_message_too_long",
    )


def _render(brief: MarketBrief) -> str:
    optional_blocks = []
    if brief.korean_context:
        optional_blocks.append(_escape(brief.korean_context))
    if brief.risk_note:
        optional_blocks.append(_escape(brief.risk_note))
    optional_text = f"\n\n{'\n\n'.join(optional_blocks)}" if optional_blocks else ""
    hashtags = " ".join(_normalize_hashtags(brief.hashtags))
    return (
        f"<b>{_escape(brief.short_title)}</b>\n\n"
        f"{_escape(brief.one_line_summary)}\n\n"
        f"• <b>무슨 일</b>: {_escape(brief.what_happened)}\n"
        f"• <b>시사점</b>: {_escape(brief.why_it_matters)}\n"
        f"• <b>체크포인트</b>: {_escape(brief.what_to_watch)}"
        f"{optional_text}\n\n"
        f'출처: <a href="{_escape(brief.source_url)}">{_escape(brief.source_name)}</a>\n'
        "※ 정보 제공 목적이며 투자 권유가 아닙니다.\n\n"
        f"{hashtags}"
    )


def _shorten_field(brief: MarketBrief, field_name: str) -> MarketBrief:
    value = getattr(brief, field_name)
    if value is None:
        return brief
    if field_name in {"korean_context", "risk_note"}:
        return brief.model_copy(update={field_name: None})
    text = str(value)
    shortened = text[:220].rsplit(" ", 1)[0].rstrip()
    if not shortened:
        shortened = text[:120].rstrip()
    return brief.model_copy(update={field_name: f"{shortened}…"})


def _escape(value: str | None) -> str:
    return html.escape(value or "", quote=True)


def _normalize_hashtags(hashtags: list[str]) -> list[str]:
    normalized = []
    for tag in hashtags[:4]:
        cleaned = tag.strip()
        if not cleaned:
            continue
        cleaned = cleaned if cleaned.startswith("#") else f"#{cleaned}"
        cleaned = "".join(char for char in cleaned if char.isalnum() or char in {"#", "_", "-"})
        if cleaned != "#" and cleaned not in normalized:
            normalized.append(cleaned)
    return normalized[:4]

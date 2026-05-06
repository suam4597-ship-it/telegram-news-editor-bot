from __future__ import annotations

import html

from app.config import load_style_guide


def escape_html(value: str | None) -> str:
    return html.escape(value or "", quote=True)


def truncate_telegram_text(text: str, max_chars: int | None = None) -> str:
    guide = load_style_guide()
    limit = max_chars or guide.max_telegram_chars
    if len(text) <= limit:
        return text
    suffix = "\n\n…"
    return text[: limit - len(suffix)].rstrip() + suffix


def format_source_link(source_name: str, source_url: str) -> str:
    return f'<a href="{escape_html(source_url)}">{escape_html(source_name)}</a>'


def ensure_disclaimer(text: str) -> str:
    guide = load_style_guide()
    if guide.disclaimer in text:
        return text
    return f"{text.rstrip()}\n{escape_html(guide.disclaimer)}"


POST_TYPE_LABELS = {
    "short_link": "짧은 링크형",
    "editorial_brief": "본문 설명형",
    "market_brief": "시장 브리핑형",
    "data_brief": "데이터형",
    "breaking": "속보형",
}


def format_admin_review(
    summary_id: int,
    telegram_text: str,
    source_name: str,
    source_url: str,
    post_type: str | None = None,
    metadata: dict[str, str] | None = None,
) -> str:
    metadata = metadata or {}
    post_type_label = POST_TYPE_LABELS.get(post_type or "", post_type or "auto")
    meta_lines = [
        _meta_line("수집", metadata.get("source_path")),
        _meta_line("레인", metadata.get("investment_lane")),
        _meta_line("관련", metadata.get("related")),
        _meta_line("리스크", metadata.get("risk_flags")),
    ]
    meta_text = "\n".join(line for line in meta_lines if line)
    body = (
        f"<b>검토 #{summary_id} · {escape_html(post_type_label)}</b>\n"
        f"{meta_text}\n"
        f"원문: {format_source_link(source_name, source_url)}\n\n"
        f"<b>발행 미리보기</b>\n"
        f"{telegram_text}"
    )
    return truncate_telegram_text(body)


def inline_review_keyboard(summary_id: int) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "승인", "callback_data": f"approve:{summary_id}"},
                {"text": "반려", "callback_data": f"reject:{summary_id}"},
            ],
            [
                {"text": "짧게", "callback_data": f"shorten:{summary_id}"},
                {"text": "길게", "callback_data": f"expand:{summary_id}"},
            ],
            [
                {"text": "재작성", "callback_data": f"rewrite:{summary_id}"},
                {"text": "수정 후 승인", "callback_data": f"edit:{summary_id}"},
            ],
        ]
    }


def _meta_line(label: str, value: str | None) -> str:
    if not value:
        return ""
    return f"{label}: {escape_html(value)}"

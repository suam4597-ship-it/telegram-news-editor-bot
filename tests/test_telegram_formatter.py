from __future__ import annotations

import pytest

from app.schemas.editorial import MarketBrief
from app.services.telegram_formatter import TELEGRAM_EDITORIAL_LIMIT, format_telegram_html, format_telegram_html_result


def brief(**updates) -> MarketBrief:
    data = {
        "short_title": "미국 소비, 아직 식지 않았습니다",
        "one_line_summary": "미국 소비 지표가 예상보다 견조하게 나왔습니다.",
        "what_happened": "최근 발표된 소비 지표가 시장 예상보다 강하게 나왔습니다.",
        "why_it_matters": "소비가 버티면 경기 둔화 우려는 줄지만, 빠른 금리 인하 명분도 약해질 수 있습니다.",
        "what_to_watch": "다음 물가 지표와 연준 인사 발언을 확인해야 합니다.",
        "korean_context": "국내에서는 원/달러 환율과 성장주 할인율 부담으로 연결될 수 있습니다.",
        "risk_note": None,
        "source_name": "Example Financial News",
        "source_url": "https://example.com/article?x=1&y=2",
        "hashtags": ["#미국경제", "#금리", "#소비지표"],
        "category": "macro",
        "importance_score": 80,
    }
    data.update(updates)
    return MarketBrief(**data)


def test_formatter_escapes_html_sensitive_text() -> None:
    message = format_telegram_html(
        brief(
            short_title="Nvidia <b>beats</b> & guides higher",
            source_name="Example <script>alert(1)</script>",
        )
    )

    assert "&lt;b&gt;beats&lt;/b&gt;" in message
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in message
    assert "<script>" not in message
    assert 'href="https://example.com/article?x=1&amp;y=2"' in message


def test_formatter_includes_source_disclaimer_and_hashtags() -> None:
    message = format_telegram_html(brief())

    assert '출처: <a href="https://example.com/article?x=1&amp;y=2">Example Financial News</a>' in message
    assert "※ 정보 제공 목적이며 투자 권유가 아닙니다." in message
    assert "#미국경제 #금리 #소비지표" in message


def test_formatter_shortens_overlength_message() -> None:
    long_text = "길게 씁니다. " * 500
    result = format_telegram_html_result(
        brief(
            korean_context=long_text,
            risk_note=long_text,
            why_it_matters=long_text,
            what_to_watch=long_text,
        )
    )

    assert result.passed is True
    assert len(result.telegram_html) <= TELEGRAM_EDITORIAL_LIMIT


def test_formatter_marks_still_overlength_as_needs_review() -> None:
    long_text = "A" * 5000
    result = format_telegram_html_result(
        brief(
            short_title="A" * 80,
            one_line_summary=long_text,
            what_happened=long_text,
            why_it_matters=long_text,
            what_to_watch=long_text,
            korean_context=long_text,
            risk_note=long_text,
        )
    )

    assert result.passed is False
    assert result.needs_review is True


def test_market_brief_missing_source_url_fails_validation() -> None:
    with pytest.raises(ValueError):
        brief(source_url="")


def test_market_brief_hashtag_count_is_validated() -> None:
    with pytest.raises(ValueError):
        brief(hashtags=["#하나"])

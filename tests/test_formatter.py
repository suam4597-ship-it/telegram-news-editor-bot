from app.publisher.formatter import escape_html, format_admin_review, inline_review_keyboard, truncate_telegram_text


def test_escape_html() -> None:
    assert escape_html('<a href="x">') == "&lt;a href=&quot;x&quot;&gt;"


def test_inline_review_keyboard_callback_data() -> None:
    keyboard = inline_review_keyboard(42)
    callbacks = [button["callback_data"] for row in keyboard["inline_keyboard"] for button in row]
    assert callbacks == ["approve:42", "reject:42", "shorten:42", "expand:42", "rewrite:42", "edit:42"]


def test_truncate_telegram_text() -> None:
    assert truncate_telegram_text("abcdef", max_chars=5) == "ab\n\n…"


def test_format_admin_review_is_scannable() -> None:
    text = format_admin_review(
        42,
        "<b>초안 제목</b>\n\n본문",
        "Naver",
        "https://example.com/a",
        "editorial_brief",
        metadata={
            "source_path": "Naver",
            "investment_lane": "국내 실적",
            "related": "현대차, 자동차",
            "risk_flags": "없음",
        },
    )
    assert "<b>검토 #42 · 본문 설명형</b>" in text
    assert "수집: Naver" in text
    assert "<b>발행 미리보기</b>" in text

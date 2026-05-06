from app.parsers.text_cleaner import clean_text, contains_paywall_hint, make_excerpt, stable_hash


def test_clean_text_normalizes_whitespace() -> None:
    assert clean_text("  A&nbsp;\n\n B \u200b C  ") == "A B C"


def test_make_excerpt_limits_length() -> None:
    assert make_excerpt("가" * 20, max_chars=10) == "가" * 9 + "…"


def test_stable_hash_is_case_and_space_insensitive() -> None:
    assert stable_hash(" Hello  World ") == stable_hash("hello world")


def test_contains_paywall_hint() -> None:
    assert contains_paywall_hint("로그인 후 이용 가능한 기사입니다.")


from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.llm.client import OpenAIResponsesClient
from app.schemas.editorial import (
    ArticleFacts,
    ArticleInput,
    ArticleTopic,
    BriefValidation,
    FactType,
    KeyFact,
    MarketBrief,
    MarketContext,
    PublishDecision,
    RecommendedAction,
)
from app.services.editorial_pipeline import ForeignEditorialPipeline

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "foreign_articles"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_foreign_pipeline_returns_korean_telegram_draft() -> None:
    pipeline = ForeignEditorialPipeline(client=OpenAIResponsesClient(api_key=""))
    draft = await pipeline.create_draft(load_fixture("earnings_big_tech.json"))

    assert draft.facts.article_topic == ArticleTopic.EARNINGS
    assert draft.brief.source_url == "https://example.com/earnings/nvidia"
    assert draft.telegram_html is not None
    assert "<b>" in draft.telegram_html
    assert "출처:" in draft.telegram_html
    assert "※ 정보 제공 목적이며 투자 권유가 아닙니다." in draft.telegram_html
    assert 2 <= len(draft.brief.hashtags) <= 4


@pytest.mark.asyncio
async def test_golden_fixtures_validate_against_article_facts() -> None:
    pipeline = ForeignEditorialPipeline(client=OpenAIResponsesClient(api_key=""))
    for fixture_name in ("macro_us_cpi.json", "earnings_big_tech.json", "central_bank_fed_speech.json"):
        article = pipeline.normalize_foreign_article(load_fixture(fixture_name))
        facts = await pipeline.extract_article_facts(article)
        brief = await pipeline.write_korean_market_brief(facts)
        validation = await pipeline.validate_market_brief(facts, brief)

        assert isinstance(facts, ArticleFacts)
        assert isinstance(brief, MarketBrief)
        assert isinstance(validation, BriefValidation)


def test_article_input_missing_source_url_fails_validation() -> None:
    with pytest.raises(ValidationError):
        ArticleInput.model_validate(load_fixture("invalid_no_source_url.json"))


def test_invalid_enum_values_fail_validation() -> None:
    valid = load_fixture("macro_us_cpi.json")
    data = {
        "source_name": valid["source_name"],
        "source_url": valid["source_url"],
        "original_language": "en",
        "published_at": valid["published_at"],
        "article_title": valid["title"],
        "article_topic": "not_a_topic",
        "main_event": "event",
        "key_facts": [],
        "entities": {},
        "market_context": {
            "affected_asset_classes": ["stocks"],
            "affected_sectors": [],
            "possible_direction": "unclear",
            "confidence": 0.5,
        },
        "uncertainty": [],
        "source_limitations": [],
        "should_publish": True,
        "review_reason": None,
    }
    with pytest.raises(ValidationError):
        ArticleFacts.model_validate(data)


@pytest.mark.asyncio
async def test_validator_catches_unsupported_numbers() -> None:
    pipeline = ForeignEditorialPipeline(client=OpenAIResponsesClient(api_key=""))
    facts = ArticleFacts(
        source_name="Example",
        source_url="https://example.com/a",
        original_language="en",
        published_at=None,
        article_title="Revenue rose",
        article_topic=ArticleTopic.EARNINGS,
        main_event="Revenue rose 3%.",
        key_facts=[KeyFact(fact="Revenue rose 3%.", evidence="Revenue rose 3%.", fact_type=FactType.NUMBER)],
        market_context=MarketContext(affected_asset_classes=["stocks"], affected_sectors=["AI"], confidence=0.7),
    )
    brief = MarketBrief(
        short_title="실적 개선",
        one_line_summary="매출이 개선됐습니다.",
        what_happened="매출은 3% 증가했습니다.",
        why_it_matters="마진과 수요 기대에 영향을 줄 수 있습니다.",
        what_to_watch="다음 가이던스를 봐야 합니다.",
        korean_context=None,
        risk_note="영업이익 99% 증가는 원문에 없습니다.",
        source_name="Example",
        source_url="https://example.com/a",
        hashtags=["#실적", "#AI"],
        category="earnings",
        importance_score=70,
    )
    validation = await pipeline.validate_market_brief(facts, brief)

    assert "99%" in validation.number_mismatches
    assert validation.passed is False


@pytest.mark.asyncio
async def test_validator_catches_investment_advice_phrases() -> None:
    pipeline = ForeignEditorialPipeline(client=OpenAIResponsesClient(api_key=""))
    article = pipeline.normalize_foreign_article(load_fixture("invalid_investment_advice.json"))
    facts = await pipeline.extract_article_facts(article)
    brief = await pipeline.write_korean_market_brief(facts)
    bad_brief = brief.model_copy(update={"why_it_matters": "지금 사야 할 매수 기회입니다."})
    validation = await pipeline.validate_market_brief(facts, bad_brief)

    assert validation.investment_advice_flags
    assert validation.recommended_action == RecommendedAction.REJECT


@pytest.mark.asyncio
async def test_uncertain_single_source_routes_to_admin_review() -> None:
    pipeline = ForeignEditorialPipeline(client=OpenAIResponsesClient(api_key=""))
    article = ArticleInput(
        source_name="Example",
        source_url="https://example.com/rumor",
        title="Sources said export controls may change",
        text_excerpt="Sources said the rule may change, but the report is unconfirmed.",
    )
    draft = await pipeline.create_draft(article, auto_publish_enabled=True)

    assert draft.publish_decision.decision == PublishDecision.ADMIN_REVIEW

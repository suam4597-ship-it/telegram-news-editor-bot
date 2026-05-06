from __future__ import annotations

from app.schemas.editorial import (
    ArticleFacts,
    ArticleTopic,
    BriefValidation,
    FactType,
    KeyFact,
    MarketBrief,
    PublishDecision,
    RecommendedAction,
)
from app.services.publish_decision import decide_publish


def facts(**updates) -> ArticleFacts:
    data = {
        "source_name": "Example",
        "source_url": "https://example.com/a",
        "original_language": "en",
        "published_at": None,
        "article_title": "Nvidia earnings beat estimates",
        "article_topic": ArticleTopic.EARNINGS,
        "main_event": "Nvidia revenue beat estimates.",
        "key_facts": [KeyFact(fact="Revenue beat estimates.", evidence="Revenue beat estimates.", fact_type=FactType.EVENT)],
        "should_publish": True,
    }
    data.update(updates)
    return ArticleFacts(**data)


def brief(**updates) -> MarketBrief:
    data = {
        "short_title": "Nvidia 실적 개선",
        "one_line_summary": "Nvidia 실적이 예상치를 웃돌았습니다.",
        "what_happened": "매출이 예상보다 좋았습니다.",
        "why_it_matters": "AI 수요 기대가 업종 심리에 영향을 줄 수 있습니다.",
        "what_to_watch": "다음 가이던스를 확인해야 합니다.",
        "source_name": "Example",
        "source_url": "https://example.com/a",
        "hashtags": ["#실적", "#AI"],
        "category": "earnings",
        "importance_score": 82,
    }
    data.update(updates)
    return MarketBrief(**data)


def validation(**updates) -> BriefValidation:
    data = {
        "passed": True,
        "factuality_issues": [],
        "unsupported_claims": [],
        "number_mismatches": [],
        "investment_advice_flags": [],
        "hype_language_flags": [],
        "copyright_risk_flags": [],
        "formatting_issues": [],
        "recommended_action": RecommendedAction.PUBLISH,
        "revised_brief": None,
    }
    data.update(updates)
    return BriefValidation(**data)


def test_publish_decision_auto_publish() -> None:
    result = decide_publish(facts(), brief(), validation(), auto_publish_enabled=True)

    assert result.decision == PublishDecision.AUTO_PUBLISH


def test_publish_decision_admin_review_for_mid_importance() -> None:
    result = decide_publish(facts(), brief(importance_score=60), validation(), auto_publish_enabled=True)

    assert result.decision == PublishDecision.ADMIN_REVIEW


def test_publish_decision_admin_review_for_geopolitics() -> None:
    result = decide_publish(
        facts(article_topic=ArticleTopic.GEOPOLITICS),
        brief(category="geopolitics"),
        validation(),
        auto_publish_enabled=True,
    )

    assert result.decision == PublishDecision.ADMIN_REVIEW


def test_publish_decision_rejects_investment_advice() -> None:
    result = decide_publish(
        facts(),
        brief(),
        validation(passed=False, investment_advice_flags=["매수"], recommended_action=RecommendedAction.REJECT),
        auto_publish_enabled=True,
    )

    assert result.decision == PublishDecision.REJECT

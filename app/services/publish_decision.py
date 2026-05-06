from __future__ import annotations

from app.schemas.editorial import (
    ArticleFacts,
    ArticleTopic,
    BriefValidation,
    MarketBrief,
    PublishDecision,
    PublishDecisionResult,
    RecommendedAction,
)

HIGH_RISK_TOPICS = {
    ArticleTopic.GEOPOLITICS,
    ArticleTopic.CRYPTO_REGULATION,
}
RUMOR_MARKERS = {"rumor", "unconfirmed", "single-source", "single source", "확인 필요", "단일 보도"}
SMALL_CAP_HYPE_MARKERS = {"small-cap hype", "급등", "penny stock", "theme stock"}


def decide_publish(
    facts: ArticleFacts,
    brief: MarketBrief,
    validation: BriefValidation,
    *,
    auto_publish_enabled: bool = False,
) -> PublishDecisionResult:
    if not facts.source_url or not brief.source_url:
        return PublishDecisionResult(decision=PublishDecision.REJECT, reason="missing_source_url")
    if not facts.key_facts or not facts.main_event.strip():
        return PublishDecisionResult(decision=PublishDecision.REJECT, reason="insufficient_facts")
    if not facts.should_publish:
        return PublishDecisionResult(decision=PublishDecision.ADMIN_REVIEW, reason=facts.review_reason or "facts_marked_review")
    if validation.investment_advice_flags:
        return PublishDecisionResult(decision=PublishDecision.REJECT, reason="investment_advice_flags")
    if validation.unsupported_claims:
        return PublishDecisionResult(decision=PublishDecision.REJECT, reason="unsupported_claims")
    if validation.number_mismatches:
        return PublishDecisionResult(decision=PublishDecision.ADMIN_REVIEW, reason="number_mismatches")
    if validation.hype_language_flags:
        return PublishDecisionResult(decision=PublishDecision.ADMIN_REVIEW, reason="hype_language_flags")
    if validation.recommended_action == RecommendedAction.REJECT:
        return PublishDecisionResult(decision=PublishDecision.REJECT, reason="validator_reject")
    if validation.recommended_action in {RecommendedAction.REVISE, RecommendedAction.ADMIN_REVIEW}:
        return PublishDecisionResult(decision=PublishDecision.ADMIN_REVIEW, reason=f"validator_{validation.recommended_action}")
    if _has_rumor_or_limitation(facts):
        return PublishDecisionResult(decision=PublishDecision.ADMIN_REVIEW, reason="source_limitation_or_single_source")
    if facts.article_topic in HIGH_RISK_TOPICS:
        return PublishDecisionResult(decision=PublishDecision.ADMIN_REVIEW, reason=f"high_risk_topic_{facts.article_topic}")
    if _has_small_cap_hype(facts, brief):
        return PublishDecisionResult(decision=PublishDecision.REJECT, reason="small_cap_hype")
    if not validation.passed:
        return PublishDecisionResult(decision=PublishDecision.ADMIN_REVIEW, reason="validation_not_passed")
    if brief.importance_score < 50:
        return PublishDecisionResult(decision=PublishDecision.REJECT, reason="importance_too_low")
    if brief.importance_score < 75:
        return PublishDecisionResult(decision=PublishDecision.ADMIN_REVIEW, reason="importance_admin_review")
    if not auto_publish_enabled:
        return PublishDecisionResult(decision=PublishDecision.ADMIN_REVIEW, reason="auto_publish_disabled")
    return PublishDecisionResult(decision=PublishDecision.AUTO_PUBLISH, reason="passed_auto_publish_rules")


def _has_rumor_or_limitation(facts: ArticleFacts) -> bool:
    text = " ".join([*facts.source_limitations, *facts.uncertainty, facts.review_reason or ""]).lower()
    return any(marker in text for marker in RUMOR_MARKERS)


def _has_small_cap_hype(facts: ArticleFacts, brief: MarketBrief) -> bool:
    text = " ".join(
        [
            facts.article_title,
            facts.main_event,
            brief.short_title,
            brief.one_line_summary,
            *facts.source_limitations,
        ]
    ).lower()
    return any(marker.lower() in text for marker in SMALL_CAP_HYPE_MARKERS)

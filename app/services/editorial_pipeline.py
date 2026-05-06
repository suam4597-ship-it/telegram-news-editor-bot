from __future__ import annotations

import re
from dataclasses import dataclass

from app.llm.client import OpenAIResponsesClient
from app.llm.prompt_loader import load_prompt
from app.parsers.text_cleaner import clean_text, make_excerpt
from app.schemas.editorial import (
    ARTICLE_FACTS_SCHEMA,
    BRIEF_VALIDATION_SCHEMA,
    MARKET_BRIEF_SCHEMA,
    ArticleFacts,
    ArticleInput,
    ArticleTopic,
    BriefValidation,
    Direction,
    EditorialDraft,
    Entities,
    FactType,
    KeyFact,
    MarketBrief,
    MarketContext,
    PublishMode,
    RecommendedAction,
)
from app.services.publish_decision import decide_publish
from app.services.telegram_formatter import format_telegram_html_result

NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?\s?(?:%|bp|bps|million|billion|trillion|달러|원|조|억|만)?", re.I)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+")
TICKER_RE = re.compile(r"\b[A-Z]{1,5}\b")

INVESTMENT_ADVICE_PHRASES = {
    "매수",
    "강력 매수",
    "지금 사야",
    "보유 추천",
    "매도 추천",
    "목표가",
    "목표주가",
    "buy this stock",
    "strong buy",
}
HYPE_PHRASES = {"폭등", "대박", "무조건", "확실한 수혜", "인생 기회", "guaranteed", "sure win"}
OPINION_OR_RUMOR_MARKERS = {"rumor", "unconfirmed", "reportedly", "sources said", "opinion", "commentary"}


@dataclass(slots=True)
class ForeignEditorialPipeline:
    client: OpenAIResponsesClient | None = None

    def __post_init__(self) -> None:
        if self.client is None:
            self.client = OpenAIResponsesClient()

    def normalize_foreign_article(self, article: ArticleInput | dict) -> ArticleInput:
        normalized = ArticleInput.model_validate(article)
        return normalized.model_copy(
            update={
                "source_name": clean_text(normalized.source_name),
                "title": clean_text(normalized.title),
                "text_excerpt": make_excerpt(normalized.text_excerpt, 3000),
            }
        )

    async def create_draft(self, article: ArticleInput | dict, *, auto_publish_enabled: bool = False) -> EditorialDraft:
        normalized = self.normalize_foreign_article(article)
        facts = await self.extract_article_facts(normalized)
        brief = await self.write_korean_market_brief(facts)
        validation = await self.validate_market_brief(facts, brief)
        final_brief = validation.revised_brief or brief
        format_result = format_telegram_html_result(final_brief)
        if not format_result.passed:
            validation = validation.model_copy(
                update={
                    "passed": False,
                    "formatting_issues": [*validation.formatting_issues, format_result.reason or "telegram_format_failed"],
                    "recommended_action": RecommendedAction.ADMIN_REVIEW,
                }
            )
        decision = decide_publish(facts, final_brief, validation, auto_publish_enabled=auto_publish_enabled)
        return EditorialDraft(
            facts=facts,
            brief=final_brief,
            validation=validation,
            telegram_html=format_result.telegram_html if format_result.passed else None,
            format_result=format_result,
            publish_decision=decision,
        )

    async def extract_article_facts(self, article: ArticleInput) -> ArticleFacts:
        if self.client and self.client.available:
            prompt = load_prompt("foreign_fact_extractor.md").format(
                source_name=article.source_name,
                source_url=article.source_url,
                published_at=article.published_at or "",
                title=article.title,
                text_excerpt=article.text_excerpt,
            )
            payload = await self.client.structured_json(
                schema_name="article_facts",
                schema=ARTICLE_FACTS_SCHEMA,
                prompt=prompt,
                instructions="Extract source-grounded financial news facts. Return only schema-valid JSON.",
                strict=False,
            )
            return ArticleFacts.model_validate(payload)
        return _fallback_facts(article)

    async def write_korean_market_brief(self, facts: ArticleFacts) -> MarketBrief:
        if self.client and self.client.available:
            prompt = load_prompt("korean_market_brief_writer.md").format(
                article_facts_json=facts.model_dump_json(ensure_ascii=False)
            )
            payload = await self.client.structured_json(
                schema_name="market_brief",
                schema=MARKET_BRIEF_SCHEMA,
                prompt=prompt,
                instructions="Write a calm Korean market brief from the provided ArticleFacts only.",
                strict=False,
            )
            return MarketBrief.model_validate(payload)
        return _fallback_brief(facts)

    async def validate_market_brief(self, facts: ArticleFacts, brief: MarketBrief) -> BriefValidation:
        local_validation = _local_validate(facts, brief)
        if self.client and self.client.available:
            prompt = load_prompt("brief_validator.md").format(
                article_facts_json=facts.model_dump_json(ensure_ascii=False),
                market_brief_json=brief.model_dump_json(ensure_ascii=False),
            )
            payload = await self.client.structured_json(
                schema_name="brief_validation",
                schema=BRIEF_VALIDATION_SCHEMA,
                prompt=prompt,
                instructions="Validate factuality, compliance, and Telegram readiness.",
                strict=False,
            )
            model_validation = BriefValidation.model_validate(payload)
            return _merge_validations(local_validation, model_validation)
        return local_validation


def _fallback_facts(article: ArticleInput) -> ArticleFacts:
    text = clean_text(f"{article.title}. {article.text_excerpt}")
    sentences = [sentence.strip() for sentence in SENTENCE_SPLIT_RE.split(text) if sentence.strip()]
    key_sentences = sentences[:3] or [text]
    topic = _topic_for(text)
    limitations = []
    lowered = text.lower()
    if any(marker in lowered for marker in OPINION_OR_RUMOR_MARKERS):
        limitations.append("single-source or unconfirmed report; admin review recommended")
    if len(text) < 80:
        limitations.append("limited source excerpt")
    should_publish = bool(article.source_url and key_sentences and len(text) >= 40)
    return ArticleFacts(
        source_name=article.source_name,
        source_url=article.source_url,
        original_language=article.original_language,
        published_at=article.published_at,
        article_title=article.title,
        article_topic=topic,
        main_event=make_excerpt(key_sentences[0], 220),
        key_facts=[
            KeyFact(
                fact=make_excerpt(sentence, 180),
                evidence=make_excerpt(sentence, 220),
                fact_type=_fact_type_for(sentence),
            )
            for sentence in key_sentences
        ],
        entities=_entities_for(text),
        market_context=_market_context_for(text, topic),
        uncertainty=limitations[:],
        source_limitations=limitations,
        should_publish=should_publish,
        review_reason=None if should_publish else "insufficient_facts_or_source",
    )


def _fallback_brief(facts: ArticleFacts) -> MarketBrief:
    hashtags = _hashtags_for(facts)
    korean_context = _korean_context_for(facts)
    return MarketBrief(
        short_title=make_excerpt(_korean_title_for(facts), 35),
        one_line_summary=_one_line_summary_for(facts),
        what_happened=_what_happened_for(facts),
        why_it_matters=_why_it_matters_for(facts),
        what_to_watch=_what_to_watch_for(facts),
        korean_context=korean_context,
        risk_note=_risk_note_for(facts),
        source_name=facts.source_name,
        source_url=facts.source_url,
        hashtags=hashtags,
        category=facts.article_topic.value,
        importance_score=_importance_for(facts),
        publish_mode=PublishMode.ADMIN_REVIEW if facts.source_limitations else PublishMode.AUTO_PUBLISH,
    )


def _local_validate(facts: ArticleFacts, brief: MarketBrief) -> BriefValidation:
    factuality_issues = []
    unsupported_claims = []
    number_mismatches = []
    investment_flags = _phrase_hits(_brief_text(brief), INVESTMENT_ADVICE_PHRASES)
    hype_flags = _phrase_hits(_brief_text(brief), HYPE_PHRASES)
    formatting_issues = []

    fact_text = " ".join(
        [facts.main_event, facts.article_title, *[fact.fact for fact in facts.key_facts], *[fact.evidence for fact in facts.key_facts]]
    )
    fact_numbers = set(NUMBER_RE.findall(fact_text))
    brief_numbers = set(NUMBER_RE.findall(_brief_text(brief)))
    unsupported_numbers = {number[0] if isinstance(number, tuple) else number for number in brief_numbers} - {
        number[0] if isinstance(number, tuple) else number for number in fact_numbers
    }
    if unsupported_numbers:
        number_mismatches.extend(sorted(unsupported_numbers))

    if brief.source_url != facts.source_url:
        factuality_issues.append("source_url does not match ArticleFacts")
    if not brief.source_url:
        formatting_issues.append("missing source_url")
    if not 2 <= len(brief.hashtags) <= 4:
        formatting_issues.append("hashtags must contain 2 to 4 items")
    if facts.source_limitations and not brief.risk_note:
        unsupported_claims.append("source limitations were not reflected in risk_note")

    passed = not any([factuality_issues, unsupported_claims, number_mismatches, investment_flags, hype_flags, formatting_issues])
    action = RecommendedAction.PUBLISH if passed else RecommendedAction.ADMIN_REVIEW
    if investment_flags or not brief.source_url:
        action = RecommendedAction.REJECT
    return BriefValidation(
        passed=passed,
        factuality_issues=factuality_issues,
        unsupported_claims=unsupported_claims,
        number_mismatches=number_mismatches,
        investment_advice_flags=investment_flags,
        hype_language_flags=hype_flags,
        copyright_risk_flags=[],
        formatting_issues=formatting_issues,
        recommended_action=action,
        revised_brief=None,
    )


def _merge_validations(local: BriefValidation, model: BriefValidation) -> BriefValidation:
    return BriefValidation(
        passed=local.passed and model.passed,
        factuality_issues=[*local.factuality_issues, *model.factuality_issues],
        unsupported_claims=[*local.unsupported_claims, *model.unsupported_claims],
        number_mismatches=[*local.number_mismatches, *model.number_mismatches],
        investment_advice_flags=[*local.investment_advice_flags, *model.investment_advice_flags],
        hype_language_flags=[*local.hype_language_flags, *model.hype_language_flags],
        copyright_risk_flags=[*local.copyright_risk_flags, *model.copyright_risk_flags],
        formatting_issues=[*local.formatting_issues, *model.formatting_issues],
        recommended_action=model.recommended_action if local.passed else local.recommended_action,
        revised_brief=model.revised_brief,
    )


def _topic_for(text: str) -> ArticleTopic:
    lowered = text.lower()
    if any(keyword in lowered for keyword in ("fed", "central bank", "fomc", "rate cut", "rate hike")):
        return ArticleTopic.CENTRAL_BANK
    if any(keyword in lowered for keyword in ("cpi", "inflation", "gdp", "retail sales", "jobs")):
        return ArticleTopic.MACRO
    if any(keyword in lowered for keyword in ("earnings", "revenue", "margin", "guidance")):
        return ArticleTopic.EARNINGS
    if any(keyword in lowered for keyword in ("tariff", "sanction", "export control", "taiwan", "middle east", "ukraine")):
        return ArticleTopic.GEOPOLITICS
    if any(keyword in lowered for keyword in ("oil", "gas", "copper", "lithium")):
        return ArticleTopic.COMMODITIES
    if any(keyword in lowered for keyword in ("policy", "regulation", "rule")):
        return ArticleTopic.POLICY
    if any(keyword in lowered for keyword in ("dollar", "yen", "won", "fx")):
        return ArticleTopic.FX
    return ArticleTopic.EQUITIES


def _fact_type_for(sentence: str) -> FactType:
    lowered = sentence.lower()
    if NUMBER_RE.search(sentence):
        return FactType.NUMBER
    if any(keyword in lowered for keyword in ("said", "says", "quote")):
        return FactType.QUOTE
    if any(keyword in lowered for keyword in ("guidance", "forecast", "outlook")):
        return FactType.GUIDANCE
    if any(keyword in lowered for keyword in ("policy", "rule", "regulation", "tariff")):
        return FactType.POLICY
    return FactType.EVENT


def _entities_for(text: str) -> Entities:
    tickers = sorted(set(TICKER_RE.findall(text)))[:5]
    companies = []
    for keyword in ("Nvidia", "Apple", "Tesla", "Microsoft", "Amazon", "Samsung", "SK Hynix", "TSMC", "AMD", "OpenAI"):
        if keyword.lower() in text.lower():
            companies.append(keyword)
    countries = [country for country in ("U.S.", "China", "Korea", "Japan", "Taiwan", "Russia", "Ukraine") if country.lower() in text.lower()]
    assets = [asset for asset in ("dollar", "Treasury yields", "oil", "gold", "won") if asset.lower() in text.lower()]
    return Entities(companies=companies[:5], tickers=tickers, countries=countries, assets=assets)


def _market_context_for(text: str, topic: ArticleTopic) -> MarketContext:
    lowered = text.lower()
    sectors = []
    for keyword, sector in (
        ("chip", "semiconductors"),
        ("ai", "AI"),
        ("battery", "batteries"),
        ("ev", "EV"),
        ("oil", "energy"),
        ("bank", "financials"),
        ("defense", "defense"),
    ):
        if keyword in lowered and sector not in sectors:
            sectors.append(sector)
    asset_classes = ["stocks"]
    if topic in {ArticleTopic.RATES, ArticleTopic.CENTRAL_BANK, ArticleTopic.MACRO}:
        asset_classes.extend(["bonds", "fx"])
    if topic == ArticleTopic.COMMODITIES:
        asset_classes.append("commodities")
    confidence = 0.65 if sectors or topic != ArticleTopic.OTHER else 0.35
    return MarketContext(affected_asset_classes=asset_classes, affected_sectors=sectors, possible_direction=Direction.UNCLEAR, confidence=confidence)


def _hashtags_for(facts: ArticleFacts) -> list[str]:
    tags = []
    topic_tag = {
        ArticleTopic.MACRO: "#매크로",
        ArticleTopic.CENTRAL_BANK: "#연준",
        ArticleTopic.EARNINGS: "#실적",
        ArticleTopic.GEOPOLITICS: "#지정학",
        ArticleTopic.POLICY: "#정책",
        ArticleTopic.COMMODITIES: "#원자재",
    }.get(facts.article_topic, "#글로벌")
    tags.append(topic_tag)
    if facts.market_context.affected_sectors:
        tags.append(f"#{facts.market_context.affected_sectors[0].replace(' ', '')}")
    elif facts.entities.companies:
        tags.append(f"#{facts.entities.companies[0].replace(' ', '')}")
    else:
        tags.append("#시장")
    if len(tags) < 3:
        tags.append("#외신")
    return tags[:4]


def _korean_title_for(facts: ArticleFacts) -> str:
    if facts.article_topic == ArticleTopic.MACRO:
        return "미국 지표, 금리 기대를 다시 흔듭니다"
    if facts.article_topic == ArticleTopic.EARNINGS:
        company = facts.entities.companies[0] if facts.entities.companies else "주요 기업"
        return f"{company} 실적, 가이던스가 관건입니다"
    if facts.article_topic == ArticleTopic.GEOPOLITICS:
        return "지정학 변수, 공급망 부담을 키웁니다"
    if facts.article_topic == ArticleTopic.CENTRAL_BANK:
        return "중앙은행 발언, 금리 기대를 조정합니다"
    return make_excerpt(facts.article_title, 35)


def _why_it_matters_for(facts: ArticleFacts) -> str:
    if facts.article_topic in {ArticleTopic.MACRO, ArticleTopic.CENTRAL_BANK, ArticleTopic.RATES}:
        return "금리 기대가 바뀌면 달러, 국채금리, 성장주 밸류에이션으로 영향이 이어질 수 있습니다."
    if facts.article_topic == ArticleTopic.EARNINGS:
        return "매출, 마진, 가이던스 변화는 같은 업종의 수요와 공급업체 기대에도 영향을 줄 수 있습니다."
    if facts.article_topic == ArticleTopic.GEOPOLITICS:
        return "수출통제, 제재, 관세 이슈는 공급망과 원가, 관련 섹터의 투자심리로 연결될 수 있습니다."
    if facts.article_topic == ArticleTopic.COMMODITIES:
        return "원자재 공급 차질은 비용 부담과 인플레이션 기대, 업종별 마진 차이로 이어질 수 있습니다."
    if facts.article_topic == ArticleTopic.POLICY:
        return "규칙 변화는 적용 대상 기업과 시행 시점에 따라 업종별 영향이 달라질 수 있습니다."
    return "단기 가격보다 후속 숫자와 회사 코멘트가 실제 기대를 바꾸는지가 중요합니다."


def _one_line_summary_for(facts: ArticleFacts) -> str:
    company = facts.entities.companies[0] if facts.entities.companies else "주요 기업"
    number = _first_number(facts)
    if facts.article_topic == ArticleTopic.EARNINGS:
        if number:
            return f"{company} 실적에서 {number} 수치가 확인되며 AI 수요와 가이던스가 핵심 변수로 떠올랐습니다."
        return f"{company} 실적 발표에서 수요와 가이던스 변화가 시장의 확인 포인트로 떠올랐습니다."
    if facts.article_topic in {ArticleTopic.MACRO, ArticleTopic.CENTRAL_BANK, ArticleTopic.RATES}:
        if number:
            return f"미국 지표에서 {number} 수치가 확인되며 금리 기대가 다시 조정될 수 있습니다."
        return "미국 지표와 중앙은행 발언이 금리 기대를 다시 흔들 수 있는 상황입니다."
    if facts.article_topic == ArticleTopic.GEOPOLITICS:
        return "지정학·공급망 변수가 관련 산업의 원가와 수급 불확실성을 키우고 있습니다."
    if facts.article_topic == ArticleTopic.COMMODITIES:
        return "원자재 수급 변화가 비용 부담과 업종별 마진 차이로 이어질 수 있습니다."
    return "외신에서 확인된 이벤트가 관련 섹터의 후속 반응을 살펴볼 만한 변수로 떠올랐습니다."


def _what_happened_for(facts: ArticleFacts) -> str:
    company = facts.entities.companies[0] if facts.entities.companies else None
    number = _first_number(facts)
    if facts.article_topic == ArticleTopic.EARNINGS:
        subject = company or "해당 기업"
        if number:
            return f"{subject}가 실적 발표에서 {number} 관련 수치를 제시했고, 시장은 매출·마진·가이던스 변화를 함께 보고 있습니다."
        return f"{subject}의 실적과 다음 분기 가이던스가 외신 보도의 핵심 내용입니다."
    if facts.article_topic in {ArticleTopic.MACRO, ArticleTopic.CENTRAL_BANK, ArticleTopic.RATES}:
        if number:
            return f"발표된 지표에서 {number} 수치가 확인됐고, 금리와 달러 반응이 함께 부각됐습니다."
        return "중앙은행 발언 또는 경제 지표가 금리 기대와 달러 흐름에 영향을 줄 수 있는 내용으로 보도됐습니다."
    if facts.article_topic == ArticleTopic.GEOPOLITICS:
        return "수출통제, 제재, 관세 또는 지역 리스크가 공급망 변수로 언급됐습니다."
    return "외신 보도에서 확인된 이벤트와 관련 기업·섹터 반응이 핵심입니다."


def _what_to_watch_for(facts: ArticleFacts) -> str:
    if facts.article_topic == ArticleTopic.EARNINGS:
        return "다음 실적 발표, 가이던스, 공급업체 주문 흐름을 같이 확인해야 합니다."
    if facts.article_topic == ArticleTopic.GEOPOLITICS:
        return "공식 발표, 시행 시점, 한국 기업의 직접 노출 여부를 확인해야 합니다."
    if facts.article_topic in {ArticleTopic.MACRO, ArticleTopic.CENTRAL_BANK}:
        return "다음 물가·고용 지표와 중앙은행 발언에서 같은 방향의 신호가 이어지는지 봐야 합니다."
    return "후속 보도와 회사 코멘트, 관련 섹터 반응을 함께 확인해야 합니다."


def _korean_context_for(facts: ArticleFacts) -> str | None:
    text = " ".join([facts.article_title, facts.main_event, *facts.market_context.affected_sectors, *facts.entities.companies]).lower()
    if any(keyword in text for keyword in ("semiconductor", "chip", "ai", "hbm", "nvidia", "samsung", "sk hynix")):
        return "국내에서는 반도체 밸류체인과 AI 서버 수요 기대가 연결 포인트입니다."
    if any(keyword in text for keyword in ("battery", "ev", "tesla")):
        return "국내에서는 2차전지 소재와 전기차 공급망 반응을 같이 볼 필요가 있습니다."
    if facts.article_topic in {ArticleTopic.MACRO, ArticleTopic.CENTRAL_BANK, ArticleTopic.FX}:
        return "국내에서는 원/달러 환율과 외국인 수급 변화로 이어질 수 있습니다."
    if facts.article_topic == ArticleTopic.GEOPOLITICS:
        return "국내 기업의 직접 노출도와 대체 공급망 수혜 여부는 추가 확인이 필요합니다."
    return None


def _risk_note_for(facts: ArticleFacts) -> str | None:
    if facts.source_limitations:
        return "단일 보도 또는 제한된 발췌 기준이라 후속 확인이 필요합니다."
    if facts.uncertainty:
        return make_excerpt(facts.uncertainty[0], 120)
    return None


def _importance_for(facts: ArticleFacts) -> float:
    base = 55.0
    if facts.article_topic in {ArticleTopic.MACRO, ArticleTopic.CENTRAL_BANK, ArticleTopic.EARNINGS, ArticleTopic.GEOPOLITICS}:
        base += 15
    if facts.key_facts and any(fact.fact_type == FactType.NUMBER for fact in facts.key_facts):
        base += 10
    if facts.market_context.affected_sectors:
        base += 8
    if facts.source_limitations:
        base -= 15
    return max(0, min(100, base))


def _brief_text(brief: MarketBrief) -> str:
    return " ".join(
        value
        for value in (
            brief.short_title,
            brief.one_line_summary,
            brief.what_happened,
            brief.why_it_matters,
            brief.what_to_watch,
            brief.korean_context,
            brief.risk_note,
        )
        if value
    )


def _phrase_hits(text: str, phrases: set[str]) -> list[str]:
    lowered = text.lower()
    return sorted(phrase for phrase in phrases if phrase.lower() in lowered)


def _first_fact(facts: ArticleFacts) -> str:
    return facts.key_facts[0].fact if facts.key_facts else facts.main_event


def _korean_sentence(text: str, limit: int) -> str:
    sentence = make_excerpt(text, limit).strip()
    if sentence and sentence[-1] not in ".!?。！？…":
        sentence += "."
    return sentence


def _first_number(facts: ArticleFacts) -> str | None:
    text = " ".join([facts.main_event, *[fact.fact for fact in facts.key_facts]])
    match = NUMBER_RE.search(text)
    return match.group(0).strip() if match else None

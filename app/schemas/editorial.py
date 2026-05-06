from __future__ import annotations

from enum import StrEnum

from pydantic import AnyUrl, BaseModel, Field, field_validator, model_validator


class ArticleTopic(StrEnum):
    MACRO = "macro"
    RATES = "rates"
    FX = "fx"
    COMMODITIES = "commodities"
    EQUITIES = "equities"
    EARNINGS = "earnings"
    POLICY = "policy"
    CENTRAL_BANK = "central_bank"
    GEOPOLITICS = "geopolitics"
    CRYPTO_REGULATION = "crypto_regulation"
    OTHER = "other"


class FactType(StrEnum):
    NUMBER = "number"
    DATE = "date"
    QUOTE = "quote"
    EVENT = "event"
    GUIDANCE = "guidance"
    POLICY = "policy"
    MARKET_REACTION = "market_reaction"
    BACKGROUND = "background"


class Direction(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    MIXED = "mixed"
    UNCLEAR = "unclear"


class PublishMode(StrEnum):
    AUTO_PUBLISH = "auto_publish"
    ADMIN_REVIEW = "admin_review"
    DO_NOT_PUBLISH = "do_not_publish"


class RecommendedAction(StrEnum):
    PUBLISH = "publish"
    REVISE = "revise"
    ADMIN_REVIEW = "admin_review"
    REJECT = "reject"


class PublishDecision(StrEnum):
    AUTO_PUBLISH = "auto_publish"
    ADMIN_REVIEW = "admin_review"
    REJECT = "reject"


class KeyFact(BaseModel):
    fact: str
    evidence: str
    fact_type: FactType


class Entities(BaseModel):
    companies: list[str] = Field(default_factory=list)
    tickers: list[str] = Field(default_factory=list)
    people: list[str] = Field(default_factory=list)
    institutions: list[str] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)
    assets: list[str] = Field(default_factory=list)


class MarketContext(BaseModel):
    affected_asset_classes: list[str] = Field(default_factory=list)
    affected_sectors: list[str] = Field(default_factory=list)
    possible_direction: Direction = Direction.UNCLEAR
    confidence: float = Field(default=0.0, ge=0, le=1)


class ArticleInput(BaseModel):
    source_name: str
    source_url: str
    original_language: str = "en"
    published_at: str | None = None
    title: str
    text_excerpt: str

    @field_validator("source_url")
    @classmethod
    def source_url_required(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source_url is required")
        return value


class ArticleFacts(BaseModel):
    source_name: str
    source_url: str
    original_language: str
    published_at: str | None = None
    article_title: str
    article_topic: ArticleTopic
    main_event: str
    key_facts: list[KeyFact] = Field(default_factory=list)
    entities: Entities = Field(default_factory=Entities)
    market_context: MarketContext = Field(default_factory=MarketContext)
    uncertainty: list[str] = Field(default_factory=list)
    source_limitations: list[str] = Field(default_factory=list)
    should_publish: bool = True
    review_reason: str | None = None

    @field_validator("source_url")
    @classmethod
    def source_url_required(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source_url is required")
        return value

    @model_validator(mode="after")
    def require_review_reason_when_not_publishable(self) -> ArticleFacts:
        if not self.should_publish and not self.review_reason:
            self.review_reason = "insufficient_publishability"
        return self


class MarketBrief(BaseModel):
    short_title: str = Field(max_length=80)
    one_line_summary: str
    what_happened: str
    why_it_matters: str
    what_to_watch: str
    korean_context: str | None = None
    risk_note: str | None = None
    source_name: str
    source_url: str
    hashtags: list[str] = Field(default_factory=list)
    category: str
    importance_score: float = Field(ge=0, le=100)
    publish_mode: PublishMode = PublishMode.ADMIN_REVIEW

    @field_validator("source_url")
    @classmethod
    def source_url_required(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source_url is required")
        return value

    @field_validator("hashtags")
    @classmethod
    def hashtag_count(cls, value: list[str]) -> list[str]:
        if not 2 <= len(value) <= 4:
            raise ValueError("hashtags must contain 2 to 4 items")
        normalized = []
        for tag in value:
            cleaned = tag.strip()
            if not cleaned:
                continue
            normalized.append(cleaned if cleaned.startswith("#") else f"#{cleaned}")
        if not 2 <= len(normalized) <= 4:
            raise ValueError("hashtags must contain 2 to 4 non-empty items")
        return normalized


class BriefValidation(BaseModel):
    passed: bool
    factuality_issues: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    number_mismatches: list[str] = Field(default_factory=list)
    investment_advice_flags: list[str] = Field(default_factory=list)
    hype_language_flags: list[str] = Field(default_factory=list)
    copyright_risk_flags: list[str] = Field(default_factory=list)
    formatting_issues: list[str] = Field(default_factory=list)
    recommended_action: RecommendedAction
    revised_brief: MarketBrief | None = None


class FormatResult(BaseModel):
    telegram_html: str
    passed: bool
    needs_review: bool = False
    reason: str | None = None


class PublishDecisionResult(BaseModel):
    decision: PublishDecision
    reason: str


class EditorialDraft(BaseModel):
    facts: ArticleFacts
    brief: MarketBrief
    validation: BriefValidation
    telegram_html: str | None = None
    format_result: FormatResult | None = None
    publish_decision: PublishDecisionResult


ARTICLE_FACTS_SCHEMA = ArticleFacts.model_json_schema()
MARKET_BRIEF_SCHEMA = MarketBrief.model_json_schema()
BRIEF_VALIDATION_SCHEMA = BriefValidation.model_json_schema()

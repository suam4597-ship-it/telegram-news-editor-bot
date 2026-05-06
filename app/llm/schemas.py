from __future__ import annotations

from pydantic import BaseModel, Field


class KeyFact(BaseModel):
    fact: str
    evidence_text: str
    fact_type: str


class Entities(BaseModel):
    companies: list[str] = Field(default_factory=list)
    tickers: list[str] = Field(default_factory=list)
    people: list[str] = Field(default_factory=list)
    institutions: list[str] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)
    assets: list[str] = Field(default_factory=list)


class MarketRelevance(BaseModel):
    asset_classes: list[str] = Field(default_factory=list)
    sectors: list[str] = Field(default_factory=list)
    impact_direction: str = "unclear"
    confidence: float = 0.0


class FactExtraction(BaseModel):
    title: str
    source: str
    published_at: str
    main_event: str
    key_facts: list[KeyFact]
    entities: Entities
    market_relevance: MarketRelevance
    risks_or_uncertainties: list[str]
    do_not_say: list[str]


class SummaryOutput(BaseModel):
    telegram_text: str
    short_title: str
    tags: list[str]
    risk_level: str
    post_type: str = "editorial_brief"


class ValidationIssue(BaseModel):
    issue_type: str
    severity: str
    message: str


class ValidationOutput(BaseModel):
    pass_: bool = Field(alias="pass")
    issues: list[ValidationIssue]
    revised_text: str
    factuality_score: float
    copy_similarity_score: float


FACT_EXTRACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "title",
        "source",
        "published_at",
        "main_event",
        "key_facts",
        "entities",
        "market_relevance",
        "risks_or_uncertainties",
        "do_not_say",
    ],
    "properties": {
        "title": {"type": "string"},
        "source": {"type": "string"},
        "published_at": {"type": "string"},
        "main_event": {"type": "string"},
        "key_facts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["fact", "evidence_text", "fact_type"],
                "properties": {
                    "fact": {"type": "string"},
                    "evidence_text": {"type": "string"},
                    "fact_type": {
                        "type": "string",
                        "enum": ["number", "date", "quote", "event", "forecast", "background", "unclear"],
                    },
                },
            },
        },
        "entities": {
            "type": "object",
            "additionalProperties": False,
            "required": ["companies", "tickers", "people", "institutions", "countries", "assets"],
            "properties": {
                "companies": {"type": "array", "items": {"type": "string"}},
                "tickers": {"type": "array", "items": {"type": "string"}},
                "people": {"type": "array", "items": {"type": "string"}},
                "institutions": {"type": "array", "items": {"type": "string"}},
                "countries": {"type": "array", "items": {"type": "string"}},
                "assets": {"type": "array", "items": {"type": "string"}},
            },
        },
        "market_relevance": {
            "type": "object",
            "additionalProperties": False,
            "required": ["asset_classes", "sectors", "impact_direction", "confidence"],
            "properties": {
                "asset_classes": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["stocks", "bonds", "fx", "commodities", "crypto", "unclear"]},
                },
                "sectors": {"type": "array", "items": {"type": "string"}},
                "impact_direction": {"type": "string", "enum": ["positive", "negative", "mixed", "unclear"]},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
        },
        "risks_or_uncertainties": {"type": "array", "items": {"type": "string"}},
        "do_not_say": {"type": "array", "items": {"type": "string"}},
    },
}

SUMMARY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["telegram_text", "short_title", "tags", "risk_level", "post_type"],
    "properties": {
        "telegram_text": {"type": "string"},
        "short_title": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
        "post_type": {
            "type": "string",
            "enum": ["short_link", "editorial_brief", "market_brief", "data_brief", "breaking"],
        },
    },
}

VALIDATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["pass", "issues", "revised_text", "factuality_score", "copy_similarity_score"],
    "properties": {
        "pass": {"type": "boolean"},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["issue_type", "severity", "message"],
                "properties": {
                    "issue_type": {"type": "string"},
                    "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                    "message": {"type": "string"},
                },
            },
        },
        "revised_text": {"type": "string"},
        "factuality_score": {"type": "number", "minimum": 0, "maximum": 1},
        "copy_similarity_score": {"type": "number", "minimum": 0, "maximum": 1},
    },
}

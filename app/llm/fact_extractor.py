from __future__ import annotations

from datetime import datetime

from app.config import settings
from app.llm.client import OpenAIResponsesClient
from app.llm.prompt_loader import load_prompt
from app.llm.schemas import FACT_EXTRACTION_SCHEMA, Entities, FactExtraction, KeyFact, MarketRelevance
from app.parsers.text_cleaner import clean_text, make_excerpt


class FactExtractor:
    def __init__(self, client: OpenAIResponsesClient | None = None):
        self.client = client or OpenAIResponsesClient()

    async def extract(
        self,
        *,
        title: str | None,
        source: str,
        published_at: datetime | None,
        article_text: str | None,
    ) -> FactExtraction:
        if not self.client.available:
            return self._fallback(title=title, source=source, published_at=published_at, article_text=article_text)

        prompt = load_prompt("fact_extractor_v1.md").format(
            title=title or "",
            source=source,
            published_at=published_at.isoformat() if published_at else "",
            article_text=make_excerpt(article_text, 2500),
        )
        payload = await self.client.structured_json(
            schema_name="fact_extraction",
            schema=FACT_EXTRACTION_SCHEMA,
            prompt=prompt,
            instructions="You extract verifiable economic news facts for a Korean Telegram editor.",
        )
        return FactExtraction.model_validate(payload)

    def _fallback(
        self,
        *,
        title: str | None,
        source: str,
        published_at: datetime | None,
        article_text: str | None,
    ) -> FactExtraction:
        text = clean_text(article_text)
        main_event = clean_text(title) or make_excerpt(text, 90) or "확인된 주요 이벤트"
        facts = [KeyFact(fact=make_excerpt(text or main_event, 140), evidence_text=make_excerpt(text, 160), fact_type="event")]
        return FactExtraction(
            title=main_event,
            source=source,
            published_at=published_at.isoformat() if published_at else "",
            main_event=main_event,
            key_facts=facts,
            entities=Entities(),
            market_relevance=MarketRelevance(asset_classes=["unclear"], sectors=[], impact_direction="unclear", confidence=0.2),
            risks_or_uncertainties=["원문 세부 내용 확인 필요"],
            do_not_say=["매수/매도 추천"],
        )


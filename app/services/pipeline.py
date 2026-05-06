from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.collectors.registry import collector_for
from app.config import settings
from app.llm.fact_extractor import FactExtractor
from app.llm.summary_writer import SummaryWriter
from app.llm.validator import SummaryValidator
from app.models import ArticleCluster, AuditLog, RawItem, Source, Summary
from app.publisher.review_bot import ReviewService
from app.ranking.clustering import get_or_create_cluster
from app.ranking.deduper import find_existing_duplicate
from app.ranking.scorer import score_item
from app.schemas.editorial import ArticleInput, PublishDecision
from app.services.editorial_pipeline import ForeignEditorialPipeline
from app.services.post_policy import select_post_type, should_skip_item


@dataclass(slots=True)
class CollectResult:
    sources_checked: int = 0
    items_created: int = 0
    duplicates_skipped: int = 0
    rejected: int = 0
    errors: int = 0


@dataclass(slots=True)
class DraftResult:
    items_checked: int = 0
    summaries_created: int = 0
    review_messages_sent: int = 0
    items_skipped: int = 0
    errors: int = 0


class NewsPipeline:
    def __init__(
        self,
        fact_extractor: FactExtractor | None = None,
        summary_writer: SummaryWriter | None = None,
        validator: SummaryValidator | None = None,
        review_service: ReviewService | None = None,
    ):
        self.fact_extractor = fact_extractor or FactExtractor()
        self.summary_writer = summary_writer or SummaryWriter()
        self.validator = validator or SummaryValidator()
        self.review_service = review_service or ReviewService()
        self.foreign_editorial_pipeline = ForeignEditorialPipeline()

    async def collect_once(self, session: Session, *, source_id: int | None = None, limit: int = 10) -> CollectResult:
        query = select(Source).where(Source.is_active.is_(True))
        if source_id is not None:
            query = query.where(Source.id == source_id)
        sources = list(session.scalars(query))
        result = CollectResult(sources_checked=len(sources))

        for source in sources:
            collector = collector_for(source)
            try:
                collected_items = await collector.collect(limit=limit)
            except Exception as exc:  # noqa: BLE001
                result.errors += 1
                session.add(
                    AuditLog(
                        event_type="collect_error",
                        entity_type="source",
                        entity_id=source.id,
                        message=str(exc),
                        payload_json={},
                    )
                )
                session.commit()
                continue

            for collected in collected_items:
                status = "rejected" if collected.rejected_reason else "fetched"
                existing = find_existing_duplicate(session, collected.canonical_url, collected.title, collected.content_hash)
                if existing:
                    result.duplicates_skipped += 1
                    continue
                raw_item = RawItem(
                    source_id=source.id,
                    original_url=collected.original_url,
                    canonical_url=collected.canonical_url,
                    title=collected.title,
                    author=collected.author,
                    published_at=collected.published_at,
                    content_hash=collected.content_hash,
                    title_hash=collected.title_hash,
                    raw_excerpt=collected.excerpt,
                    full_text_stored=False,
                    status=status,
                    rejection_reason=collected.rejected_reason,
                )
                session.add(raw_item)
                try:
                    session.flush()
                except IntegrityError:
                    session.rollback()
                    result.duplicates_skipped += 1
                    continue
                if collected.rejected_reason:
                    result.rejected += 1
                else:
                    result.items_created += 1
            source.last_crawled_at = datetime.now(UTC)
            session.add(AuditLog(event_type="collect_complete", entity_type="source", entity_id=source.id, payload_json=asdict(result)))
            session.commit()
        return result

    async def draft_once(self, session: Session, *, limit: int = 3) -> DraftResult:
        items = list(
            session.scalars(
                select(RawItem)
                .join(RawItem.source)
                .where(RawItem.status.in_(["fetched", "parsed"]))
                .where(Source.is_active.is_(True))
                .order_by(RawItem.published_at.desc().nullslast(), RawItem.fetched_at.desc())
                .limit(limit)
            )
        )
        result = DraftResult(items_checked=len(items))
        for item in items:
            try:
                summary = await self._draft_item(session, item)
                if summary is None:
                    result.items_skipped += 1
                    continue
                result.summaries_created += 1
                review_job = await self.review_service.send_summary_for_review(session, summary)
                if review_job is not None:
                    result.review_messages_sent += 1
            except Exception as exc:  # noqa: BLE001
                result.errors += 1
                item.status = "draft_failed"
                session.add(
                    AuditLog(
                        event_type="draft_error",
                        entity_type="raw_item",
                        entity_id=item.id,
                        message=str(exc),
                        payload_json={},
                    )
                )
                session.commit()
        return result

    async def _draft_item(self, session: Session, item: RawItem) -> Summary | None:
        scores = score_item(item, item.source)
        skip_reason = should_skip_item(item, item.source, scores)
        if skip_reason:
            item.status = "rejected"
            item.rejection_reason = skip_reason
            session.add(
                AuditLog(
                    event_type="draft_skipped",
                    entity_type="raw_item",
                    entity_id=item.id,
                    message=skip_reason,
                    payload_json=scores,
                )
            )
            session.commit()
            return None
        post_type = select_post_type(item, item.source, scores)
        cluster = get_or_create_cluster(
            session,
            item,
            importance_score=scores["importance_score"],
            novelty_score=scores["novelty_score"],
            market_impact_score=scores["market_impact_score"],
        )
        if _is_foreign_item(item):
            return await self._draft_foreign_item(session, item, cluster, scores, post_type)
        facts = await self.fact_extractor.extract(
            title=item.title,
            source=item.source.name,
            published_at=item.published_at,
            article_text=item.raw_excerpt,
        )
        summary_output = await self.summary_writer.write(
            facts=facts,
            source_url=item.canonical_url,
            source_name=item.source.name,
            post_type=post_type,
        )
        validation = await self.validator.validate(facts=facts, telegram_text=summary_output.telegram_text)
        telegram_text = _select_validated_text(summary_output.telegram_text, validation)
        summary = Summary(
            cluster_id=cluster.id,
            fact_json=facts.model_dump(mode="json"),
            summary_json=summary_output.model_dump(mode="json"),
            validation_json=validation.model_dump(mode="json", by_alias=True),
            telegram_text=telegram_text,
            post_type=post_type,
            compliance_flags={"issues": [issue.model_dump(mode="json") for issue in validation.issues]},
            factuality_score=validation.factuality_score,
            copy_similarity_score=validation.copy_similarity_score,
            status="draft" if validation.pass_ else "needs_review",
            model_name=settings.openai_model if settings.openai_api_key else "local-fallback",
            prompt_version="v1",
        )
        session.add(summary)
        item.status = "summarized"
        session.add(
            AuditLog(
                event_type="summary_created",
                entity_type="raw_item",
                entity_id=item.id,
                payload_json={**scores, "post_type": post_type},
            )
        )
        session.commit()
        session.refresh(summary)
        return summary

    async def _draft_foreign_item(
        self,
        session: Session,
        item: RawItem,
        cluster: ArticleCluster,
        scores: dict[str, float],
        post_type: str,
    ) -> Summary | None:
        draft = await self.foreign_editorial_pipeline.create_draft(
            ArticleInput(
                source_name=item.source.name,
                source_url=item.canonical_url,
                original_language=item.source.language or "en",
                published_at=item.published_at.isoformat() if item.published_at else None,
                title=item.title or "",
                text_excerpt=item.raw_excerpt or item.title or "",
            ),
            auto_publish_enabled=bool(item.source.auto_publish_allowed),
        )
        if draft.publish_decision.decision == PublishDecision.REJECT:
            item.status = "rejected"
            item.rejection_reason = draft.publish_decision.reason
            session.add(
                AuditLog(
                    event_type="foreign_draft_rejected",
                    entity_type="raw_item",
                    entity_id=item.id,
                    message=draft.publish_decision.reason,
                    payload_json={**scores, "decision": draft.publish_decision.model_dump(mode="json")},
                )
            )
            session.commit()
            return None

        summary = Summary(
            cluster_id=cluster.id,
            fact_json=draft.facts.model_dump(mode="json"),
            summary_json=draft.brief.model_dump(mode="json"),
            validation_json=draft.validation.model_dump(mode="json"),
            telegram_text=draft.telegram_html or (draft.format_result.telegram_html if draft.format_result else ""),
            post_type=post_type,
            compliance_flags={
                "decision": draft.publish_decision.model_dump(mode="json"),
                "format_result": draft.format_result.model_dump(mode="json") if draft.format_result else {},
                "issues": {
                    "unsupported_claims": draft.validation.unsupported_claims,
                    "investment_advice_flags": draft.validation.investment_advice_flags,
                    "hype_language_flags": draft.validation.hype_language_flags,
                    "formatting_issues": draft.validation.formatting_issues,
                },
            },
            factuality_score=1.0 if draft.validation.passed else 0.55,
            copy_similarity_score=0.1,
            status="draft" if draft.validation.passed else "needs_review",
            model_name=settings.openai_model if settings.openai_api_key else "local-fallback",
            prompt_version="foreign_v1",
        )
        session.add(summary)
        item.status = "summarized"
        session.add(
            AuditLog(
                event_type="foreign_summary_created",
                entity_type="raw_item",
                entity_id=item.id,
                payload_json={**scores, "post_type": post_type, "decision": draft.publish_decision.model_dump(mode="json")},
            )
        )
        session.commit()
        session.refresh(summary)
        return summary


def latest_pending_clusters(session: Session, limit: int = 10) -> list[ArticleCluster]:
    return list(session.scalars(select(ArticleCluster).order_by(ArticleCluster.updated_at.desc()).limit(limit)))


def _select_validated_text(original_text: str, validation: object) -> str:
    revised_text = getattr(validation, "revised_text", "") or ""
    if not revised_text.strip() or revised_text.strip() == original_text.strip():
        return original_text
    if getattr(validation, "pass_", False):
        return original_text
    return revised_text


def _is_foreign_item(item: RawItem) -> bool:
    source = item.source
    return (source.country or "").upper() not in {"", "KR"} or (source.language or "").lower().startswith("en")

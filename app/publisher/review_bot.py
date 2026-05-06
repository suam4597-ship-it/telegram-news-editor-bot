from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.llm.schemas import FactExtraction
from app.llm.summary_writer import SummaryWriter
from app.llm.validator import SummaryValidator
from app.models import AuditLog, PublishJob, Summary
from app.publisher.limits import check_publish_allowed
from app.publisher.formatter import format_admin_review, inline_review_keyboard
from app.publisher.telegram_client import TelegramClient, TelegramError
from app.services.post_policy import PostType


class ReviewService:
    def __init__(
        self,
        telegram: TelegramClient | None = None,
        summary_writer: SummaryWriter | None = None,
        validator: SummaryValidator | None = None,
    ):
        self.telegram = telegram or TelegramClient()
        self.summary_writer = summary_writer or SummaryWriter()
        self.validator = validator or SummaryValidator()

    async def send_summary_for_review(self, session: Session, summary: Summary) -> PublishJob | None:
        if not (self.telegram.available and settings.telegram_admin_channel_id):
            return None
        item = summary.cluster.representative_item
        source_name = item.source.name
        source_url = item.canonical_url
        text = format_admin_review(
            summary.id,
            summary.telegram_text or "",
            source_name,
            source_url,
            summary.post_type,
            metadata=self._review_metadata(summary),
        )
        response = await self.telegram.send_message(
            chat_id=settings.telegram_admin_channel_id,
            text=text,
            reply_markup=inline_review_keyboard(summary.id),
            disable_web_page_preview=True,
        )
        message = response["result"]
        job = PublishJob(
            summary_id=summary.id,
            channel_id=settings.telegram_public_channel_id or "",
            post_type=summary.post_type,
            admin_chat_id=str(settings.telegram_admin_channel_id),
            admin_message_id=str(message["message_id"]),
            status="pending_review",
        )
        session.add(job)
        session.add(AuditLog(event_type="review_sent", entity_type="summary", entity_id=summary.id, payload_json=response))
        session.commit()
        return job

    async def handle_update(self, session: Session, update: dict[str, Any]) -> dict[str, Any]:
        if "callback_query" in update:
            return await self._handle_callback(session, update["callback_query"])
        if "message" in update:
            return await self._handle_message(session, update["message"])
        return {"handled": False, "reason": "unsupported_update"}

    async def _handle_callback(self, session: Session, callback: dict[str, Any]) -> dict[str, Any]:
        data = callback.get("data") or ""
        callback_id = callback.get("id")
        message = callback.get("message") or {}
        chat_id = str((message.get("chat") or {}).get("id", ""))
        message_id = message.get("message_id")
        try:
            action, summary_id_text = data.split(":", 1)
            summary_id = int(summary_id_text)
        except ValueError:
            if callback_id:
                await self.telegram.answer_callback_query(callback_id, "알 수 없는 작업입니다.")
            return {"handled": False, "reason": "bad_callback_data"}

        summary = session.get(Summary, summary_id)
        if not summary:
            if callback_id:
                await self.telegram.answer_callback_query(callback_id, "초안을 찾을 수 없습니다.")
            return {"handled": False, "reason": "summary_not_found"}

        if action == "approve":
            result = await self._approve(session, summary)
            answer = result.get("message", "공개 채널에 발행했습니다.")
        elif action == "reject":
            summary.status = "rejected"
            result = {"status": "rejected"}
            answer = "반려했습니다."
        elif action == "shorten":
            result = await self._regenerate(session, summary, "short_link", chat_id=chat_id, message_id=message_id)
            answer = "짧은 링크형으로 바꿨습니다."
        elif action == "expand":
            result = await self._regenerate(session, summary, "editorial_brief", chat_id=chat_id, message_id=message_id)
            answer = "본문 설명형으로 바꿨습니다."
        elif action == "rewrite":
            target_post_type = summary.post_type if summary.post_type in {"short_link", "editorial_brief", "market_brief", "data_brief", "breaking"} else "editorial_brief"
            result = await self._regenerate(session, summary, target_post_type, chat_id=chat_id, message_id=message_id)
            answer = "같은 유형으로 다시 작성했습니다."
        elif action == "edit":
            summary.status = "edit_requested"
            result = {"status": "edit_requested"}
            answer = "이 초안 메시지에 답장으로 수정 문안을 보내주세요."
        else:
            result = {"status": "unknown_action"}
            answer = "알 수 없는 작업입니다."

        session.add(AuditLog(event_type=f"review_{action}", entity_type="summary", entity_id=summary.id, payload_json=result))
        session.commit()
        if callback_id:
            await self._answer_callback_safely(callback_id, answer)
        if action in {"approve", "reject"} and result.get("status") in {"published", "rejected"} and chat_id and message_id:
            await self.telegram.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=None)
        return {"handled": True, "action": action, "summary_id": summary.id, **result}

    async def _answer_callback_safely(self, callback_id: str, answer: str) -> None:
        try:
            await self.telegram.answer_callback_query(callback_id, answer)
        except TelegramError as exc:
            message = str(exc).lower()
            if "query is too old" in message or "query id is invalid" in message:
                return
            raise

    async def _approve(self, session: Session, summary: Summary) -> dict[str, Any]:
        if not settings.telegram_public_channel_id:
            summary.status = "approval_failed"
            raise RuntimeError("TELEGRAM_PUBLIC_CHANNEL_ID is not configured")
        gate = check_publish_allowed(session, summary, channel_id=settings.telegram_public_channel_id)
        if not gate.allowed:
            summary.status = "approval_blocked"
            job = session.scalar(
                select(PublishJob)
                .where(PublishJob.summary_id == summary.id)
                .order_by(PublishJob.created_at.desc())
            )
            if job:
                job.status = "blocked"
                job.error_message = gate.detail
            return {"status": gate.reason, "message": gate.detail}
        response = await self.telegram.send_message(
            chat_id=settings.telegram_public_channel_id,
            text=summary.telegram_text or "",
            disable_web_page_preview=False,
        )
        message_id = str(response["result"]["message_id"])
        summary.status = "published"
        job = session.scalar(
            select(PublishJob)
            .where(PublishJob.summary_id == summary.id)
            .order_by(PublishJob.created_at.desc())
        )
        if job:
            job.status = "published"
            job.post_type = summary.post_type
            job.published_at = datetime.now(UTC)
            job.telegram_message_id = message_id
        return {"status": "published", "telegram_message_id": message_id}

    async def _regenerate(
        self,
        session: Session,
        summary: Summary,
        post_type: PostType,
        *,
        chat_id: str,
        message_id: int | str | None,
    ) -> dict[str, Any]:
        item = summary.cluster.representative_item
        facts = FactExtraction.model_validate(summary.fact_json)
        output = await self.summary_writer.write(
            facts=facts,
            source_url=item.canonical_url,
            source_name=item.source.name,
            post_type=post_type,
        )
        validation = await self.validator.validate(facts=facts, telegram_text=output.telegram_text)
        summary.summary_json = output.model_dump(mode="json")
        summary.validation_json = validation.model_dump(mode="json", by_alias=True)
        summary.telegram_text = _select_validated_text(output.telegram_text, validation)
        summary.post_type = post_type
        summary.compliance_flags = {"issues": [issue.model_dump(mode="json") for issue in validation.issues]}
        summary.factuality_score = validation.factuality_score
        summary.copy_similarity_score = validation.copy_similarity_score
        summary.status = "draft" if validation.pass_ else "needs_review"
        session.add(summary)
        job = session.scalar(
            select(PublishJob)
            .where(PublishJob.summary_id == summary.id)
            .order_by(PublishJob.created_at.desc())
        )
        if job:
            job.post_type = post_type
        session.commit()
        if chat_id and message_id:
            text = format_admin_review(
                summary.id,
                summary.telegram_text or "",
                item.source.name,
                item.canonical_url,
                summary.post_type,
                metadata=self._review_metadata(summary),
            )
            try:
                await self.telegram.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    reply_markup=inline_review_keyboard(summary.id),
                    disable_web_page_preview=True,
                )
            except TelegramError as exc:
                if "message is not modified" not in str(exc).lower():
                    raise
        return {"status": "regenerated", "post_type": post_type}

    async def _handle_message(self, session: Session, message: dict[str, Any]) -> dict[str, Any]:
        reply_to = message.get("reply_to_message") or {}
        reply_message_id = reply_to.get("message_id")
        text = message.get("text") or message.get("caption")
        if not reply_message_id or not text:
            return {"handled": False, "reason": "not_a_text_reply"}
        job = session.scalar(select(PublishJob).where(PublishJob.admin_message_id == str(reply_message_id)))
        if not job:
            return {"handled": False, "reason": "no_matching_review_job"}
        summary = session.get(Summary, job.summary_id)
        if not summary:
            return {"handled": False, "reason": "summary_not_found"}
        summary.telegram_text = text
        summary.status = "draft"
        session.add(
            AuditLog(
                event_type="review_text_updated",
                entity_type="summary",
                entity_id=summary.id,
                message="Admin reply replaced telegram_text",
                payload_json={"admin_message_id": message.get("message_id")},
            )
        )
        session.commit()
        await self.send_summary_for_review(session, summary)
        return {"handled": True, "action": "text_updated", "summary_id": summary.id}

    def _review_metadata(self, summary: Summary) -> dict[str, str]:
        item = summary.cluster.representative_item
        source = item.source
        fact_json = summary.fact_json or {}
        entities = fact_json.get("entities") or {}
        market_relevance = fact_json.get("market_relevance") or {}
        options = source.options_json or {}

        related_values = [
            *(entities.get("companies") or [])[:3],
            *(entities.get("tickers") or [])[:3],
            *(market_relevance.get("sectors") or [])[:3],
            *(entities.get("assets") or [])[:2],
        ]
        related = ", ".join(dict.fromkeys(str(value) for value in related_values if value)) or "추출 전/확인 필요"

        issues = (summary.compliance_flags or {}).get("issues") or []
        if isinstance(issues, dict):
            risk_values = [key for key, value in issues.items() if value]
        else:
            risk_values = [
                str(issue.get("issue_type") or issue.get("message") or "검토 필요")
                for issue in issues
                if isinstance(issue, dict)
            ]
        risk_flags = ", ".join(dict.fromkeys(risk_values))
        if not risk_flags and source.commercial_use_status in {"unknown", "non_commercial_only", "link_only"}:
            risk_flags = f"소스 사용조건 확인({source.commercial_use_status})"
        if not risk_flags:
            risk_flags = "없음"

        return {
            "source_path": _source_path_label(source),
            "investment_lane": _investment_lane_label(item.raw_excerpt, options, source.category),
            "related": related,
            "risk_flags": risk_flags,
        }


def _source_path_label(source: Any) -> str:
    provider = (source.options_json or {}).get("provider")
    if provider:
        return str(provider)
    if source.source_type == "naver_news":
        return "Naver"
    if "CNBC" in source.name.upper():
        return "CNBC"
    if "NASDAQ" in source.name.upper():
        return "Nasdaq"
    return source.source_type


def _investment_lane_label(raw_excerpt: str | None, options: dict, category: str | None) -> str:
    if raw_excerpt:
        for line in raw_excerpt.splitlines():
            if line.startswith("투자 레인:"):
                return line.split(":", 1)[1].strip()
    lane = options.get("lane")
    if lane:
        return str(lane)
    return category or "auto"


def _select_validated_text(original_text: str, validation: Any) -> str:
    revised_text = getattr(validation, "revised_text", "") or ""
    if not revised_text.strip() or revised_text.strip() == original_text.strip():
        return original_text
    if getattr(validation, "pass_", False):
        return original_text
    return revised_text

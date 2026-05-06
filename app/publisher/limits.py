from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import PublishJob, Summary

SEOUL = ZoneInfo("Asia/Seoul")


@dataclass(slots=True)
class PublishGateResult:
    allowed: bool
    reason: str = "ok"
    detail: str = ""


def check_publish_allowed(
    session: Session,
    summary: Summary,
    *,
    channel_id: str,
    now: datetime | None = None,
) -> PublishGateResult:
    now_utc = now or datetime.now(UTC)
    if _daily_published_count(session, channel_id=channel_id, now=now_utc) >= settings.daily_public_post_limit:
        return PublishGateResult(False, "daily_limit", f"하루 발행 한도 {settings.daily_public_post_limit}개에 도달했습니다.")

    cooldown_minutes = _cooldown_minutes(summary)
    if cooldown_minutes > 0 and _has_recent_cluster_publish(session, summary, now_utc, cooldown_minutes):
        return PublishGateResult(False, "cluster_cooldown", f"같은 이슈는 {cooldown_minutes}분 쿨다운 이후 발행할 수 있습니다.")

    return PublishGateResult(True)


def _daily_published_count(session: Session, *, channel_id: str, now: datetime) -> int:
    local_now = now.astimezone(SEOUL)
    local_start = datetime.combine(local_now.date(), time.min, tzinfo=SEOUL)
    start_utc = local_start.astimezone(UTC)
    return int(
        session.scalar(
            select(func.count(PublishJob.id)).where(
                PublishJob.channel_id == channel_id,
                PublishJob.status == "published",
                PublishJob.published_at >= start_utc,
            )
        )
        or 0
    )


def _has_recent_cluster_publish(session: Session, summary: Summary, now: datetime, cooldown_minutes: int) -> bool:
    threshold = now - timedelta(minutes=cooldown_minutes)
    existing = session.scalar(
        select(PublishJob.id)
        .join(Summary, Summary.id == PublishJob.summary_id)
        .where(
            Summary.cluster_id == summary.cluster_id,
            Summary.id != summary.id,
            PublishJob.status == "published",
            PublishJob.published_at >= threshold,
        )
        .limit(1)
    )
    return existing is not None


def _cooldown_minutes(summary: Summary) -> int:
    item = summary.cluster.representative_item if summary.cluster else None
    source = item.source if item else None
    return int(getattr(source, "cooldown_minutes", None) or settings.default_cluster_cooldown_minutes)

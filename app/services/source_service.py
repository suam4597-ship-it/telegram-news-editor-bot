from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import SourceConfig, load_source_config
from app.models import Source


def seed_sources(session: Session, path: str | None = None) -> int:
    config = load_source_config(path)
    count = 0
    configured_names: set[str] = set()
    for item in config.sources:
        configured_names.add(item.name)
        upsert_source(session, item)
        count += 1
    if configured_names:
        stale_sources = session.scalars(select(Source).where(~Source.name.in_(configured_names)))
        for source in stale_sources:
            source.is_active = False
    session.commit()
    return count


def upsert_source(session: Session, item: SourceConfig) -> Source:
    source = session.scalar(select(Source).where(Source.name == item.name))
    if source is None:
        source = Source(name=item.name, source_type=item.type)
        session.add(source)
    source.source_type = item.type
    source.base_url = item.url
    source.feed_url = item.feed_url
    source.category = item.category
    source.country = item.country
    source.language = item.language
    source.reliability_score = item.reliability_score
    source.crawl_interval_minutes = item.crawl_interval_minutes
    source.license_status = item.license_status
    source.is_active = item.is_active and item.license_status != "blocked" and item.commercial_use_status != "blocked"
    source.crawl_mode = item.crawl_mode or item.type
    source.template_policy = item.template_policy
    source.requires_approval = item.requires_approval
    source.cooldown_minutes = item.cooldown_minutes
    source.commercial_use_status = item.commercial_use_status
    source.auto_publish_allowed = item.auto_publish_allowed and not item.requires_approval
    source.rate_limit_per_minute = item.rate_limit.requests_per_minute
    source.options_json = item.options
    session.flush()
    return source

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db import Base
from app.models import ArticleCluster, PublishJob, RawItem, Source, Summary
from app.publisher.limits import check_publish_allowed


def test_publish_gate_blocks_same_cluster_cooldown(monkeypatch) -> None:
    monkeypatch.setattr(settings, "daily_public_post_limit", 12)
    session = _session()
    source, item, cluster = _seed_cluster(session, cooldown_minutes=180)
    first = Summary(cluster_id=cluster.id, post_type="editorial_brief", telegram_text="first")
    second = Summary(cluster_id=cluster.id, post_type="editorial_brief", telegram_text="second")
    session.add_all([first, second])
    session.flush()
    session.add(
        PublishJob(
            summary_id=first.id,
            channel_id="@public",
            post_type="editorial_brief",
            status="published",
            published_at=datetime.now(UTC) - timedelta(minutes=20),
        )
    )
    session.commit()

    result = check_publish_allowed(session, second, channel_id="@public")

    assert result.allowed is False
    assert result.reason == "cluster_cooldown"
    assert source.id == item.source_id


def test_publish_gate_blocks_daily_limit(monkeypatch) -> None:
    monkeypatch.setattr(settings, "daily_public_post_limit", 1)
    session = _session()
    _, _, cluster = _seed_cluster(session, cooldown_minutes=0)
    first = Summary(cluster_id=cluster.id, post_type="short_link", telegram_text="first")
    second = Summary(cluster_id=cluster.id, post_type="short_link", telegram_text="second")
    session.add_all([first, second])
    session.flush()
    session.add(
        PublishJob(
            summary_id=first.id,
            channel_id="@public",
            post_type="short_link",
            status="published",
            published_at=datetime.now(UTC),
        )
    )
    session.commit()

    result = check_publish_allowed(session, second, channel_id="@public")

    assert result.allowed is False
    assert result.reason == "daily_limit"


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _seed_cluster(session, *, cooldown_minutes: int):
    source = Source(
        name="테스트",
        source_type="rss",
        category="stock",
        reliability_score=0.7,
        crawl_interval_minutes=30,
        license_status="link_only",
        is_active=True,
        cooldown_minutes=cooldown_minutes,
    )
    session.add(source)
    session.flush()
    item = RawItem(
        source_id=source.id,
        original_url="https://example.com/a",
        canonical_url="https://example.com/a",
        title="테스트 기사",
        status="summarized",
    )
    session.add(item)
    session.flush()
    cluster = ArticleCluster(representative_item_id=item.id, main_topic="테스트", cluster_hash="abc")
    session.add(cluster)
    session.commit()
    return source, item, cluster

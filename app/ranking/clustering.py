from __future__ import annotations

import re
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ArticleCluster, RawItem
from app.parsers.text_cleaner import clean_text

TOKEN_RE = re.compile(r"[A-Za-z0-9가-힣]+")
STOPWORDS = {"단독", "속보", "관련", "뉴스", "오늘", "시장"}


def cluster_key(title: str | None) -> str:
    tokens = [token.lower() for token in TOKEN_RE.findall(clean_text(title)) if token not in STOPWORDS]
    core = " ".join(sorted(tokens[:8]))
    return sha256(core.encode("utf-8")).hexdigest()


def get_or_create_cluster(
    session: Session,
    item: RawItem,
    importance_score: float,
    novelty_score: float,
    market_impact_score: float,
) -> ArticleCluster:
    key = cluster_key(item.title or item.canonical_url)
    existing = session.scalar(select(ArticleCluster).where(ArticleCluster.cluster_hash == key))
    if existing:
        existing.updated_at = item.fetched_at
        return existing
    cluster = ArticleCluster(
        main_topic=item.title,
        representative_item_id=item.id,
        cluster_hash=key,
        importance_score=importance_score,
        novelty_score=novelty_score,
        market_impact_score=market_impact_score,
    )
    session.add(cluster)
    session.flush()
    return cluster


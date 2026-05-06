from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx

from app.config import settings
from app.models import Source
from app.parsers.text_cleaner import make_excerpt, stable_hash
from app.parsers.url_normalizer import normalize_url


@dataclass(slots=True)
class CollectedItem:
    source_id: int
    source_name: str
    original_url: str
    canonical_url: str
    title: str | None
    author: str | None = None
    published_at: datetime | None = None
    excerpt: str | None = None
    content_text: str | None = None
    rejected_reason: str | None = None

    @property
    def title_hash(self) -> str:
        return stable_hash(self.title or "")

    @property
    def content_hash(self) -> str:
        return stable_hash(self.content_text or self.excerpt or self.title or self.canonical_url)


class CollectorError(RuntimeError):
    pass


class BaseCollector:
    def __init__(self, source: Source):
        self.source = source
        self.timeout = settings.request_timeout_seconds

    async def collect(self, limit: int = 10) -> list[CollectedItem]:
        raise NotImplementedError

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            headers={"User-Agent": settings.user_agent, "Accept": "text/html,application/xml;q=0.9,*/*;q=0.8"},
        )

    async def robots_allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        robots_url = urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))
        parser = RobotFileParser()
        parser.set_url(robots_url)
        try:
            async with self.client() as client:
                response = await client.get(robots_url)
            if response.status_code >= 400:
                return True
            parser.parse(response.text.splitlines())
            return parser.can_fetch(settings.user_agent, url)
        except httpx.HTTPError:
            return True

    def item_from_parts(
        self,
        original_url: str,
        title: str | None,
        content_text: str | None,
        author: str | None = None,
        published_at: datetime | None = None,
        canonical_url: str | None = None,
        rejected_reason: str | None = None,
    ) -> CollectedItem:
        canonical = normalize_url(canonical_url or original_url, base_url=self.source.base_url or self.source.feed_url)
        return CollectedItem(
            source_id=self.source.id,
            source_name=self.source.name,
            original_url=urljoin(self.source.base_url or self.source.feed_url or "", original_url),
            canonical_url=canonical,
            title=title,
            author=author,
            published_at=published_at,
            excerpt=make_excerpt(content_text),
            content_text=content_text,
            rejected_reason=rejected_reason,
        )


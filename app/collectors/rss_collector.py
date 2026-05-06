from __future__ import annotations

from datetime import datetime
from email.utils import parsedate_to_datetime

import feedparser

from app.collectors.base import BaseCollector, CollectedItem, CollectorError
from app.parsers.text_cleaner import clean_text
from app.parsers.url_normalizer import normalize_url


class RssCollector(BaseCollector):
    async def collect(self, limit: int = 10) -> list[CollectedItem]:
        if not self.source.feed_url:
            raise CollectorError(f"RSS source {self.source.name} has no feed_url")
        allowed = await self.robots_allowed(self.source.feed_url)
        self.source.robots_allowed = allowed
        if not allowed:
            return []

        async with self.client() as client:
            response = await client.get(self.source.feed_url, headers=_request_headers(self.source.options_json or {}))
            response.raise_for_status()

        parsed = feedparser.parse(response.content)
        items: list[CollectedItem] = []
        for entry in parsed.entries[:limit]:
            link = getattr(entry, "link", None)
            if not link:
                continue
            title = clean_text(getattr(entry, "title", None))
            summary = clean_text(getattr(entry, "summary", None))
            published_at = _entry_datetime(entry)
            canonical_url = normalize_url(link)
            items.append(
                CollectedItem(
                    source_id=self.source.id,
                    source_name=self.source.name,
                    original_url=link,
                    canonical_url=canonical_url,
                    title=title or None,
                    author=clean_text(getattr(entry, "author", None)) or None,
                    published_at=published_at,
                    excerpt=summary,
                    content_text=summary,
                )
            )
        return items


def _entry_datetime(entry: object) -> datetime | None:
    for attr in ("published", "updated", "created"):
        value = getattr(entry, attr, None)
        if value:
            try:
                return parsedate_to_datetime(value)
            except (TypeError, ValueError, IndexError):
                continue
    return None


def _request_headers(options: dict) -> dict[str, str] | None:
    headers = options.get("request_headers")
    if isinstance(headers, dict):
        return {str(key): str(value) for key, value in headers.items()}
    return None

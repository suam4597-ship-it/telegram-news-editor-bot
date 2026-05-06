from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

from app.collectors.base import BaseCollector, CollectedItem, CollectorError
from app.config import QueryPack, load_source_query_config, settings
from app.parsers.text_cleaner import clean_text, make_excerpt
from app.parsers.url_normalizer import normalize_url

NAVER_NEWS_API_URL = "https://openapi.naver.com/v1/search/news.json"
HTML_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(slots=True)
class ActiveQuery:
    pack: QueryPack
    query: str
    sort: str
    display: int
    exclude_domains: set[str]


class NaverNewsCollector(BaseCollector):
    async def collect(self, limit: int = 10) -> list[CollectedItem]:
        if not settings.naver_client_id or not settings.naver_client_secret:
            raise CollectorError("NAVER_CLIENT_ID and NAVER_CLIENT_SECRET must be configured for naver_news sources")

        active_queries = _active_queries(self.source.options_json or {}, limit=limit)
        if not active_queries:
            return []

        headers = {
            "X-Naver-Client-Id": settings.naver_client_id,
            "X-Naver-Client-Secret": settings.naver_client_secret,
            "User-Agent": settings.user_agent,
            "Accept": "application/json",
        }
        items: list[CollectedItem] = []
        seen_urls: set[str] = set()

        async with self.client() as client:
            for active_query in active_queries:
                if len(items) >= limit:
                    break
                response = await client.get(
                    NAVER_NEWS_API_URL,
                    headers=headers,
                    params={
                        "query": active_query.query,
                        "display": active_query.display,
                        "start": 1,
                        "sort": active_query.sort,
                    },
                )
                response.raise_for_status()
                for raw in response.json().get("items", []):
                    collected = self._item_from_naver_result(raw, active_query)
                    if collected is None or collected.canonical_url in seen_urls:
                        continue
                    seen_urls.add(collected.canonical_url)
                    items.append(collected)
                    if len(items) >= limit:
                        break

        return items

    def _item_from_naver_result(self, raw: dict, active_query: ActiveQuery) -> CollectedItem | None:
        original_url = raw.get("originallink") or raw.get("link")
        if not original_url:
            return None
        canonical_url = normalize_url(original_url)
        if _is_excluded_domain(canonical_url, active_query.exclude_domains):
            return None

        title = _clean_naver_text(raw.get("title"))
        description = _clean_naver_text(raw.get("description"))
        published_at = _parse_pub_date(raw.get("pubDate"))
        pack_label = active_query.pack.label or active_query.pack.name
        lane = active_query.pack.lane or active_query.pack.name
        excerpt = make_excerpt(
            "\n".join(
                part
                for part in (
                    f"투자 레인: {pack_label}",
                    f"검색어: {active_query.query}",
                    f"기사 설명: {description}",
                )
                if part
            )
        )

        return CollectedItem(
            source_id=self.source.id,
            source_name=self.source.name,
            original_url=original_url,
            canonical_url=canonical_url,
            title=title or None,
            author=None,
            published_at=published_at,
            excerpt=excerpt,
            content_text=f"{lane} {active_query.query} {description}",
        )


def _active_queries(source_options: dict, *, limit: int) -> list[ActiveQuery]:
    query_config_path = source_options.get("query_config_path")
    config = load_source_query_config(query_config_path)
    selected_pack_names = set(source_options.get("query_packs") or [])
    source_excluded_domains = {_normalize_domain(domain) for domain in source_options.get("exclude_domains", [])}
    active: list[ActiveQuery] = []

    for pack in config.query_packs:
        if not pack.enabled:
            continue
        if selected_pack_names and pack.name not in selected_pack_names:
            continue
        display = min(pack.max_results, config.defaults.display, max(limit, 1), 100)
        sort = pack.sort or config.defaults.sort
        exclude_domains = {
            *(_normalize_domain(domain) for domain in config.defaults.exclude_domains),
            *(_normalize_domain(domain) for domain in pack.exclude_domains),
            *source_excluded_domains,
        }
        for query in pack.queries:
            cleaned_query = clean_text(query)
            if not cleaned_query:
                continue
            active.append(
                ActiveQuery(
                    pack=pack,
                    query=cleaned_query,
                    sort=sort,
                    display=display,
                    exclude_domains={domain for domain in exclude_domains if domain},
                )
            )

    return active


def _clean_naver_text(value: str | None) -> str:
    return clean_text(HTML_TAG_RE.sub("", value or ""))


def _parse_pub_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None


def _is_excluded_domain(url: str, excluded_domains: set[str]) -> bool:
    domain = _normalize_domain(urlsplit(url).netloc)
    return any(domain == excluded or domain.endswith(f".{excluded}") for excluded in excluded_domains)


def _normalize_domain(domain: str) -> str:
    return domain.lower().strip().removeprefix("www.")

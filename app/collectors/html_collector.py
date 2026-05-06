from __future__ import annotations

from urllib.parse import urlsplit

from app.collectors.base import BaseCollector, CollectedItem, CollectorError
from app.parsers.article_parser import extract_listing_links, parse_article_html
from app.parsers.url_normalizer import normalize_url


class HtmlCollector(BaseCollector):
    async def collect(self, limit: int = 10) -> list[CollectedItem]:
        url = self.source.base_url
        if not url:
            raise CollectorError(f"HTML source {self.source.name} has no url/base_url")

        if not await self.robots_allowed(url):
            self.source.robots_allowed = False
            return []
        self.source.robots_allowed = True

        options = self.source.options_json or {}
        mode = options.get("mode") or ("listing" if self.source.crawl_mode == "html_listing" else "article")

        async with self.client() as client:
            response = await client.get(url)
            response.raise_for_status()
            html = response.text

            if mode == "listing":
                link_selector = options.get("link_selector")
                candidates = extract_listing_links(html, url, selector=link_selector, limit=limit * 3)
                candidates = [link for link in candidates if _same_domain(url, link)]
                items: list[CollectedItem] = []
                for article_url in candidates[:limit]:
                    if not await self.robots_allowed(article_url):
                        continue
                    article_response = await client.get(article_url)
                    if article_response.status_code >= 400:
                        continue
                    parsed = parse_article_html(article_response.text, article_url)
                    items.append(
                        CollectedItem(
                            source_id=self.source.id,
                            source_name=self.source.name,
                            original_url=article_url,
                            canonical_url=parsed.canonical_url,
                            title=parsed.title,
                            author=parsed.author,
                            published_at=parsed.published_at,
                            excerpt=parsed.excerpt,
                            content_text=parsed.text,
                            rejected_reason=parsed.rejected_reason,
                        )
                    )
                return items

        parsed = parse_article_html(html, url)
        return [
            CollectedItem(
                source_id=self.source.id,
                source_name=self.source.name,
                original_url=url,
                canonical_url=normalize_url(parsed.canonical_url),
                title=parsed.title,
                author=parsed.author,
                published_at=parsed.published_at,
                excerpt=parsed.excerpt,
                content_text=parsed.text,
                rejected_reason=parsed.rejected_reason,
            )
        ]


def _same_domain(base_url: str, candidate_url: str) -> bool:
    return urlsplit(base_url).netloc.lower().removeprefix("www.") == urlsplit(candidate_url).netloc.lower().removeprefix("www.")

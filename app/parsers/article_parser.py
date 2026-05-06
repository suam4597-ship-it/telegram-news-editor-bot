from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin

import trafilatura
from bs4 import BeautifulSoup

from app.parsers.text_cleaner import clean_text, contains_paywall_hint, make_excerpt
from app.parsers.url_normalizer import canonical_or_original


@dataclass(slots=True)
class ParsedArticle:
    title: str | None
    canonical_url: str
    author: str | None
    published_at: datetime | None
    text: str
    excerpt: str
    rejected_reason: str | None = None


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None


def _first_meta(soup: BeautifulSoup, *names: str) -> str | None:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return clean_text(tag["content"])
    return None


def parse_article_html(html: str, url: str, max_excerpt_chars: int = 500) -> ParsedArticle:
    soup = BeautifulSoup(html, "lxml")
    canonical_tag = soup.find("link", rel=lambda value: value and "canonical" in value)
    canonical_url = canonical_or_original(
        canonical_tag.get("href") if canonical_tag else None,
        original_url=url,
        base_url=url,
    )
    title = _first_meta(soup, "og:title", "twitter:title") or clean_text(soup.title.string if soup.title else "")
    author = _first_meta(soup, "author", "article:author")
    published_at = parse_datetime(
        _first_meta(
            soup,
            "article:published_time",
            "date",
            "pubdate",
            "publish_date",
            "DC.date.issued",
        )
    )
    extracted = trafilatura.extract(
        html,
        url=url,
        include_comments=False,
        include_tables=False,
        favor_precision=True,
    )
    text = clean_text(extracted or soup.get_text(" ", strip=True))
    rejected_reason = "paywall_or_login_detected" if contains_paywall_hint(text) else None
    return ParsedArticle(
        title=title or None,
        canonical_url=canonical_url,
        author=author,
        published_at=published_at,
        text=text,
        excerpt=make_excerpt(text, max_excerpt_chars),
        rejected_reason=rejected_reason,
    )


def extract_listing_links(html: str, page_url: str, selector: str | None = None, limit: int = 10) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    anchors = soup.select(selector) if selector else soup.find_all("a", href=True)
    links: list[str] = []
    for anchor in anchors:
        href = anchor.get("href")
        label = clean_text(anchor.get_text(" ", strip=True))
        if not href or len(label) < 4:
            continue
        absolute = urljoin(page_url, href)
        if absolute.startswith(("mailto:", "javascript:")):
            continue
        normalized = canonical_or_original(None, absolute, base_url=page_url)
        if normalized not in links:
            links.append(normalized)
        if len(links) >= limit:
            break
    return links


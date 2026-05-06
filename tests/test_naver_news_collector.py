from __future__ import annotations

import httpx
import pytest
import respx

from app.collectors.naver_news_collector import NAVER_NEWS_API_URL, NaverNewsCollector, _clean_naver_text
from app.config import settings
from app.models import Source


def test_clean_naver_text_strips_html_tags() -> None:
    assert _clean_naver_text("<b>삼성전자</b> 영업이익&nbsp;전망") == "삼성전자 영업이익 전망"


@pytest.mark.asyncio
@respx.mock
async def test_naver_news_collector_parses_api_response(tmp_path, monkeypatch) -> None:
    query_config = tmp_path / "source_queries.yml"
    query_config.write_text(
        """
defaults:
  sort: date
  display: 10
  exclude_domains:
    - blog.naver.com
query_packs:
  - name: domestic_earnings
    label: 국내 실적/가이던스
    lane: domestic_earnings
    max_results: 3
    queries:
      - 실적 영업이익 전망
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "naver_client_id", "client-id")
    monkeypatch.setattr(settings, "naver_client_secret", "client-secret")
    source = Source(
        id=1,
        name="Naver News - investment query packs",
        source_type="naver_news",
        category="stock",
        country="KR",
        reliability_score=0.72,
        options_json={"query_config_path": str(query_config), "query_packs": ["domestic_earnings"]},
    )
    respx.get(NAVER_NEWS_API_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {
                        "title": "<b>현대차</b> 영업이익 전망 상향",
                        "originallink": "https://example.com/news/1?utm_source=naver",
                        "link": "https://n.news.naver.com/mnews/article/001/1",
                        "description": "하반기 실적 개선 기대가 커졌습니다.",
                        "pubDate": "Wed, 06 May 2026 10:30:00 +0900",
                    }
                ]
            },
        )
    )

    items = await NaverNewsCollector(source).collect(limit=2)

    assert len(items) == 1
    assert items[0].title == "현대차 영업이익 전망 상향"
    assert items[0].canonical_url == "https://example.com/news/1"
    assert "투자 레인: 국내 실적/가이던스" in (items[0].excerpt or "")
    assert "검색어: 실적 영업이익 전망" in (items[0].excerpt or "")

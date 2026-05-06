from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.collectors.base import BaseCollector, CollectedItem, CollectorError
from app.config import settings
from app.parsers.text_cleaner import clean_text
from app.parsers.url_normalizer import normalize_url

DART_LIST_URL = "https://opendart.fss.or.kr/api/list.json"
DART_VIEWER_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"


class DartCollector(BaseCollector):
    async def collect(self, limit: int = 10) -> list[CollectedItem]:
        if not settings.opendart_api_key:
            raise CollectorError("OPENDART_API_KEY is required for DartCollector")
        options = self.source.options_json or {}
        days_back = int(options.get("days_back", 1))
        page_count = min(int(options.get("page_count", limit)), 100)
        end_date = datetime.now(UTC).date()
        begin_date = end_date - timedelta(days=days_back)

        params = {
            "crtfc_key": settings.opendart_api_key,
            "bgn_de": begin_date.strftime("%Y%m%d"),
            "end_de": end_date.strftime("%Y%m%d"),
            "page_no": 1,
            "page_count": min(page_count, limit),
            "sort": "date",
            "sort_mth": "desc",
        }
        async with self.client() as client:
            response = await client.get(DART_LIST_URL, params=params)
            response.raise_for_status()
            payload = response.json()

        if payload.get("status") not in (None, "000"):
            raise CollectorError(f"OpenDART error {payload.get('status')}: {payload.get('message')}")

        items: list[CollectedItem] = []
        for disclosure in payload.get("list", [])[:limit]:
            rcept_no = disclosure.get("rcept_no")
            if not rcept_no:
                continue
            viewer_url = DART_VIEWER_URL.format(rcept_no=rcept_no)
            report_name = clean_text(disclosure.get("report_nm"))
            corp_name = clean_text(disclosure.get("corp_name"))
            title = f"{corp_name} {report_name}".strip()
            received_date = _dart_date(disclosure.get("rcept_dt"))
            text = clean_text(
                " / ".join(
                    part
                    for part in [
                        f"회사: {corp_name}",
                        f"종목코드: {disclosure.get('stock_code') or '없음'}",
                        f"공시명: {report_name}",
                        f"접수일: {disclosure.get('rcept_dt')}",
                        f"비고: {disclosure.get('rm') or ''}",
                    ]
                    if part
                )
            )
            items.append(
                CollectedItem(
                    source_id=self.source.id,
                    source_name=self.source.name,
                    original_url=viewer_url,
                    canonical_url=normalize_url(viewer_url),
                    title=title or None,
                    author=clean_text(disclosure.get("flr_nm")) or None,
                    published_at=received_date,
                    excerpt=text,
                    content_text=text,
                )
            )
        return items


def _dart_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%d").replace(tzinfo=UTC)
    except ValueError:
        return None


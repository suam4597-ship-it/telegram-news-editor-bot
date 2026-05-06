from app.collectors.base import BaseCollector
from app.collectors.dart_collector import DartCollector
from app.collectors.html_collector import HtmlCollector
from app.collectors.naver_news_collector import NaverNewsCollector
from app.collectors.rss_collector import RssCollector
from app.models import Source


def collector_for(source: Source) -> BaseCollector:
    match source.source_type:
        case "rss":
            return RssCollector(source)
        case "html":
            return HtmlCollector(source)
        case "dart":
            return DartCollector(source)
        case "naver_news":
            return NaverNewsCollector(source)
        case _:
            raise ValueError(f"Unsupported source type: {source.source_type}")

from app.models import RawItem, Source
from app.services.post_policy import select_post_type, should_skip_item


def test_select_post_type_short_link_for_simple_news() -> None:
    source = Source(name="테스트 RSS", source_type="rss", category="stock", template_policy="auto")
    item = RawItem(
        source_id=1,
        original_url="https://example.com/a",
        canonical_url="https://example.com/a",
        title="기업 행사 소식",
        raw_excerpt="기업이 행사를 열었다.",
    )
    assert select_post_type(item, source, {"importance_score": 40, "market_impact_score": 0}) == "short_link"


def test_select_post_type_editorial_for_numeric_stock_issue() -> None:
    source = Source(name="테스트 RSS", source_type="rss", category="stock", template_policy="auto")
    item = RawItem(
        source_id=1,
        original_url="https://example.com/a",
        canonical_url="https://example.com/a",
        title="현대차 영업이익 12조 전망",
        raw_excerpt="하반기 실적 개선과 가이던스 변화가 체크포인트다.",
    )
    assert select_post_type(item, source, {"importance_score": 78, "market_impact_score": 60}) == "editorial_brief"


def test_select_post_type_data_for_dart() -> None:
    source = Source(name="DART", source_type="dart", category="disclosure", template_policy="auto")
    item = RawItem(
        source_id=1,
        original_url="https://example.com/a",
        canonical_url="https://example.com/a",
        title="신규 시설투자 공시",
    )
    assert select_post_type(item, source, {"importance_score": 95, "market_impact_score": 80}) == "data_brief"


def test_naver_investment_article_routes_to_editorial() -> None:
    source = Source(name="Naver News", source_type="naver_news", category="stock", country="KR", template_policy="auto")
    item = RawItem(
        source_id=1,
        original_url="https://example.com/a",
        canonical_url="https://example.com/a",
        title="현대차 영업이익 전망 상향",
        raw_excerpt="투자 레인: 국내 실적/가이던스 기사 설명: 하반기 실적 개선 기대",
    )
    scores = {"importance_score": 72, "market_impact_score": 60}
    assert select_post_type(item, source, scores) == "editorial_brief"
    assert should_skip_item(item, source, scores) is None


def test_foreign_article_without_connection_is_skipped() -> None:
    source = Source(name="CNBC Lifestyle RSS", source_type="rss", category="foreign_rss", country="US", template_policy="auto")
    item = RawItem(
        source_id=1,
        original_url="https://example.com/a",
        canonical_url="https://example.com/a",
        title="Restaurant chain launches new menu",
        raw_excerpt="A consumer lifestyle story without market or sector signal.",
    )
    assert should_skip_item(item, source, {"importance_score": 32, "market_impact_score": 10}) is not None


def test_chart_signal_article_is_skipped() -> None:
    source = Source(name="Naver News", source_type="naver_news", category="stock", country="KR", template_policy="auto")
    item = RawItem(
        source_id=1,
        original_url="https://example.com/a",
        canonical_url="https://example.com/a",
        title="MK시그널 골든크로스 종목 수익률 공개",
        raw_excerpt="매수신호와 목표가 중심의 차트 콘텐츠입니다.",
    )
    assert should_skip_item(item, source, {"importance_score": 80, "market_impact_score": 70}) == "low_quality_investment_signal"

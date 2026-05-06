from app.parsers.article_parser import extract_listing_links, parse_article_html


def test_parse_article_html_extracts_metadata() -> None:
    html = """
    <html>
      <head>
        <title>시장 금리 변화</title>
        <link rel="canonical" href="https://example.com/news/1?utm_source=x">
        <meta property="article:published_time" content="2026-05-06T09:00:00+09:00">
      </head>
      <body><article><p>한국 시장 금리가 움직였습니다. 다음 지표 확인이 필요합니다.</p></article></body>
    </html>
    """
    article = parse_article_html(html, "https://example.com/news/1")
    assert article.title == "시장 금리 변화"
    assert article.canonical_url == "https://example.com/news/1"
    assert "한국 시장 금리" in article.text


def test_extract_listing_links() -> None:
    html = '<a href="/a">거시경제 기사</a><a href="/news/1?utm_source=x">시장 금리 기사</a>'
    assert extract_listing_links(html, "https://example.com/list") == [
        "https://example.com/a",
        "https://example.com/news/1",
    ]

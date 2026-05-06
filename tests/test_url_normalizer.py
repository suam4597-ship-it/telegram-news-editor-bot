from app.parsers.url_normalizer import normalize_url


def test_normalize_url_removes_tracking_and_fragment() -> None:
    url = "HTTPS://M.Example.com:443/news/amp/?utm_source=x&b=2&a=1&fbclid=abc#section"
    assert normalize_url(url) == "https://example.com/news?a=1&b=2"


def test_normalize_url_joins_base_url() -> None:
    assert normalize_url("/article?id=1&utm_medium=social", "https://example.com/list") == "https://example.com/article?id=1"


from pathlib import Path

from app.config import load_source_config, load_source_query_config


def test_load_source_config(tmp_path: Path) -> None:
    config_file = tmp_path / "sources.yml"
    config_file.write_text(
        """
sources:
  - name: Test RSS
    type: rss
    feed_url: https://example.com/rss
    license_status: link_only
    is_active: true
""",
        encoding="utf-8",
    )
    config = load_source_config(config_file)
    assert config.sources[0].name == "Test RSS"
    assert config.sources[0].feed_url == "https://example.com/rss"
    assert config.sources[0].rate_limit.requests_per_minute == 10
    assert config.sources[0].template_policy == "auto"
    assert config.sources[0].requires_approval is True
    assert config.sources[0].cooldown_minutes == 180


def test_load_naver_source_config(tmp_path: Path) -> None:
    config_file = tmp_path / "sources.yml"
    config_file.write_text(
        """
sources:
  - name: Naver News
    type: naver_news
    license_status: link_only
    is_active: true
    options:
      query_packs:
        - domestic_earnings
""",
        encoding="utf-8",
    )
    config = load_source_config(config_file)
    assert config.sources[0].type == "naver_news"
    assert config.sources[0].options["query_packs"] == ["domestic_earnings"]


def test_load_source_query_config(tmp_path: Path) -> None:
    config_file = tmp_path / "source_queries.yml"
    config_file.write_text(
        """
defaults:
  sort: date
  display: 10
query_packs:
  - name: domestic_earnings
    label: 국내 실적/가이던스
    queries:
      - 실적 영업이익 전망
""",
        encoding="utf-8",
    )
    config = load_source_query_config(config_file)
    assert config.query_packs[0].name == "domestic_earnings"
    assert config.query_packs[0].queries == ["실적 영업이익 전망"]

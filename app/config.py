from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"
    database_url: str = "postgresql+psycopg://newsbot:newsbot@postgres:5432/newsbot"
    redis_url: str = "redis://redis:6379/0"

    openai_api_key: str | None = None
    openai_model: str = "gpt-5.4-mini"

    naver_client_id: str | None = None
    naver_client_secret: str | None = None

    telegram_bot_token: str | None = None
    telegram_admin_channel_id: str | None = None
    telegram_public_channel_id: str | None = None
    telegram_webhook_secret: str | None = None

    opendart_api_key: str | None = None

    user_agent: str = "TelegramNewsEditorBot/0.1 contact@example.com"
    source_config_path: str = "config/sources.yml"
    source_query_config_path: str = "config/source_queries.yml"
    style_guide_path: str = "config/style_guide.yml"
    request_timeout_seconds: float = 10.0
    daily_public_post_limit: int = 12
    default_cluster_cooldown_minutes: int = 180

    @property
    def is_test(self) -> bool:
        return self.app_env.lower() == "test"


settings = Settings()


class RateLimitConfig(BaseModel):
    requests_per_minute: int = Field(default=10, ge=1)


class SourceConfig(BaseModel):
    name: str
    type: Literal["rss", "html", "dart", "naver_news"]
    url: str | None = None
    feed_url: str | None = None
    category: str = "macro"
    country: str | None = None
    language: str = "ko"
    reliability_score: float = Field(default=0.7, ge=0, le=1)
    crawl_interval_minutes: int = Field(default=30, ge=1)
    license_status: Literal["allowed", "licensed", "link_only", "blocked", "unknown"] = "unknown"
    is_active: bool = True
    crawl_mode: Literal["rss", "html_article", "html_listing", "api", "dart", "naver_news"] | None = None
    template_policy: Literal["auto", "short_link", "editorial_brief", "market_brief", "data_brief", "breaking"] = "auto"
    requires_approval: bool = True
    cooldown_minutes: int = Field(default=180, ge=0)
    commercial_use_status: Literal["allowed", "licensed", "non_commercial_only", "link_only", "blocked", "unknown"] = "unknown"
    auto_publish_allowed: bool = False
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    options: dict[str, Any] = Field(default_factory=dict)

    @field_validator("url", "feed_url")
    @classmethod
    def empty_to_none(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            return None
        return value


class SourceConfigFile(BaseModel):
    sources: list[SourceConfig] = Field(default_factory=list)


class QueryDefaults(BaseModel):
    sort: Literal["date", "sim"] = "date"
    display: int = Field(default=10, ge=1, le=100)
    exclude_domains: list[str] = Field(default_factory=list)


class QueryPack(BaseModel):
    name: str
    label: str | None = None
    lane: str | None = None
    language: str = "ko"
    enabled: bool = True
    search_interval_minutes: int = Field(default=30, ge=1)
    max_results: int = Field(default=5, ge=1, le=100)
    sort: Literal["date", "sim"] | None = None
    queries: list[str] = Field(default_factory=list)
    exclude_domains: list[str] = Field(default_factory=list)


class SourceQueryConfigFile(BaseModel):
    defaults: QueryDefaults = Field(default_factory=QueryDefaults)
    query_packs: list[QueryPack] = Field(default_factory=list)


class StyleGuide(BaseModel):
    disclaimer: str = "※ 정보 제공 목적, 투자 권유 아님"
    max_telegram_chars: int = 4096
    summary_max_chars: int = 700
    max_excerpt_chars: int = 500
    forbidden_phrases: list[str] = Field(default_factory=list)
    ai_phrases: list[str] = Field(default_factory=list)
    default_tags: list[str] = Field(default_factory=list)


def _load_yaml(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {}
    with target.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_source_config(path: str | Path | None = None) -> SourceConfigFile:
    return SourceConfigFile.model_validate(_load_yaml(path or settings.source_config_path))


def load_source_query_config(path: str | Path | None = None) -> SourceQueryConfigFile:
    return SourceQueryConfigFile.model_validate(_load_yaml(path or settings.source_query_config_path))


@lru_cache(maxsize=8)
def load_style_guide(path: str | Path | None = None) -> StyleGuide:
    return StyleGuide.model_validate(_load_yaml(path or settings.style_guide_path))

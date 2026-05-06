from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db import Base

JsonType = JSON().with_variant(JSONB, "postgresql")


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    base_url: Mapped[str | None] = mapped_column(Text)
    feed_url: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(80))
    country: Mapped[str | None] = mapped_column(String(20))
    language: Mapped[str] = mapped_column(String(10), default="ko", nullable=False)
    reliability_score: Mapped[float] = mapped_column(Float, default=0.7, nullable=False)
    crawl_interval_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    robots_allowed: Mapped[bool | None] = mapped_column(Boolean)
    license_status: Mapped[str] = mapped_column(String(30), default="unknown", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    crawl_mode: Mapped[str | None] = mapped_column(String(40))
    template_policy: Mapped[str] = mapped_column(String(40), default="auto", nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    cooldown_minutes: Mapped[int] = mapped_column(Integer, default=180, nullable=False)
    commercial_use_status: Mapped[str] = mapped_column(String(40), default="unknown", nullable=False)
    auto_publish_allowed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    options_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    last_crawled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    raw_items = relationship("RawItem", back_populates="source")

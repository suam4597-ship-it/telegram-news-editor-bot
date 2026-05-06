from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class RawItem(Base):
    __tablename__ = "raw_items"
    __table_args__ = (UniqueConstraint("canonical_url", name="uq_raw_items_canonical_url"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False)
    original_url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    content_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    title_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    raw_excerpt: Mapped[str | None] = mapped_column(Text)
    full_text_stored: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="fetched", nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text)

    source = relationship("Source", back_populates="raw_items")
    cluster = relationship("ArticleCluster", back_populates="representative_item", uselist=False)


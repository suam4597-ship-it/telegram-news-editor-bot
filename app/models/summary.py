from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db import Base

JsonType = JSON().with_variant(JSONB, "postgresql")


class Summary(Base):
    __tablename__ = "summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("article_clusters.id"), nullable=False)
    fact_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    summary_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    validation_json: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    telegram_text: Mapped[str | None] = mapped_column(Text)
    post_type: Mapped[str] = mapped_column(String(40), default="editorial_brief", nullable=False)
    compliance_flags: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    factuality_score: Mapped[float | None] = mapped_column(Float)
    copy_similarity_score: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(120))
    prompt_version: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    cluster = relationship("ArticleCluster", back_populates="summaries")
    publish_jobs = relationship("PublishJob", back_populates="summary")

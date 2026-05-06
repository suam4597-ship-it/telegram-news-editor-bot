from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class ArticleCluster(Base):
    __tablename__ = "article_clusters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    main_topic: Mapped[str | None] = mapped_column(Text)
    representative_item_id: Mapped[int | None] = mapped_column(ForeignKey("raw_items.id"))
    cluster_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    importance_score: Mapped[float | None] = mapped_column(Float)
    novelty_score: Mapped[float | None] = mapped_column(Float)
    market_impact_score: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    representative_item = relationship("RawItem", back_populates="cluster")
    summaries = relationship("Summary", back_populates="cluster")


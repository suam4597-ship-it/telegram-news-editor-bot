from __future__ import annotations

import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.db import SessionLocal
from app.services.pipeline import NewsPipeline


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Asia/Seoul")
    pipeline = NewsPipeline()

    async def collect_job() -> None:
        with SessionLocal() as session:
            await pipeline.collect_once(session)

    async def draft_job() -> None:
        with SessionLocal() as session:
            await pipeline.draft_once(session, limit=3)

    scheduler.add_job(lambda: asyncio.create_task(collect_job()), "interval", minutes=10, id="collect_once")
    scheduler.add_job(lambda: asyncio.create_task(draft_job()), "interval", minutes=20, id="draft_once")
    for job_id, hour, minute in [
        ("morning_check", 8, 10),
        ("morning_issue", 10, 30),
        ("lunch_digest", 12, 20),
        ("market_close", 15, 50),
        ("us_preview", 21, 30),
    ]:
        scheduler.add_job(
            lambda: asyncio.create_task(draft_job()),
            "cron",
            day_of_week="mon-fri",
            hour=hour,
            minute=minute,
            id=job_id,
        )
    return scheduler

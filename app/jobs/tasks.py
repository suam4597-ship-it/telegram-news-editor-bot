from __future__ import annotations

import asyncio
from dataclasses import asdict

from app.db import SessionLocal
from app.services.pipeline import NewsPipeline


def collect_once_job(limit: int = 10) -> dict:
    async def run() -> dict:
        with SessionLocal() as session:
            result = await NewsPipeline().collect_once(session, limit=limit)
            return asdict(result)

    return asyncio.run(run())


def draft_once_job(limit: int = 3) -> dict:
    async def run() -> dict:
        with SessionLocal() as session:
            result = await NewsPipeline().draft_once(session, limit=limit)
            return asdict(result)

    return asyncio.run(run())

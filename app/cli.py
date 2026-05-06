from __future__ import annotations

import asyncio
from dataclasses import asdict

import typer
from rich.console import Console
from sqlalchemy import select

from app.collectors.registry import collector_for
from app.db import SessionLocal, init_db as create_tables
from app.models import Source, Summary
from app.publisher.review_bot import ReviewService
from app.publisher.telegram_client import TelegramClient
from app.services.pipeline import NewsPipeline
from app.services.source_service import seed_sources as seed_source_config

app = typer.Typer(help="Telegram economic news editor bot CLI")
console = Console()


@app.command("init-db")
def init_db_command() -> None:
    create_tables()
    console.print("[green]DB tables are ready.[/green]")


@app.command("seed-sources")
def seed_sources(path: str | None = typer.Option(None, help="Path to sources.yml")) -> None:
    with SessionLocal() as session:
        count = seed_source_config(session, path)
    console.print(f"[green]Seeded {count} sources.[/green]")


@app.command("check-source")
def check_source(source_id: int, limit: int = typer.Option(3, min=1, max=20)) -> None:
    async def run() -> None:
        with SessionLocal() as session:
            source = session.get(Source, source_id)
            if not source:
                raise typer.BadParameter(f"Source {source_id} not found")
            items = await collector_for(source).collect(limit=limit)
            console.print(f"[green]Collected preview: {len(items)} items[/green]")
            for item in items:
                console.print({"title": item.title, "url": item.canonical_url, "rejected": item.rejected_reason})

    asyncio.run(run())


@app.command("collect-once")
def collect_once(
    source_id: int | None = typer.Option(None, help="Only collect one source id"),
    limit: int = typer.Option(10, min=1, max=100),
) -> None:
    async def run() -> None:
        with SessionLocal() as session:
            result = await NewsPipeline().collect_once(session, source_id=source_id, limit=limit)
            console.print(asdict(result))

    asyncio.run(run())


@app.command("draft-once")
def draft_once(limit: int = typer.Option(3, min=1, max=20)) -> None:
    async def run() -> None:
        with SessionLocal() as session:
            result = await NewsPipeline().draft_once(session, limit=limit)
            console.print(asdict(result))

    asyncio.run(run())


@app.command("send-test")
def send_test(message: str) -> None:
    async def run() -> None:
        from app.config import settings

        if not settings.telegram_admin_channel_id:
            raise typer.BadParameter("TELEGRAM_ADMIN_CHANNEL_ID is not configured")
        result = await TelegramClient().send_message(chat_id=settings.telegram_admin_channel_id, text=message)
        console.print(result)

    asyncio.run(run())


@app.command("requeue-summary")
def requeue_summary(summary_id: int) -> None:
    async def run() -> None:
        with SessionLocal() as session:
            summary = session.get(Summary, summary_id)
            if not summary:
                raise typer.BadParameter(f"Summary {summary_id} not found")
            job = await ReviewService().send_summary_for_review(session, summary)
            console.print({"summary_id": summary.id, "review_job_id": job.id if job else None})

    asyncio.run(run())


@app.command("list-sources")
def list_sources() -> None:
    with SessionLocal() as session:
        sources = session.scalars(select(Source).order_by(Source.id)).all()
        for source in sources:
            console.print(
                {
                    "id": source.id,
                    "name": source.name,
                    "type": source.source_type,
                    "active": source.is_active,
                    "license": source.license_status,
                    "commercial_use": source.commercial_use_status,
                    "template": source.template_policy,
                    "approval": source.requires_approval,
                }
            )


if __name__ == "__main__":
    app()

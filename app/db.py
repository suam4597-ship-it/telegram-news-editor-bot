from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    ensure_operational_columns()


def ensure_operational_columns() -> None:
    """Add small MVP columns when an existing local DB predates the model."""
    additions = {
        "sources": {
            "crawl_mode": "VARCHAR(40)",
            "template_policy": "VARCHAR(40) DEFAULT 'auto' NOT NULL",
            "requires_approval": "BOOLEAN DEFAULT TRUE NOT NULL",
            "cooldown_minutes": "INTEGER DEFAULT 180 NOT NULL",
            "commercial_use_status": "VARCHAR(40) DEFAULT 'unknown' NOT NULL",
            "auto_publish_allowed": "BOOLEAN DEFAULT FALSE NOT NULL",
        },
        "summaries": {
            "post_type": "VARCHAR(40) DEFAULT 'editorial_brief' NOT NULL",
        },
        "publish_jobs": {
            "post_type": "VARCHAR(40)",
        },
    }
    with engine.begin() as connection:
        inspector = inspect(connection)
        existing_tables = set(inspector.get_table_names())
        for table_name, columns in additions.items():
            if table_name not in existing_tables:
                continue
            existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, sql_type in columns.items():
                if column_name not in existing_columns:
                    connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {sql_type}"))

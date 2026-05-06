from __future__ import annotations

from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RawItem
from app.parsers.text_cleaner import clean_text, stable_hash


def title_hash(title: str | None) -> str:
    return stable_hash(clean_text(title))


def content_hash(text: str | None) -> str:
    return stable_hash(clean_text(text))


def title_similarity(left: str | None, right: str | None) -> float:
    return SequenceMatcher(None, clean_text(left).lower(), clean_text(right).lower()).ratio()


def find_existing_duplicate(session: Session, canonical_url: str, title: str | None, content_hash_value: str) -> RawItem | None:
    existing = session.scalar(select(RawItem).where(RawItem.canonical_url == canonical_url))
    if existing:
        return existing
    existing = session.scalar(select(RawItem).where(RawItem.content_hash == content_hash_value))
    if existing:
        return existing
    if title:
        incoming_title_hash = title_hash(title)
        return session.scalar(select(RawItem).where(RawItem.title_hash == incoming_title_hash))
    return None


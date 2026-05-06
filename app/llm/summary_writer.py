from __future__ import annotations

import html
import re

from app.config import load_style_guide
from app.llm.client import OpenAIResponsesClient
from app.llm.prompt_loader import load_prompt
from app.llm.schemas import SUMMARY_SCHEMA, FactExtraction, SummaryOutput
from app.parsers.text_cleaner import clean_text, make_excerpt
from app.publisher.formatter import format_source_link, truncate_telegram_text
from app.services.post_policy import PostType

READABLE_SECTION_MARKERS = ("📍 핵심 포인트", "📍 시장에서 볼 부분", "🔎 체크 포인트")
BLANK_LINES_RE = re.compile(r"\n{3,}")


class SummaryWriter:
    def __init__(self, client: OpenAIResponsesClient | None = None):
        self.client = client or OpenAIResponsesClient()

    async def write(
        self,
        *,
        facts: FactExtraction,
        source_url: str,
        source_name: str,
        post_type: PostType = "editorial_brief",
    ) -> SummaryOutput:
        if post_type == "short_link" or not self.client.available:
            return _build_template_output(facts=facts, source_url=source_url, source_name=source_name, post_type=post_type)

        prompt = load_prompt("summary_writer_v1.md").format(
            fact_json=facts.model_dump_json(ensure_ascii=False),
            source_url=source_url,
            source_name=source_name,
            post_type=post_type,
        )
        payload = await self.client.structured_json(
            schema_name="summary_output",
            schema=SUMMARY_SCHEMA,
            prompt=prompt,
            instructions="Write polished Korean Telegram market notes in the exact requested visual format.",
        )
        output = SummaryOutput.model_validate(payload).model_copy(update={"post_type": post_type})
        if not _looks_readable(output.telegram_text):
            return _build_template_output(facts=facts, source_url=source_url, source_name=source_name, post_type=post_type)
        return output.model_copy(update={"telegram_text": _normalize_message(output.telegram_text)})


def _build_template_output(
    *,
    facts: FactExtraction,
    source_url: str,
    source_name: str,
    post_type: PostType,
) -> SummaryOutput:
    guide = load_style_guide()
    title = _title_for(facts, post_type)
    tags = _tags_for(facts)
    source_line = f"출처: {format_source_link(source_name, source_url)}"
    disclaimer = html.escape(guide.disclaimer)

    if post_type == "short_link":
        body = (
            f"<b>{html.escape(title)}</b>\n\n"
            f"{source_line}\n"
            f"{disclaimer}"
        )
        return SummaryOutput(
            telegram_text=truncate_telegram_text(_normalize_message(body)),
            short_title=title,
            tags=tags,
            risk_level="low",
            post_type=post_type,
        )

    if post_type == "breaking":
        body = (
            f"<b>속보: {html.escape(title)}</b>\n\n"
            f"{html.escape(make_excerpt(facts.main_event, 120))}\n\n"
            "시장 영향은 아직 확인 중입니다. 세부 내용이 나오면 추가로 점검하겠습니다.\n\n"
            f"{source_line}\n"
            f"{disclaimer}"
        )
        return SummaryOutput(
            telegram_text=truncate_telegram_text(_normalize_message(body)),
            short_title=title,
            tags=tags,
            risk_level="high",
            post_type=post_type,
        )

    section_title = "시장에서 볼 부분" if post_type == "market_brief" else "핵심 포인트"
    body = (
        f"<b>{html.escape(title)}</b>\n\n"
        f"{html.escape(make_excerpt(facts.main_event, 140))}\n\n"
        f"📍 {section_title}\n"
        f"{_bullet_block(_fact_points(facts))}\n\n"
        f"{_domestic_connection_block(facts=facts, source_name=source_name)}"
        "🔎 체크 포인트\n"
        f"{_bullet_block(_check_points(facts))}\n\n"
        "💬 시사점\n"
        f"{html.escape(_implication_for(facts, post_type))}\n\n"
        f"{' '.join(tags)}\n\n"
        f"{source_line}\n"
        f"{disclaimer}"
    )
    return SummaryOutput(
        telegram_text=truncate_telegram_text(_normalize_message(body), max_chars=guide.summary_max_chars),
        short_title=title,
        tags=tags,
        risk_level="medium",
        post_type=post_type,
    )


def _title_for(facts: FactExtraction, post_type: PostType) -> str:
    title = clean_text(facts.title or facts.main_event)
    title = title.removeprefix("속보:").strip()
    limit = 38 if post_type == "short_link" else 34
    return make_excerpt(title, limit)


def _fact_points(facts: FactExtraction) -> list[str]:
    points = [fact.fact for fact in facts.key_facts if clean_text(fact.fact)]
    if not points and clean_text(facts.main_event):
        points.append(facts.main_event)
    return [_sentence(point, 105) for point in points[:3]]


def _check_points(facts: FactExtraction) -> list[str]:
    points = [value for value in facts.risks_or_uncertainties if clean_text(value)]
    if not points:
        points = ["원문과 후속 보도에서 숫자, 일정, 관련 섹터를 같이 확인해야 합니다."]
    return [_sentence(point, 105) for point in points[:2]]


def _implication_for(facts: FactExtraction, post_type: PostType) -> str:
    sectors = ", ".join(facts.market_relevance.sectors[:3])
    direction = facts.market_relevance.impact_direction
    if post_type == "market_brief":
        return "방향을 단정하기보다 금리, 환율, 섹터 수급이 같은 방향으로 움직이는지 보는 쪽이 좋습니다."
    if sectors:
        return f"{sectors} 관련주는 숫자와 일정이 실제 기대치에 반영되는지 확인하는 흐름입니다."
    if direction and direction != "unclear":
        return "단기 반응보다 후속 숫자와 확인 가능한 이벤트가 이어지는지가 더 중요합니다."
    return "아직은 발췌 기준의 정보라 원문 확인과 후속 보도가 필요합니다."


def _domestic_connection_block(*, facts: FactExtraction, source_name: str) -> str:
    foreign_source = any(name in source_name.lower() for name in ("cnbc", "nasdaq"))
    if not foreign_source:
        return ""
    sectors = ", ".join(facts.market_relevance.sectors[:3])
    companies = ", ".join(facts.entities.companies[:3])
    connection = sectors or companies or "반도체, 2차전지, 성장주 등 관련 섹터"
    return (
        "🇰🇷 국내 연결고리\n"
        f"• {html.escape(connection)} 반응과 국내 관련 업종 수급을 같이 확인할 필요가 있습니다.\n\n"
    )


def _bullet_block(points: list[str]) -> str:
    return "\n".join(f"• {html.escape(point)}" for point in points if point)


def _sentence(value: str, limit: int) -> str:
    text = make_excerpt(value, limit).rstrip()
    if text and text[-1] not in ".!?。！？…":
        text += "."
    return text


def _tags_for(facts: FactExtraction) -> list[str]:
    guide = load_style_guide()
    raw_tags = [
        *facts.entities.companies[:2],
        *facts.market_relevance.sectors[:2],
        *facts.entities.assets[:2],
    ]
    tags: list[str] = []
    for value in raw_tags:
        cleaned = "".join(char for char in value.strip() if char.isalnum() or char in {"_", "-"})
        if cleaned and f"#{cleaned}" not in tags:
            tags.append(f"#{cleaned}")
    return (tags or guide.default_tags)[:4]


def _looks_readable(text: str) -> bool:
    first_line = clean_text(text.splitlines()[0] if text.splitlines() else "")
    first_line = first_line.replace("<b>", "").replace("</b>", "")
    return (
        "<b>" in text
        and len(first_line) <= 44
        and "출처:" in text
        and "투자 권유" in text
        and any(marker in text for marker in READABLE_SECTION_MARKERS)
        and "체크 포인트" in text
    )


def _normalize_message(text: str) -> str:
    lines = [line.rstrip() for line in text.strip().splitlines()]
    normalized = "\n".join(lines)
    return BLANK_LINES_RE.sub("\n\n", normalized)

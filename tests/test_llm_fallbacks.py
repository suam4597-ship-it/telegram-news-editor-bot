import pytest

from app.llm.fact_extractor import FactExtractor
from app.llm.client import OpenAIResponsesClient
from app.llm.summary_writer import SummaryWriter
from app.llm.validator import SummaryValidator


@pytest.mark.asyncio
async def test_llm_fallback_chain_without_api_key() -> None:
    client = OpenAIResponsesClient(api_key="")
    facts = await FactExtractor(client=client).extract(
        title="미 CPI 예상 상회",
        source="테스트",
        published_at=None,
        article_text="미국 CPI가 예상치를 웃돌며 금리 기대가 조정됐다.",
    )
    summary = await SummaryWriter(client=client).write(facts=facts, source_url="https://example.com/a", source_name="테스트")
    validation = await SummaryValidator(client=client).validate(facts=facts, telegram_text=summary.telegram_text)
    assert "출처:" in summary.telegram_text
    assert validation.pass_ is True


@pytest.mark.asyncio
async def test_short_link_fallback_uses_short_post_type() -> None:
    client = OpenAIResponsesClient(api_key="")
    facts = await FactExtractor(client=client).extract(
        title="현대차 하반기 실적 개선 기대",
        source="테스트",
        published_at=None,
        article_text="현대차 하반기 실적 개선 기대가 제기됐다.",
    )
    summary = await SummaryWriter(client=client).write(
        facts=facts,
        source_url="https://example.com/a",
        source_name="테스트",
        post_type="short_link",
    )
    assert summary.post_type == "short_link"
    assert len(summary.telegram_text.splitlines()) <= 4


@pytest.mark.asyncio
async def test_editorial_fallback_uses_readable_sections() -> None:
    client = OpenAIResponsesClient(api_key="")
    facts = await FactExtractor(client=client).extract(
        title="현대차 하반기 실적 개선 기대",
        source="테스트",
        published_at=None,
        article_text="하반기 판매 회복과 원가 부담 완화가 주요 변수로 제시됐습니다.",
    )
    summary = await SummaryWriter(client=client).write(
        facts=facts,
        source_url="https://example.com/a",
        source_name="테스트",
        post_type="editorial_brief",
    )
    assert "📍 핵심 포인트" in summary.telegram_text
    assert "🔎 체크 포인트" in summary.telegram_text
    assert "💬 시사점" in summary.telegram_text
    assert "출처:" in summary.telegram_text

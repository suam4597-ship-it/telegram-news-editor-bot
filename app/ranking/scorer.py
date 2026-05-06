from __future__ import annotations

import re
from datetime import UTC, datetime

from app.models import RawItem, Source

INVESTMENT_KEYWORDS = {
    "실적",
    "영업이익",
    "순이익",
    "매출",
    "EPS",
    "어닝",
    "가이던스",
    "전망",
    "수주",
    "공급계약",
    "계약",
    "자사주",
    "배당",
    "주주환원",
    "유상증자",
    "전환사채",
    "CB",
    "BW",
    "임상",
    "FDA",
    "승인",
    "가격 인상",
    "증설",
    "공장",
    "수급",
    "외국인",
    "기관",
    "금리",
    "환율",
    "달러",
    "유가",
    "CPI",
    "PCE",
    "FOMC",
    "Fed",
    "Treasury",
    "earnings",
    "guidance",
    "revenue",
    "margin",
    "buyback",
    "dividend",
    "orders",
    "공급망",
    "수출통제",
    "관세",
    "희토류",
    "제재",
    "지정학",
    "중동",
    "대만",
    "우크라이나",
    "supply chain",
    "export control",
    "tariff",
    "sanction",
}

SECTOR_KEYWORDS = {
    "반도체",
    "HBM",
    "AI",
    "엔비디아",
    "Nvidia",
    "NVDA",
    "AMD",
    "TSMC",
    "2차전지",
    "배터리",
    "전기차",
    "EV",
    "테슬라",
    "Tesla",
    "TSLA",
    "자동차",
    "현대차",
    "조선",
    "방산",
    "원전",
    "전력망",
    "로봇",
    "바이오",
    "Apple",
    "AAPL",
    "Microsoft",
    "MSFT",
    "Amazon",
    "AMZN",
    "Google",
    "GOOGL",
    "희토류",
    "전력기기",
    "변압기",
    "전선",
    "데이터센터",
    "LNG",
    "해운",
    "에너지",
}

KOREA_CONNECTION_KEYWORDS = {
    "한국",
    "국내",
    "코스피",
    "코스닥",
    "원화",
    "삼성",
    "삼성전자",
    "SK하이닉스",
    "SK hynix",
    "LG",
    "현대차",
    "기아",
    "한화",
    "HD현대",
    "두산",
    "Korea",
    "South Korea",
    "memory",
    "HBM",
    "semiconductor",
    "battery",
    "shipbuilding",
    "defense",
}

NOISE_KEYWORDS = {
    "맛집",
    "여행",
    "부동산 분양",
    "연예",
    "스포츠",
    "복권",
    "사주",
    "홍보",
    "행사",
    "이벤트",
    "브랜드 대상",
    "골든크로스",
    "데드크로스",
    "매수신호",
    "매도신호",
    "MK시그널",
    "시그널",
    "순매수 상위",
    "고수익 투자자",
    "목표가",
    "추천주",
    "리딩방",
    "수익률",
    "상한가",
    "특징주",
    "신고가",
    "장 초반",
    "장중",
    "곱버스",
    "목표주가",
    "투자의견",
    "매수 제시",
    "매수 유지",
    "증권가",
    "리포트",
    "코스피 7000",
    "7천피",
    "코스피",
    "코스닥",
    "국내 증시",
    "증시 판도",
    "지수 전망",
    "랠리",
    "급등",
    "이 종목",
    "Jim Cramer",
    "Cramer",
    "to buy",
    "buy for",
    "winners to buy",
    "Bitcoin",
    "crypto",
    "treasury firm",
}

CLICKBAIT_KEYWORDS = {"충격", "대박", "폭등", "급등주", "비밀", "단독 추천", "몰빵", "수익 보장", "상한가"}
QUALITY_SIGNAL_KEYWORDS = {
    "공급계약",
    "수주",
    "가이던스",
    "영업이익",
    "증설",
    "투자",
    "수출통제",
    "관세",
    "공급망",
    "희토류",
    "방산",
    "조선",
    "원전",
    "HBM",
    "데이터센터",
}
NUMBER_RE = re.compile(r"(\d+[\d,.]*\s?(%|조|억|만|달러|원|bp|대|건)?)", re.IGNORECASE)
TICKER_RE = re.compile(r"\b[A-Z]{1,5}\b")


def score_item(item: RawItem, source: Source) -> dict[str, float]:
    title = item.title or ""
    excerpt = item.raw_excerpt or ""
    text = f"{title} {excerpt}"
    reliability = float(source.reliability_score or 0.5)
    freshness = _freshness_score(item.published_at)

    investment_hits = sum(1 for keyword in INVESTMENT_KEYWORDS if keyword.lower() in text.lower())
    sector_hits = sum(1 for keyword in SECTOR_KEYWORDS if keyword.lower() in text.lower())
    ticker_hits = len(TICKER_RE.findall(text)) if (source.country or "").upper() != "KR" else 0
    number_hits = len(NUMBER_RE.findall(text))

    market_impact = min(1.0, (investment_hits + min(sector_hits, 3) + min(ticker_hits, 2)) / 6)
    quality_hits = sum(1 for keyword in QUALITY_SIGNAL_KEYWORDS if keyword.lower() in text.lower())
    if quality_hits:
        market_impact = min(1.0, market_impact + min(quality_hits, 3) * 0.08)
    korea_relevance = _korea_relevance(text, source)
    data_richness = min(1.0, 0.35 + min(number_hits, 3) * 0.22)
    novelty = 0.72

    source_bonus = 0.05 if source.source_type == "naver_news" else 0.0
    if source.category in {"foreign_rss", "us_market", "global_market"}:
        source_bonus += 0.03

    clickbait_penalty = 0.15 if any(keyword.lower() in text.lower() for keyword in CLICKBAIT_KEYWORDS) else 0.0
    noise_penalty = 0.20 if any(keyword.lower() in text.lower() for keyword in NOISE_KEYWORDS) else 0.0

    score = (
        reliability * 0.18
        + freshness * 0.14
        + market_impact * 0.34
        + novelty * 0.10
        + korea_relevance * 0.12
        + data_richness * 0.12
        + source_bonus
        - clickbait_penalty
        - noise_penalty
    )
    return {
        "importance_score": round(max(0, min(score, 1)) * 100, 2),
        "freshness_score": round(freshness * 100, 2),
        "market_impact_score": round(market_impact * 100, 2),
        "novelty_score": round(novelty * 100, 2),
        "data_richness_score": round(data_richness * 100, 2),
        "korea_relevance_score": round(korea_relevance * 100, 2),
        "clickbait_penalty": round(clickbait_penalty * 100, 2),
        "noise_penalty": round(noise_penalty * 100, 2),
    }


def has_korea_or_sector_connection(text: str) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in KOREA_CONNECTION_KEYWORDS | SECTOR_KEYWORDS)


def _korea_relevance(text: str, source: Source) -> float:
    if (source.country or "").upper() == "KR":
        return 1.0
    if has_korea_or_sector_connection(text):
        return 0.75
    return 0.25


def _freshness_score(published_at: datetime | None) -> float:
    if not published_at:
        return 0.5
    now = datetime.now(UTC)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=UTC)
    hours = max((now - published_at).total_seconds() / 3600, 0)
    if hours <= 1:
        return 1.0
    if hours <= 6:
        return 0.8
    if hours <= 24:
        return 0.55
    return 0.25

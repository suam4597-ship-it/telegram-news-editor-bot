from __future__ import annotations

from typing import Literal

from app.models import RawItem, Source
from app.ranking.scorer import has_korea_or_sector_connection

PostType = Literal["short_link", "editorial_brief", "market_brief", "data_brief", "breaking"]

POST_TYPES: set[str] = {"short_link", "editorial_brief", "market_brief", "data_brief", "breaking"}

BREAKING_KEYWORDS = {"속보", "긴급", "단독"}
DATA_SOURCE_TYPES = {"dart"}
DATA_CATEGORIES = {"data", "disclosure", "official"}
EDITORIAL_KEYWORDS = {
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
    "자사주",
    "배당",
    "주주환원",
    "유상증자",
    "전환사채",
    "임상",
    "FDA",
    "승인",
    "가격 인상",
    "증설",
    "정책",
    "규제",
    "금리",
    "환율",
    "CPI",
    "PCE",
    "FOMC",
    "HBM",
    "반도체",
    "2차전지",
    "방산",
    "원전",
    "로봇",
    "earnings",
    "guidance",
    "revenue",
    "Nvidia",
    "NVDA",
    "AMD",
    "Tesla",
    "TSLA",
    "공급망",
    "수출통제",
    "관세",
    "희토류",
    "제재",
    "지정학",
    "중동",
    "대만",
    "우크라이나",
    "전력기기",
    "변압기",
    "전선",
    "데이터센터",
    "LNG",
}
SHORT_ONLY_RISK_KEYWORDS = {
    "목표가",
    "매수가",
    "매도가",
    "추천주",
    "급등주",
    "상한가",
    "수익률",
}
NOISE_KEYWORDS = {"맛집", "여행", "연예", "스포츠", "복권", "행사", "홍보"}
LOW_QUALITY_INVESTMENT_KEYWORDS = {
    "골든크로스",
    "데드크로스",
    "매수신호",
    "매도신호",
    "MK시그널",
    "시그널",
    "순매수 상위",
    "고수익 투자자",
    "목표가",
    "목표주가",
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


def select_post_type(item: RawItem, source: Source, scores: dict[str, float]) -> PostType:
    configured = getattr(source, "template_policy", "auto") or "auto"
    if configured in POST_TYPES and configured != "auto":
        return configured  # type: ignore[return-value]

    text = f"{item.title or ''} {item.raw_excerpt or ''}"
    importance_score = scores.get("importance_score", 0.0)
    market_impact_score = scores.get("market_impact_score", 0.0)

    if source.source_type in DATA_SOURCE_TYPES or (source.category or "") in DATA_CATEGORIES:
        return "data_brief"
    if any(keyword in text for keyword in NOISE_KEYWORDS | LOW_QUALITY_INVESTMENT_KEYWORDS):
        return "short_link"
    if any(keyword in text for keyword in BREAKING_KEYWORDS) and importance_score >= 80:
        return "breaking"
    if any(keyword in text for keyword in SHORT_ONLY_RISK_KEYWORDS) and importance_score < 85:
        return "short_link"
    if _is_foreign_source(source) and not has_korea_or_sector_connection(text):
        return "short_link"
    if _has_editorial_signal(text) and (importance_score >= 60 or market_impact_score >= 45):
        if source.category in {"macro", "us_market", "global_market"}:
            return "market_brief"
        return "editorial_brief"
    return "short_link"


def should_skip_item(item: RawItem, source: Source, scores: dict[str, float]) -> str | None:
    text = f"{item.title or ''} {item.raw_excerpt or ''}"
    if any(keyword in text for keyword in LOW_QUALITY_INVESTMENT_KEYWORDS):
        return "low_quality_investment_signal"
    if any(keyword in text for keyword in NOISE_KEYWORDS):
        return "investment_relevance_low"
    if _is_foreign_source(source) and not has_korea_or_sector_connection(text) and scores.get("market_impact_score", 0) < 65:
        return "foreign_without_korea_or_sector_connection"
    if scores.get("importance_score", 0) < 35 and not _has_editorial_signal(text):
        return "importance_score_too_low"
    return None


def _has_editorial_signal(text: str) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in EDITORIAL_KEYWORDS) or any(char.isdigit() for char in text)


def _is_foreign_source(source: Source) -> bool:
    return (source.country or "").upper() not in {"", "KR"}

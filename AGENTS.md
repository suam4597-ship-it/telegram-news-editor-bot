# AGENTS.md

## Project Purpose

This repository powers a Telegram channel that curates mostly foreign economic, financial, market, and investment-related news into Korean market briefs.

The goal is not to translate or rewrite entire articles. The goal is to produce concise, source-grounded Korean briefs that help readers understand:
- what happened,
- why it matters,
- what to watch next.

## Editorial Principles

Write like a calm market editor, not like a hype account or a generic AI assistant.

Allowed:
- factual summaries,
- market context,
- possible implications,
- uncertainty,
- next checkpoints,
- official data references,
- source links.

Forbidden:
- buy/sell/hold recommendations,
- target prices,
- "must buy", "sure win", "guaranteed", or "massive profit" language,
- fabricated numbers, dates, quotes, tickers, or causality,
- long translated passages,
- copying article wording,
- republishing full article text,
- using news article images unless explicitly licensed.

## Korean Style Guide

Tone:
- calm,
- practical,
- concise,
- readable on mobile,
- useful for Korean retail investors.

Avoid:
- "이 기사는 ~에 대해 다룹니다"
- "결론적으로"
- "투자자들은 주목해야 합니다"
- "큰 파장을 일으킬 수 있습니다"
- "폭등", "대박", "무조건", "강력 매수"

Prefer:
- "시장이 본 건 숫자보다 방향입니다."
- "아직은 단일 보도라 확인이 필요합니다."
- "주가보다 가이던스 변화가 더 중요해 보입니다."
- "다음 체크포인트는 발표 일정과 회사 코멘트입니다."

## Telegram Formatting

Use Telegram HTML parse mode.

Allowed tags:
- `<b>`
- `<i>`
- `<a href="...">`
- `<code>`

Always HTML-escape generated content before wrapping it with tags.

Keep final Telegram messages under 3,500 characters.

Recommended format:

```text
<b>{short_title}</b>

{one_sentence_summary}

• <b>무슨 일</b>: {fact}
• <b>시사점</b>: {market_implication}
• <b>체크포인트</b>: {what_to_watch}

출처: <a href="{source_url}">{source_name}</a>
※ 정보 제공 목적이며 투자 권유가 아닙니다.

{hashtags}
```

## Pipeline Rules

Use a multi-step pipeline:
1. Extract facts from source text into structured JSON.
2. Convert facts into an editorial brief.
3. Validate the brief against the facts.
4. Format the validated brief for Telegram.

Do not let the final writer use raw article text directly if a fact JSON is available.
The writer should primarily use extracted facts to reduce copying and hallucination risk.

## Validation Rules

A brief must be marked `needs_review` if:
- it contains an unsupported claim,
- it contains a number not present in the extracted facts,
- it sounds like investment advice,
- it includes a target price,
- it uses hype language,
- it has no source URL,
- it is based on a rumor or single unconfirmed report,
- it exceeds the Telegram message limit,
- it fails HTML validation.

## Test Requirements

When modifying the editorial pipeline:
- add unit tests for formatting,
- add tests for banned phrases,
- add schema validation tests,
- add at least 3 golden examples:
  1. macro news,
  2. company earnings,
  3. policy/regulation news.

All tests must pass before the task is complete.

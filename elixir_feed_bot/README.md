# FeedBot Elixir

국내·해외 뉴스 RSS를 폴링해 투자 관련 기업·산업·기술 이슈만 텔레그램 채널에 발행하는 Elixir OTP 봇입니다.

## Pipeline

```text
RSS/Atom feeds
→ first-run warmup
→ URL dedup
→ blacklist filter
→ story-level dedup
→ category + base_score
→ LLM summary/impact/importance
→ Telegram HTML queue
```

첫 실행 첫 폴링은 warmup 모드입니다. 기존 RSS 항목을 전부 `seen`으로 마킹하고 발행하지 않습니다. 두 번째 폴링부터 새 항목만 발행 후보가 됩니다.

## Sources

시작 피드는 `lib/feed_bot/sources/feeds.ex`에서 관리합니다.

- 한국 전문/주요: 디일렉, 한국경제 IT, 매일경제 기업·경영, 전자신문, 파이낸셜뉴스 산업/IT
- 영문 전문/주요: Stratechery, SemiAnalysis, TechCrunch, The Verge, Ars Technica, WIRED
- 커뮤니티: Hacker News 200점+

한국경제와 파이낸셜뉴스는 현재 동작하는 공식 RSS 경로로 보정했습니다.

## Setup

```powershell
cd elixir_feed_bot
mix deps.get
```

환경변수:

```powershell
$env:LLM_PROVIDER="auto"
$env:OPENAI_API_KEY="..."
$env:OPENAI_MODEL="gpt-5.4-mini"

$env:TELEGRAM_BOT_TOKEN="..."
$env:TELEGRAM_CHAT_ID="@your_channel"
$env:HTTP_USER_AGENT="FeedBot/0.1 your-email@example.com"
$env:IMPORTANCE_THRESHOLD="7"
$env:DRY_RUN="true"
```

`LLM_PROVIDER`는 `auto`, `openai`, `anthropic` 중 하나입니다. `auto`에서는 `OPENAI_API_KEY`가 있으면 OpenAI를 먼저 쓰고, 없으면 `ANTHROPIC_API_KEY`로 fallback합니다.

Anthropic을 명시적으로 쓰려면:

```powershell
$env:LLM_PROVIDER="anthropic"
$env:ANTHROPIC_API_KEY="..."
$env:ANTHROPIC_MODEL="claude-haiku-4-5-20251001"
```

`TELEGRAM_CHAT_ID`가 없으면 `TELEGRAM_ADMIN_CHANNEL_ID`, `TELEGRAM_CHANNEL_ID`, `TELEGRAM_PUBLIC_CHANNEL_ID` 순서로 fallback합니다.

## Run

로그로만 확인:

```powershell
$env:DRY_RUN="true"
mix run --no-halt
```

실제 발행:

```powershell
$env:DRY_RUN="false"
mix run --no-halt
```

기본값은 안전을 위해 `DRY_RUN=false`가 아니므로, 테스트 환경에서는 항상 `DRY_RUN=true`를 먼저 설정하세요.

## Tuning

- 너무 많이 올라오면 `IMPORTANCE_THRESHOLD=8`
- 너무 조용하면 `IMPORTANCE_THRESHOLD=6`
- 가격성/시황성 글이 통과하면 `FeedBot.Filter.blacklist/0`에 패턴 추가
- 원하는 주제가 덜 잡히면 `FeedBot.Filter.positives/0`에 키워드 추가
- 중복 보도가 통과하면 `FeedBot.StoryDedup`의 유사도 threshold를 낮춤

## Tests

```powershell
mix test
mix compile --warnings-as-errors
```

테스트는 필터, RSS 파싱, feed metadata, Telegram HTML escaping을 확인합니다.

## Current Branch Notes

현재 GitHub 브랜치의 실제 상태는 RSS 뉴스 파이프라인 + OpenAI/Anthropic provider 선택 지원입니다.

아래 항목은 이전 v0.2 작업 맥락으로 언급되었지만, 현재 브랜치에는 아직 완전히 반영되어 있지 않습니다. 해당 변경을 이어가려면 별도 patch/diff가 필요합니다.

- 외신 RSS 30개 이상 확장
- feed metadata의 `region`
- `ArticleFetcher`
- LLM 8필드 출력: `headline`, `summary`, `key_facts`, `impact`, `why_it_matters`, `tickers`, `importance`, `category`
- Telegram MarkdownV2 포맷 및 plain text fallback

## Policy

- 매수/매도/목표가/수익보장 표현을 만들지 않습니다.
- 원문 전문을 저장하지 않고 RSS title/description/link만 사용합니다.
- Telegram 메시지는 HTML parse mode로 발행하며, 모든 외부 텍스트는 escape합니다.
- LLM 중요도는 rule 기반 `base_score`의 ±2 범위 안으로 보정합니다.

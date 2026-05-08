# FeedBot Elixir

DART/EDGAR 이벤트를 선별해 Telegram 채널에 포스팅하는 Elixir OTP 봇입니다.

이 앱은 뉴스 번역 봇이 아니라, 공시/이벤트 중 투자자가 볼 만한 구조적 변화를 걸러내는 보조 파이프라인입니다.

## Pipeline

```text
DART/EDGAR fetch
→ warmup/dedup
→ rule filter + base_score
→ LLM summary/impact/importance
→ Telegram HTML formatter
→ sendMessage
→ persistent dedup mark
```

첫 실행의 첫 폴링은 warmup 모드입니다. 최근 2일치 이벤트를 전부 `seen`으로 마킹하고 발행하지 않습니다. 두 번째 폴링부터 새 이벤트만 발행 후보가 됩니다.

## Setup

```powershell
cd elixir_feed_bot
mix deps.get
```

환경변수는 `.env.example`를 참고해서 설정합니다. PowerShell 예시는 아래와 같습니다.

```powershell
$env:DART_API_KEY="..."
$env:ANTHROPIC_API_KEY="..."
$env:TELEGRAM_BOT_TOKEN="..."
$env:TELEGRAM_CHANNEL_ID="@your_channel"
$env:MIN_IMPORTANCE="7"
$env:DRY_RUN="false"
```

## Run

```powershell
mix run --no-halt
```

텔레그램으로 보내지 않고 로그로만 확인하려면:

```powershell
$env:DRY_RUN="true"
mix run --no-halt
```

## Tests

```powershell
mix test
```

현재 테스트는 필터 분류, 텔레그램 HTML escaping, 길이 제한, Telegram 설정 오류 처리를 확인합니다.

## Important Env Vars

- `DART_API_KEY`: OpenDART API key
- `ANTHROPIC_API_KEY`: Anthropic Messages API key
- `ANTHROPIC_MODEL`: 기본값 `claude-haiku-4-5-20251001`
- `TELEGRAM_BOT_TOKEN`: BotFather에서 받은 Telegram bot token
- `TELEGRAM_CHANNEL_ID`: 공개 채널 username 또는 chat_id
- `POLL_INTERVAL_MS`: 기본값 `60000`
- `MIN_IMPORTANCE`: 기본값 `7`
- `DRY_RUN`: `true`이면 Telegram 전송 대신 로그 출력

## Policy

- 매수/매도/목표가/수익보장 표현을 만들지 않습니다.
- 정정공시, 일상 자금조달, 가격성 신호는 기본적으로 reject합니다.
- LLM 최종 중요도는 rule 기반 `base_score`의 ±2 범위 안으로 보정됩니다.
- Telegram 메시지는 HTML parse mode 기준으로 escape됩니다.

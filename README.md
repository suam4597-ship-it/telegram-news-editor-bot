# Telegram News Editor Bot MVP

경제·투자 뉴스를 수집해 텔레그램 관리자 채널에 초안을 보내고, 승인된 글만 공개 채널에 발행하는 반자동 뉴스 에디터 봇입니다.

## 현재 소스 전략

- 국내 메인: 네이버 뉴스 검색 API
  - `config/source_queries.yml`의 기업·산업·지정학 쿼리팩으로 기사 발견
  - `originallink`, 제목, description, 발행시각만 저장
  - 본문 전문과 보도사진은 저장하지 않음
- 외신 메인: CNBC/Nasdaq 공식 RSS
  - 글로벌 기업, AI/반도체, 공급망, 산업 변화 이슈 발견
  - 외신 요약은 국내 연결고리가 약하면 발행 제외 또는 짧은 링크형
- 비활성: 넓은 국내 증권 RSS
  - 차트신호, 목표가, 순매수, 추천성 글이 자주 섞여 기본 비활성화

모든 공개 발행은 MVP 단계에서 관리자 승인 후 진행합니다.

## 설정 파일

- `config/sources.yml`: 소스 추가, 비활성화, 수집 주기, 승인 정책, 소스별 레인 관리
- `config/source_queries.yml`: 네이버 뉴스 검색 쿼리팩 관리
- `config/style_guide.yml`: 금지 표현, 기본 고지, 글자 수 제한 관리
- `app/llm/prompts/*.md`: 팩트 추출, 요약 작성, 검증 프롬프트 관리

## .env 필수 값

```env
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.4-mini

NAVER_CLIENT_ID=
NAVER_CLIENT_SECRET=

TELEGRAM_BOT_TOKEN=
TELEGRAM_ADMIN_CHANNEL_ID=
TELEGRAM_PUBLIC_CHANNEL_ID=
TELEGRAM_WEBHOOK_SECRET=
```

`NAVER_CLIENT_ID`와 `NAVER_CLIENT_SECRET`은 네이버 개발자 센터에서 검색 API 애플리케이션을 만든 뒤 발급받습니다. OpenDART는 이번 뉴스 중심 개편의 기본 수집 대상에서 제외했습니다.

## 빠른 실행

```powershell
docker compose up --build
docker compose exec app newsbot init-db
docker compose exec app newsbot seed-sources
docker compose exec app newsbot collect-once
docker compose exec app newsbot draft-once --limit 3
```

Docker CLI가 현재 PowerShell PATH에서 안 잡히면 아래처럼 실행할 수 있습니다.

```powershell
$env:PATH='C:\Program Files\Docker\Docker\resources\bin;' + $env:PATH
docker compose exec app newsbot seed-sources
```

## 주요 CLI

- `newsbot init-db`: DB 테이블 생성 및 운영 컬럼 보정
- `newsbot seed-sources`: `config/sources.yml`을 DB에 반영
- `newsbot list-sources`: 현재 DB 소스 목록 확인
- `newsbot check-source SOURCE_ID`: 특정 소스 수집 미리보기
- `newsbot collect-once`: 활성 소스 1회 수집
- `newsbot draft-once --limit 3`: 수집 기사 초안 생성 후 관리자 채널 전송
- `newsbot requeue-summary SUMMARY_ID`: 초안을 다시 관리자 검토로 전송

## 관리자 버튼

관리자 채널 초안에는 `승인`, `반려`, `짧게`, `길게`, `재작성`, `수정 후 승인` 버튼이 붙습니다. `수정 후 승인`은 초안 메시지에 답장으로 최종 문안을 보내면 새 문안이 저장되고 다시 승인 대기 상태로 전송됩니다.

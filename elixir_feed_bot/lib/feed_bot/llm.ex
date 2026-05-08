defmodule FeedBot.LLM do
  @moduledoc """
  LLM 보강: 한 줄 요약, 영향 범위, 중요도 점수.

  Anthropic Messages API 사용. JSON 출력은 prefill 트릭으로 강제.
  비용: 이미 Filter 통과한 이벤트만 호출됨. 작은 모델(Haiku) 권장.
  """

  require Logger
  alias FeedBot.Event

  @endpoint "https://api.anthropic.com/v1/messages"

  @doc """
  Event에 :summary, :impact, :delta, :importance 를 채워 반환.
  실패 시 importance=0 으로 두어 자연스럽게 컷오프.
  """
  @spec enrich(Event.t()) :: Event.t()
  def enrich(%Event{} = ev) do
    case call(prompt(ev)) do
      {:ok, %{"summary" => s, "impact" => i, "importance" => imp} = res} ->
        %{
          ev
          | summary: s,
            impact: i,
            delta: res["delta"],
            importance: anchored_importance(ev.base_score, imp)
        }

      {:error, reason} ->
        Logger.warning("LLM enrich failed: #{inspect(reason)} (#{ev.title})")
        %{ev | importance: 0}
    end
  end

  # ────────────────────────────────────────────────────────────
  # 프롬프트
  # ────────────────────────────────────────────────────────────
  defp prompt(%Event{} = ev) do
    """
    너는 한국 투자자 대상 텔레그램 채널의 큐레이터다.

    이 채널의 정체성:
      ✅  사업의 실체적 변화 — 사업영역, CAPEX, 경쟁우위, 거버넌스, 자본배분의 장기 변화
      ❌  단기 가격성·테마성·수급 신호, 일상적 자금조달, 정정공시
      ❌  주가가 오르내릴지에 대한 예측 (이건 우리가 안 다룬다)

    아래 공시를 평가하라.

    소스      : #{source_label(ev.source)}
    기업      : #{ev.company}#{ticker_suffix(ev.ticker)}
    유형      : #{ev.form_type}#{items_suffix(ev.items)}
    카테고리  : #{ev.category}
    사전점수  : #{ev.base_score}/10  (룰 기반 추정. 본문 보고 ±2 범위로 조정 가능)
    제목      : #{ev.title}
    URL       : #{ev.url}

    importance 기준 (0-10):
      9-10  사업 방향이 근본적으로 바뀌는 사건
            예: 수십억 달러 M&A, 영업양수도, 통제권 변경, 대표이사 교체, 파산
      7-8   1년+ 영향이 갈 사건
            예: 대형 CAPEX, 핵심 고객 신규 계약, 자사주 소각, 핵심 인사 영입
      5-6   거버넌스·자본배분 신호
            예: 일반 자사주 매입, 5%룰 보고, 정기보고서, 가이던스 변화
      3-4   본문 따라 가치 갈리는 것
      0-2   정정공시, 일상 자금조달, 보일러플레이트
            (이미 Filter가 대부분 잡았지만 빠져나온 게 있으면 여기로)

    summary 작성 규칙:
      - 한국어, 50자 이내, 단정형 ('~결정', '~체결')
      - 무엇이 일어났는지만. 추측·예측 금지.
      - 숫자(금액·기간·수량)가 있으면 반드시 포함
      - 좋은 예: "SK하이닉스, 美 인디애나에 38억달러 HBM 패키징 공장 신설"
      - 나쁜 예: "SK하이닉스의 호재성 공시 발표"

    impact 작성 규칙:
      - 어떤 산업·공급망·기업이 영향받을지. 한 줄.
      - 좋은 예: "엔비디아향 HBM3E 공급 캐파 확대, TSMC CoWoS 의존도 일부 분산"
      - 나쁜 예: "주가 상승이 예상됨"

    delta 작성 규칙:
      - 이전 발표/분기 대비 무엇이 달라졌는지. 정황이 보일 때만.
      - 정황 없으면 빈 문자열.
      - 좋은 예: "전분기 가이던스 대비 capex 30% 상향"

    출력 형식: JSON 한 객체. 다른 텍스트(설명, 코드펜스) 절대 금지.
    스키마:
      {"summary": string, "impact": string, "delta": string, "importance": int 0-10}
    """
  end

  defp source_label(:dart), do: "DART (한국 전자공시)"
  defp source_label(:edgar), do: "SEC EDGAR (미국)"

  defp ticker_suffix(nil), do: ""
  defp ticker_suffix(""), do: ""
  defp ticker_suffix(t), do: " (#{t})"

  defp items_suffix(nil), do: ""
  defp items_suffix([]), do: ""
  defp items_suffix(items), do: " · Items: #{Enum.join(items, ", ")}"

  # ────────────────────────────────────────────────────────────
  # Anthropic API 호출 (JSON prefill 트릭)
  # ────────────────────────────────────────────────────────────
  defp call(user_prompt) do
    api_key = Application.get_env(:feed_bot, :anthropic_api_key)
    model = Application.get_env(:feed_bot, :llm_model, "claude-haiku-4-5-20251001")

    if is_nil(api_key) do
      {:error, :no_api_key}
    else
      body = %{
        model: model,
        max_tokens: 500,
        messages: [
          %{role: "user", content: user_prompt},
          # ← prefill: assistant 응답을 "{" 로 강제 시작 → JSON 외 출력 차단
          %{role: "assistant", content: "{"}
        ]
      }

      headers = [
        {"x-api-key", api_key},
        {"anthropic-version", "2023-06-01"},
        {"content-type", "application/json"}
      ]

      with {:ok, %{status: 200, body: %{"content" => [%{"text" => text} | _]}}} <-
             Req.post(@endpoint, headers: headers, json: body, receive_timeout: 30_000),
           # prefill 했으니 응답에 "{" prepend 후 파싱
           {:ok, parsed} <- Jason.decode("{" <> text) do
        {:ok, parsed}
      else
        {:ok, %{status: s, body: b}} -> {:error, {:http, s, b}}
        {:error, e} -> {:error, {:json, exception_message(e)}}
        err -> err
      end
    end
  end

  defp exception_message(e) do
    Exception.message(e)
  rescue
    _ -> inspect(e)
  end

  defp anchored_importance(nil, n), do: clamp(n)

  defp anchored_importance(base_score, n) when is_integer(base_score) do
    raw = clamp(n)
    min_score = max(base_score - 2, 0)
    max_score = min(base_score + 2, 10)

    raw
    |> max(min_score)
    |> min(max_score)
  end

  defp anchored_importance(_, n), do: clamp(n)

  defp clamp(n) when is_integer(n) and n in 0..10, do: n
  defp clamp(n) when is_integer(n) and n < 0, do: 0
  defp clamp(n) when is_integer(n) and n > 10, do: 10
  defp clamp(_), do: 0
end

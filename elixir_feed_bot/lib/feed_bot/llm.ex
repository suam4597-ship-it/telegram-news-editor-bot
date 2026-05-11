defmodule FeedBot.LLM do
  @moduledoc """
  뉴스 기사 LLM 보강.
  Filter 통과한 것만 호출 → 비용 통제. 작은 모델(Haiku 등) 권장.
  """

  require Logger
  alias FeedBot.Event

  @anthropic_endpoint "https://api.anthropic.com/v1/messages"
  @openai_endpoint "https://api.openai.com/v1/responses"

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

  @doc false
  @spec provider() :: :openai | :anthropic | :none
  def provider, do: resolve_provider()

  # ────────────────────────────────────────────
  defp prompt(%Event{} = ev) do
    """
    너는 한국 투자자 대상 텔레그램 채널의 큐레이터다.

    채널 정체성:
      ✅ 기술·산업·기업의 실체적 변화 — 제품 출시, 공장 신설, 인수, 협력, 규제, 임원
      ❌ 가격성·테마성·시황성·전망성 (Filter 가 대부분 거름)
      ❌ 주가 방향 예측 (이건 절대 안 한다)

    뉴스 기사 평가:

    매체     : #{ev.source_name} [tier=#{ev.source_tier}, lang=#{ev.source_lang}]
    카테고리 : #{ev.category}
    사전점수 : #{ev.base_score}/10  (룰 기반 추정. 본문 보고 ±2 범위로 조정 가능)
    제목     : #{ev.title}
    요약     : #{ev.description || "(RSS 요약 없음)"}
    URL      : #{ev.url}

    importance 기준 (0-10):
      9-10  업계 지형 자체가 바뀌는 사건
            예: 대형 M&A 발표·완료, 통제권 변경, 핵심 산업 규제 신설, 산업 표준 변경
      7-8   1년+ 영향이 가는 사건
            예: 대형 CAPEX 발표, 핵심 기술 양산 시작, CEO 교체, 굵직한 협력·계약
      5-6   기업의 사업 변화 신호
            예: 신제품 출시, 작은 인수, 부분 협력, 새 임원 영입
      3-4   본문 따라 가치 갈리는 일반 보도
      0-2   가격성·테마성 노이즈, 단순 보도자료 베껴 쓴 기사

    매체 tier 보정 (점수에 반영):
      - specialist : 신호 밀도 높음. 사전점수 그대로 신뢰.
      - major      : 보통. 본문에 따라 조정.
      - general    : 가산점 있더라도 한 단계 깎아서 평가.

    summary 작성 규칙 (50자 이내, 한국어):
      - 단정형 ('출시', '체결', '결정', '발표')
      - 숫자(금액·기간·수량·국가)가 있으면 반드시 포함
      - 매체의 클릭베이트 표현 제거
      - 좋은 예: "TSMC, 美 애리조나 3nm 팹 양산 시작"
                 "Anthropic, AWS 와 40억달러 추가 투자 합의"
      - 나쁜 예: "TSMC가 큰 발걸음" / "AI 시장 격변 예고"

    impact 작성 규칙 (한 줄, 한국어):
      - 어떤 산업/공급망/기업이 영향받는지
      - 좋은 예: "엔비디아 향 HBM 캐파 확대, SK하이닉스/마이크론 경쟁 심화"
      - 나쁜 예: "주가 상승 가능"

    delta 작성 규칙:
      - 이전 보도/발표 대비 변화 정황이 있을 때만. 없으면 빈 문자열.

    출력: JSON 한 객체. 다른 텍스트(설명, 코드펜스) 절대 금지.
    스키마:
      {"summary": string, "impact": string, "delta": string, "importance": int 0-10}
    """
  end

  defp call(user_prompt) do
    case resolve_provider() do
      :openai -> call_openai(user_prompt)
      :anthropic -> call_anthropic(user_prompt)
      :none -> {:error, :no_llm_api_key}
    end
  end

  defp resolve_provider do
    configured =
      :feed_bot
      |> Application.get_env(:llm_provider, "auto")
      |> normalize_provider()

    case configured do
      :openai -> :openai
      :anthropic -> :anthropic
      :auto -> auto_provider()
    end
  end

  defp normalize_provider(provider) when provider in [:openai, :anthropic, :auto], do: provider

  defp normalize_provider(provider) when is_binary(provider) do
    case String.downcase(provider) do
      "openai" -> :openai
      "anthropic" -> :anthropic
      _ -> :auto
    end
  end

  defp normalize_provider(_), do: :auto

  defp auto_provider do
    cond do
      present?(Application.get_env(:feed_bot, :openai_api_key)) -> :openai
      present?(Application.get_env(:feed_bot, :anthropic_api_key)) -> :anthropic
      true -> :none
    end
  end

  defp call_anthropic(user_prompt) do
    api_key = Application.get_env(:feed_bot, :anthropic_api_key)
    model = Application.get_env(:feed_bot, :anthropic_model, "claude-haiku-4-5-20251001")

    if not present?(api_key) do
      {:error, :no_api_key}
    else
      body = %{
        model: model,
        max_tokens: 500,
        messages: [
          %{role: "user", content: user_prompt},
          # JSON prefill: assistant 응답을 "{" 로 강제 시작
          %{role: "assistant", content: "{"}
        ]
      }

      headers = [
        {"x-api-key", api_key},
        {"anthropic-version", "2023-06-01"},
        {"content-type", "application/json"}
      ]

      with {:ok, %{status: 200, body: %{"content" => [%{"text" => text} | _]}}} <-
             Req.post(@anthropic_endpoint, headers: headers, json: body, receive_timeout: 30_000),
           {:ok, parsed} <- Jason.decode("{" <> text) do
        {:ok, parsed}
      else
        {:ok, %{status: s, body: b}} -> {:error, {:http, s, b}}
        {:error, e} -> {:error, {:json, exception_message(e)}}
        err -> err
      end
    end
  end

  defp call_openai(user_prompt) do
    api_key = Application.get_env(:feed_bot, :openai_api_key)
    model = Application.get_env(:feed_bot, :openai_model, "gpt-5.4-mini")

    if not present?(api_key) do
      {:error, :no_api_key}
    else
      body = %{
        model: model,
        input: user_prompt,
        text: %{
          format: %{
            type: "json_schema",
            name: "feed_bot_news_enrichment",
            strict: true,
            schema: response_schema()
          }
        }
      }

      headers = [
        {"authorization", "Bearer #{api_key}"},
        {"content-type", "application/json"}
      ]

      with {:ok, %{status: 200, body: body}} <-
             Req.post(@openai_endpoint, headers: headers, json: body, receive_timeout: 30_000),
           {:ok, text} <- extract_openai_text(body),
           {:ok, parsed} <- Jason.decode(text) do
        {:ok, parsed}
      else
        {:ok, %{status: s, body: b}} -> {:error, {:http, s, b}}
        {:error, e} -> {:error, {:openai, exception_message(e)}}
        err -> err
      end
    end
  end

  defp response_schema do
    %{
      type: "object",
      additionalProperties: false,
      required: ["summary", "impact", "delta", "importance"],
      properties: %{
        summary: %{type: "string"},
        impact: %{type: "string"},
        delta: %{type: "string"},
        importance: %{type: "integer", minimum: 0, maximum: 10}
      }
    }
  end

  defp extract_openai_text(%{"output_text" => text}) when is_binary(text), do: {:ok, text}

  defp extract_openai_text(%{"output" => output}) when is_list(output) do
    text =
      output
      |> Enum.flat_map(fn
        %{"content" => content} when is_list(content) -> content
        _ -> []
      end)
      |> Enum.find_value(fn
        %{"type" => "output_text", "text" => text} when is_binary(text) -> text
        %{"text" => text} when is_binary(text) -> text
        _ -> nil
      end)

    if is_binary(text), do: {:ok, text}, else: {:error, :missing_openai_output_text}
  end

  defp extract_openai_text(_), do: {:error, :missing_openai_output_text}

  defp exception_message(e) do
    Exception.message(e)
  rescue
    _ -> inspect(e)
  end

  defp present?(value) when is_binary(value), do: String.trim(value) != ""
  defp present?(nil), do: false
  defp present?(_), do: true

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

  defp clamp(n) when is_binary(n) do
    case Integer.parse(n) do
      {parsed, _} -> clamp(parsed)
      :error -> 0
    end
  end

  defp clamp(_), do: 0
end

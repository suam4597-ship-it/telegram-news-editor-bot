defmodule FeedBot.Formatter do
  @moduledoc """
  FeedBot.Event를 Telegram HTML 메시지로 바꾸는 deterministic formatter.

  LLM은 텍스트 필드만 채우고, HTML 태그와 escaping은 이 모듈만 담당한다.
  """

  alias FeedBot.Event

  @max_length 3_500

  @doc "Telegram sendMessage(parse_mode: HTML)에 바로 넣을 수 있는 문자열."
  @spec telegram_html(Event.t()) :: String.t()
  def telegram_html(%Event{} = ev) do
    title = present(ev.summary) || fallback_title(ev)
    impact = present(ev.impact) || "영향 범위는 원문 확인이 필요합니다."
    delta = present(ev.delta)

    body =
      [
        "<b>#{esc(title)}</b>",
        "",
        "#{esc(one_line(ev))}",
        "",
        "• <b>무슨 일</b>: #{esc(what_happened(ev))}",
        "• <b>시사점</b>: #{esc(impact)}",
        "• <b>체크포인트</b>: #{esc(checkpoint(ev))}",
        optional_delta(delta),
        "",
        "출처: <a href=\"#{esc_attr(ev.url)}\">#{esc(source_name(ev))}</a>",
        "※ 정보 제공 목적이며 투자 권유가 아닙니다.",
        "",
        hashtags(ev)
      ]
      |> Enum.reject(&(&1 in [nil, ""]))
      |> Enum.join("\n")

    trim_to_limit(body)
  end

  @doc "Telegram 안전 길이 제한."
  @spec max_length() :: pos_integer()
  def max_length, do: @max_length

  defp one_line(%Event{company: company, category: category, base_score: base_score}) do
    company = present(company) || "해당 기업"
    category = category_label(category)

    "#{company} 관련 #{category} 이벤트입니다. 룰 기반 사전점수는 #{base_score || 0}/10입니다."
  end

  defp what_happened(%Event{company: company, title: title, form_type: form_type}) do
    company = present(company) || "기업"
    form = if present(form_type), do: " (#{form_type})", else: ""
    "#{company}의 #{title}#{form} 공시입니다."
  end

  defp checkpoint(%Event{category: :ma}), do: "거래 구조, 대금 규모, 완료 조건과 기존 사업과의 연결성을 확인해야 합니다."
  defp checkpoint(%Event{category: :capex}), do: "투자 금액, 가동 시점, 고객사·제품 믹스 변화를 같이 봐야 합니다."
  defp checkpoint(%Event{category: :contract}), do: "계약 규모, 기간, 매출 대비 비중과 반복 가능성을 확인해야 합니다."
  defp checkpoint(%Event{category: :buyback}), do: "실제 소각 여부, 집행 기간, 기존 주주환원 정책 변화가 핵심입니다."
  defp checkpoint(%Event{category: :control}), do: "새 최대주주의 의사결정 방향과 자금 조달 구조를 확인해야 합니다."
  defp checkpoint(%Event{category: :ceo_change}), do: "신임 경영진의 전략 변화와 사업 포트폴리오 조정 가능성을 봐야 합니다."

  defp checkpoint(%Event{category: :cybersecurity}),
    do: "서비스 중단 범위, 고객 영향, 복구 일정과 비용 반영 여부가 중요합니다."

  defp checkpoint(%Event{category: :bankruptcy}), do: "채권자 협상, 자산 매각, 상장 유지 여부를 우선 확인해야 합니다."
  defp checkpoint(_), do: "원문 세부 조건과 후속 공시에서 숫자·일정 변화가 나오는지 확인해야 합니다."

  defp optional_delta(nil), do: nil
  defp optional_delta(delta), do: "• <b>변화</b>: #{esc(delta)}"

  defp source_name(%Event{source: :dart}), do: "DART"
  defp source_name(%Event{source: :edgar}), do: "SEC EDGAR"
  defp source_name(%Event{source: source}) when is_atom(source), do: Atom.to_string(source)
  defp source_name(_), do: "원문"

  defp fallback_title(%Event{company: company, title: title}) do
    case present(company) do
      nil -> title
      company -> "#{company}, #{title}"
    end
  end

  defp hashtags(%Event{source: source, category: category, ticker: ticker}) do
    [
      "#공시",
      source_tag(source),
      category_tag(category),
      ticker_tag(ticker)
    ]
    |> Enum.reject(&is_nil/1)
    |> Enum.uniq()
    |> Enum.take(4)
    |> Enum.join(" ")
  end

  defp source_tag(:dart), do: "#DART"
  defp source_tag(:edgar), do: "#EDGAR"
  defp source_tag(_), do: nil

  defp category_tag(nil), do: nil
  defp category_tag(category), do: "##{category_label(category) |> String.replace(" ", "")}"

  defp ticker_tag(nil), do: nil
  defp ticker_tag(""), do: nil
  defp ticker_tag(ticker), do: "##{String.replace(to_string(ticker), ~r/[^A-Za-z0-9가-힣_]/u, "")}"

  defp category_label(:ma), do: "M&A"
  defp category_label(:capex), do: "시설투자"
  defp category_label(:contract), do: "수주계약"
  defp category_label(:buyback), do: "주주환원"
  defp category_label(:equity), do: "자본변동"
  defp category_label(:ownership), do: "지분변동"
  defp category_label(:officer), do: "임원변경"
  defp category_label(:ceo_change), do: "대표변경"
  defp category_label(:control), do: "지배구조"
  defp category_label(:ip), do: "특허라이선스"
  defp category_label(:litigation), do: "소송"
  defp category_label(:dividend_policy), do: "배당정책"
  defp category_label(:periodic), do: "정기보고"
  defp category_label(:bankruptcy), do: "파산구조조정"
  defp category_label(:cybersecurity), do: "사이버보안"
  defp category_label(:restructure), do: "구조조정"
  defp category_label(:impairment), do: "손상차손"
  defp category_label(:listing), do: "상장요건"
  defp category_label(:other_material), do: "주요이벤트"

  defp category_label(category) when is_atom(category),
    do: category |> Atom.to_string() |> String.replace("_", " ")

  defp category_label(_), do: "이벤트"

  defp present(nil), do: nil
  defp present(""), do: nil
  defp present(value) when is_binary(value), do: String.trim(value) |> empty_to_nil()
  defp present(value), do: value

  defp empty_to_nil(""), do: nil
  defp empty_to_nil(value), do: value

  defp esc(value) do
    value
    |> to_string()
    |> String.replace("&", "&amp;")
    |> String.replace("<", "&lt;")
    |> String.replace(">", "&gt;")
  end

  defp esc_attr(value) do
    value
    |> esc()
    |> String.replace("\"", "&quot;")
  end

  defp trim_to_limit(text) when byte_size(text) <= @max_length, do: text

  defp trim_to_limit(text) do
    ellipsis = "…"
    limit = @max_length - byte_size(ellipsis)

    {graphemes, _bytes} =
      text
      |> String.graphemes()
      |> Enum.reduce_while({[], 0}, fn grapheme, {acc, bytes} ->
        next_bytes = bytes + byte_size(grapheme)

        if next_bytes > limit do
          {:halt, {acc, bytes}}
        else
          {:cont, {[grapheme | acc], next_bytes}}
        end
      end)

    graphemes
    |> Enum.reverse()
    |> Enum.join()
    |> Kernel.<>(ellipsis)
  end
end

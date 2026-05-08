defmodule FeedBot.Filter do
  @moduledoc """
  뉴스 기사용 필터.

  뉴스는 제목 표현이 너무 다양해서 화이트리스트가 안 통한다.
  대신 두 단계로 작동:

    1. Hard reject 블랙리스트 — 가격성·시황성·클릭베이트 단어 매칭 시 즉시 drop
    2. base_score 계산 — 4점 시작 + 긍정 키워드 가산 (+5 max) + 매체 tier 보정 (±1)
       → 0-10 clamp 후 LLM 으로 전달

  대원칙
    ✅ 사업·기술·산업의 실체적 변화 (제품 출시, 신설, 인수, 협력, 규제)
    ❌ 가격성·테마성·전망성·시황성
  """

  alias FeedBot.Event

  # ────────────────────────────────────────────
  # Hard reject — 즉시 drop (LLM 안 거침)
  # ────────────────────────────────────────────
  defp blacklist do
    [
      # ── 한국어 ──
      # 가격 동향
      ~r/급등|급락|치솟|폭등|폭락|껑충|곤두박질|상한가|하한가/,
      # 테마/추천
      ~r/수혜주|관련주|테마주|유망주|추천주|대장주|상승주|급등주/,
      # 시황 정형 표현
      ~r/(코스피|코스닥|환율|국제유가|금값).*?(상승|하락|마감|급등|급락)/,
      ~r/^오늘의\s|장\s?마감|마감 시황|개장 시황/,
      # 추측·전망성 제목 (단정형이 아닌 것)
      ~r/오를까\??$|내릴까\??$|갈까\??$|일까\??$|어디로\??$/,
      ~r/(전망|예상|관측).{0,5}(솔솔|이어져|확산)/,
      # 종목분석 장르
      ~r/(종목|매수).*?(추천|콜|타이밍)/,

      # ── 영문 ──
      # 가격 동향
      ~r/\b(soar|plunge|tumble|surge|skyrocket|nosedive|rally|sell.?off)/i,
      # 클릭베이트
      ~r/\b(stocks?|shares?)\s+to\s+(buy|watch|own|avoid|sell)/i,
      ~r/\bstock\s+(of the (day|week|month|year)|alert|pick)/i,
      ~r/\b(could|might|may|set to|poised to)\s+(soar|jump|surge|rally|crash|plunge|moon)/i,
      ~r/\b(why|how)\s+.+(stock|shares?)\s+(jumped|surged|fell|crashed|popped)/i,
      ~r/\bbest\s+stocks?\s+(for|to)/i
    ]
  end

  # ────────────────────────────────────────────
  # 긍정 시그널 — base_score 가산
  # ────────────────────────────────────────────
  defp positives do
    [
      # ── 한국어 ──
      {~r/공장.*신설|공장.*증설|시설투자|신규투자|R&D센터|연구소.*설립/, 3},
      {~r/인수|합병|M&A|영업양수도|분사|스핀오프|매각/, 3},
      {~r/공급계약|수주|MOU|파트너십|JV|협력.*체결|업무협약/, 2},
      {~r/특허|라이선스|기술이전|기술수출|독점.*공급/, 2},
      {~r/출시|공개|발표회|언론공개|런칭|양산.*시작|상용화/, 2},
      {~r/대표.*선임|CEO.*선임|CTO.*영입|핵심.*영입|회장.*취임/, 2},
      {~r/자사주.*소각|배당정책.*변경|주주환원/, 2},
      {~r/규제|법안|제재|금지|승인.*받|허가.*받/, 2},
      # ── 영문 ──
      {~r/\b(acquir|merger|takeover|spin.?off|divest|joint venture)/i, 3},
      {~r/\b(launches?|unveil|announc|debut|releas|rolls? out|introduces?)/i, 2},
      {~r/\b(partnership|collaboration|teaming up|alliance)/i, 2},
      {~r/\b(factory|fab|plant|gigafactory|capacity expansion|build.*new)/i, 3},
      {~r/\b(patent|licensing|technology transfer|IP deal)/i, 2},
      {~r/\b(CEO|CFO|CTO|chief)\s+(named|appointed|joins?|departs?|to step)/i, 2},
      {~r/\b(regulation|sanction|antitrust|export control|ban|approval)/i, 2}
    ]
  end

  # ────────────────────────────────────────────
  # 카테고리 추정 (LLM 에 hint 로 전달)
  # ────────────────────────────────────────────
  defp category_rules do
    [
      {~r/인수|합병|M&A|영업양수|acquir|merger|takeover/i, :ma},
      {~r/공장.*신설|시설투자|신규투자|factory|fab|plant|gigafactory|capacity/i, :capex},
      {~r/출시|공개|launch|unveil|releas|debut|양산/i, :product},
      {~r/공급계약|수주|MOU|파트너십|partnership|joint venture|collaboration/i, :partnership},
      {~r/특허|patent|licens/i, :ip},
      {~r/CEO|CTO|CFO|대표.*선임|영입|appointed|departs/i, :officer},
      {~r/규제|제재|법안|regulation|antitrust|sanction|ban|approval/i, :regulation},
      {~r/실적|매출|영업이익|earnings|revenue|guidance|quarter/i, :financial}
    ]
  end

  # ────────────────────────────────────────────
  # 공개 API
  # ────────────────────────────────────────────

  @doc "이 기사를 LLM 분석 단계로 보낼지 판단."
  def relevant?(%Event{} = ev) do
    text = full_text(ev)
    not blacklisted?(text)
  end

  @doc "기사에 :category, :base_score 부여."
  def categorize(%Event{} = ev) do
    text = full_text(ev)

    if blacklisted?(text) do
      %{ev | category: :rejected, base_score: 0}
    else
      %{ev | category: detect_category(text), base_score: compute_base_score(ev, text)}
    end
  end

  # ────────────────────────────────────────────
  defp full_text(%Event{title: title, description: desc}),
    do: "#{title} #{desc || ""}"

  defp blacklisted?(text), do: Enum.any?(blacklist(), &Regex.match?(&1, text))

  defp compute_base_score(%Event{source_tier: tier}, text) do
    boost =
      positives()
      |> Enum.reduce(0, fn {regex, b}, acc ->
        if Regex.match?(regex, text), do: acc + b, else: acc
      end)
      |> min(5)

    tier_mod =
      case tier do
        :specialist -> 1
        :major -> 0
        :general -> -1
        _ -> 0
      end

    (4 + boost + tier_mod) |> max(0) |> min(10)
  end

  defp detect_category(text) do
    Enum.find_value(category_rules(), :other, fn {regex, cat} ->
      if Regex.match?(regex, text), do: cat, else: nil
    end)
  end
end

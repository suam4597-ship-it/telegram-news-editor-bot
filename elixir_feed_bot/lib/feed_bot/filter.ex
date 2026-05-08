defmodule FeedBot.Filter do
  @moduledoc """
  채널 정체성을 결정하는 필터.

  대원칙
    ✅  사업의 실체적 변화 (사업영역·CAPEX·경쟁우위·거버넌스·자본배분)
    ❌  가격성·테마성 단기 신호, 일상적 자금조달, 보일러플레이트

  점수 가이드 (base_score, LLM이 참고)
    9-10  사업 방향이 근본적으로 바뀜 (M&A, 영업양수도, 통제권 변경, 파산)
    7-8   1년+ 영향 (대형 CAPEX, 핵심 계약, 자사주 소각, 핵심 인사)
    5-6   거버넌스/지분 변동 / 정기보고 / 일반적 자사주 매입
    3-4   판단 보류, 본문 보고 결정
    0-2   정정·일상 자금조달·이자지급 등 (대부분 reject로 잡힘)
  """

  alias FeedBot.Event

  # ────────────────────────────────────────────────────────────
  # DART 화이트리스트
  # ────────────────────────────────────────────────────────────
  # report_nm 기준 정규식. 위에서부터 순차 매칭.
  # 'ㆍ' (U+318D) 와 '·' (U+00B7) 는 둘 다 매칭하도록 [ㆍ·] 사용.
  defp dart_rules do
    [
      # ── M&A · 구조 변화 ──
      {~r/회사합병결정|회사분할결정|분할합병결정/, :ma, 10},
      {~r/영업양[수도][결정]|영업양수도|타법인주식.*취득.*결정|타법인.*출자증권.*취득/, :ma, 9},
      {~r/자회사.*편입|종속회사.*편입|합병등종료보고서/, :ma, 7},

      # ── CAPEX · 시설투자 ──
      # 신규시설투자는 가장 강한 신호 (사업 방향 + 자본 배분 모두)
      {~r/신규시설투자|시설투자.*결정|유형자산.*양수.*결정|공장.*신설|증설투자/, :capex, 9},

      # ── 대형 계약 · 수주 ──
      # 단일판매ㆍ공급계약체결 (유가증권시장: 매출 5%, 코스닥: 10% 초과 시 의무공시)
      {~r/단일판매[ㆍ·]공급계약/, :contract, 8},
      {~r/공급계약체결|수주공시/, :contract, 7},

      # ── 자사주 ──
      # 소각이 매입보다 신호 강함 (실제 유통주식 감소 = 영구적 자본 환원)
      {~r/자기주식.*소각.*결정/, :buyback, 8},
      {~r/자기주식.*취득.*결정/, :buyback, 6},
      {~r/자기주식.*처분.*결정/, :buyback, 6},
      # 단순 신탁계약은 약한 신호
      {~r/자기주식.*신탁/, :buyback, 4},

      # ── 자본 변동 (희석/구조 변화) ──
      {~r/제3자배정.*증자|유상증자.*결정/, :equity, 7},
      {~r/전환사채.*발행|신주인수권부사채.*발행|교환사채.*발행/, :equity, 6},
      {~r/주식매수선택권.*부여/, :stock_option, 5},

      # ── 지분 변동 ──
      # 5%룰 (대량보유) 보고는 시장 신호. 임원 거래는 노이즈가 많아 base_score 낮춤.
      {~r/주식등의대량보유상황보고/, :ownership, 7},
      {~r/임원[ㆍ·]주요주주.*소유상황보고/, :ownership, 4},

      # ── 거버넌스 / 임원 ──
      {~r/대표이사.*변경|대표이사.*선임|대표이사.*사임/, :ceo_change, 8},
      {~r/최대주주.*변경/, :control, 9},
      {~r/임원변경/, :officer, 4},

      # ── IP · 소송 ──
      {~r/특허권.*취득|특허.*소송|기술이전.*계약|라이선스.*계약/, :ip, 7},
      {~r/소송.*제기|소송.*피소|판결/, :litigation, 6},

      # ── 주주환원 정책 ──
      # 단발성 배당은 reject 쪽에서 잡힘. 정책 변경만 통과.
      {~r/배당정책.*변경|중간배당.*결정|주주환원/, :dividend_policy, 6},

      # ── 정기보고 (내용 기반 판단) ──
      {~r/^사업보고서$|^반기보고서$|^분기보고서$/, :periodic, 5}
    ]
  end

  # ────────────────────────────────────────────────────────────
  # DART 블랙리스트 (제목에 매칭되면 무조건 reject)
  # ────────────────────────────────────────────────────────────
  defp dart_blacklist do
    ~r/
      \[기재정정\] |
      \[첨부정정\] |
      \[첨부추가\] |
      확인서$ |
      이의제기 |
      ^결산실적공시$ |              # 단순 분기 숫자
      ^현금[ㆍ·]현물배당.*결정 |    # 정기 배당 (정책 변경은 화이트리스트가 잡음)
      무상증자.*결정 |              # 가격성 신호
      주식분할.*결정 |
      주식병합.*결정 |
      회사채.*발행 |                # 일상적 자금조달
      기업어음증권 |
      채무증권 |
      소액공모 |
      자산유동화
    /x
  end

  # ────────────────────────────────────────────────────────────
  # 8-K Item 가이드라인
  # ────────────────────────────────────────────────────────────
  # 참고: SEC Form 8-K General Instructions
  # https://www.sec.gov/about/forms/form8-k.pdf
  #
  # 의도적 제외:
  #   2.02  Results of Operations         (단순 분기 실적 발표)
  #   4.01  Auditor change                (대부분 노이즈)
  #   4.02  Non-reliance                  (회계 이슈, 별도 처리 필요)
  #   5.03  Articles amendments           (보일러플레이트)
  #   5.04  Code of ethics changes        (보일러플레이트)
  #   5.05  Code of ethics waivers
  #   5.06  Change in shell company status
  #   9.01  Financial statements          (다른 Item 의 첨부)
  @edgar_items %{
    # Section 1 - Registrant's Business and Operations
    # Material definitive agreement (key signal)
    "1.01" => {:contract, 8},
    # Termination of material agreement
    "1.02" => {:contract, 7},
    # Bankruptcy / receivership
    "1.03" => {:bankruptcy, 10},
    # Mine safety - reportable shutdown
    "1.04" => {:disaster, 8},
    # Material cybersecurity incident
    "1.05" => {:cybersecurity, 8},

    # Section 2 - Financial Information
    # Completion of acquisition / disposition
    "2.01" => {:ma, 9},
    # Material direct financial obligation
    "2.03" => {:debt, 5},
    # Triggering event accelerating obligation
    "2.04" => {:debt, 7},
    # Costs from exit / disposal activities
    "2.05" => {:restructure, 8},
    # Material impairment
    "2.06" => {:impairment, 7},

    # Section 3 - Securities and Trading Markets
    # Delisting / failure to satisfy listing
    "3.01" => {:listing, 8},
    # Unregistered sale of equity
    "3.02" => {:equity, 6},
    # Modification of holder rights
    "3.03" => {:equity, 5},

    # Section 5 - Corporate Governance and Management
    # Change in control of registrant
    "5.01" => {:control, 9},
    # Departure / appointment of director / officer
    "5.02" => {:officer, 7},
    # Submission of matters to vote of holders
    "5.07" => {:vote, 5},

    # Section 7 - Regulation FD
    # Reg FD disclosure (제목 따라 가산)
    "7.01" => {:reg_fd, 5},

    # Section 8 - Other Events
    # Other Events (issuer's discretion)
    "8.01" => {:other_material, 6}
  }

  # ────────────────────────────────────────────────────────────
  # 8-K title 가산점
  # ────────────────────────────────────────────────────────────
  # Item 만으로는 안 보이는 신호를 제목 키워드로 보강
  defp edgar_title_bonus do
    [
      {~r/\bacquir(e|ed|es|ing)|\bacquisition|\bmerger|\btakeover/i, 3},
      {~r/\bjoint venture|\bstrategic (alliance|partnership)/i, 2},
      {~r/\bspin.?off|\bdivest|\bdiscontinu/i, 2},
      {~r/\bbuyback|\bshare repurchase|\baccelerated repurchase/i, 2},
      {~r/\bdividend.*increas|\bspecial dividend/i, 1},
      {~r/\brestructur|\blayoff|\bworkforce reduction|\breduction in force/i, 2},
      {~r/\bguidance|\boutlook/i, 1},
      {~r/\bCEO|\bChief Executive|\bChief Financial|\bCFO|\bChief Operating/i, 1}
    ]
  end

  # ────────────────────────────────────────────────────────────
  # 공개 API
  # ────────────────────────────────────────────────────────────

  @doc "이 이벤트를 LLM 분석 단계로 보낼지 판단."
  def relevant?(%Event{} = ev) do
    case classify(ev) do
      {:ok, _, _} -> true
      :reject -> false
    end
  end

  @doc "이벤트에 :category 와 :base_score 부여."
  def categorize(%Event{} = ev) do
    case classify(ev) do
      {:ok, cat, score} -> %{ev | category: cat, base_score: score}
      :reject -> %{ev | category: :other, base_score: 0}
    end
  end

  # ── DART 분류 ─────────────────────────────────────────
  defp classify(%Event{source: :dart, title: title}) when is_binary(title) do
    if Regex.match?(dart_blacklist(), title) do
      :reject
    else
      Enum.find_value(dart_rules(), :reject, fn {regex, cat, score} ->
        if Regex.match?(regex, title), do: {:ok, cat, score}, else: nil
      end)
    end
  end

  # ── EDGAR 분류 ────────────────────────────────────────
  defp classify(%Event{source: :edgar, items: items, title: title})
       when is_list(items) and items != [] do
    items
    |> Enum.map(&Map.get(@edgar_items, &1))
    |> Enum.reject(&is_nil/1)
    |> case do
      [] ->
        :reject

      hits ->
        # 가장 높은 base_score를 가진 Item 선택 (한 8-K가 여러 Item 가질 때)
        {cat, base} = Enum.max_by(hits, fn {_, s} -> s end)
        bonus = title_bonus(title || "")
        {:ok, cat, min(base + bonus, 10)}
    end
  end

  # Items 추출 실패한 8-K/6-K도 일단 통과 (LLM이 본문 보고 판단)
  defp classify(%Event{source: :edgar, form_type: ft, title: title})
       when ft in ["8-K", "6-K"] do
    {:ok, :other_material, 4 + title_bonus(title || "")}
  end

  defp classify(_), do: :reject

  defp title_bonus(title) when is_binary(title) do
    edgar_title_bonus()
    |> Enum.reduce(0, fn {regex, b}, acc ->
      if Regex.match?(regex, title), do: acc + b, else: acc
    end)
    # 가산점 상한
    |> min(3)
  end
end

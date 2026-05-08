defmodule FeedBot.Sources.DART do
  @moduledoc """
  DART OpenAPI 클라이언트.

  list.json 으로 최근 공시 조회.
  pblntf_ty: A 정기공시 / B 주요사항보고 / D 지분공시

  자정 직후 어제 공시 누락을 막기 위해 항상 [어제, 오늘] 윈도우로 조회.
  중복은 Producer 의 in-memory seen + Dedup(ETS+DETS) 가 처리.
  """

  require Logger
  alias FeedBot.Event

  @endpoint "https://opendart.fss.or.kr/api/list.json"

  # 채널에 올릴 가치가 있는 공시 유형
  @publish_types ~w(B A D)

  # 페이지당 최대치(API 상한) + 페이지 폴링 한도(시간 보호)
  @page_count 100
  @max_pages 5

  @doc "최근 공시 목록을 Event 리스트로 반환."
  def fetch_recent do
    today = Date.utc_today()
    bgn_de = today |> Date.add(-1) |> Date.to_iso8601(:basic)
    end_de = today |> Date.to_iso8601(:basic)

    Enum.flat_map(@publish_types, &fetch_paginated(&1, bgn_de, end_de))
  end

  # ────────────────────────────────────────────────────────────
  # 페이지네이션 fetch
  # ────────────────────────────────────────────────────────────
  defp fetch_paginated(pblntf_ty, bgn_de, end_de) do
    case Application.get_env(:feed_bot, :dart_api_key) do
      nil ->
        Logger.warning("DART_API_KEY not set, skipping DART fetch")
        []

      api_key ->
        do_paginated(api_key, pblntf_ty, bgn_de, end_de, 1, [])
    end
  end

  defp do_paginated(_, _, _, _, page, acc) when page > @max_pages do
    Logger.warning("DART hit @max_pages=#{@max_pages}, possibly missing entries")
    acc
  end

  defp do_paginated(api_key, pblntf_ty, bgn_de, end_de, page, acc) do
    case do_fetch(api_key, pblntf_ty, bgn_de, end_de, page) do
      {:ok, list, total_page} ->
        acc = acc ++ Enum.map(list, &normalize/1)

        if page >= total_page do
          acc
        else
          do_paginated(api_key, pblntf_ty, bgn_de, end_de, page + 1, acc)
        end

      :empty ->
        acc

      :error ->
        acc
    end
  end

  defp do_fetch(api_key, pblntf_ty, bgn_de, end_de, page_no) do
    params = %{
      crtfc_key: api_key,
      bgn_de: bgn_de,
      end_de: end_de,
      pblntf_ty: pblntf_ty,
      page_count: @page_count,
      page_no: page_no,
      sort: "date",
      sort_mth: "desc"
    }

    case Req.get(@endpoint, params: params, receive_timeout: 15_000) do
      {:ok, %{status: 200, body: %{"status" => "000", "list" => list, "total_page" => tp}}}
      when is_list(list) ->
        {:ok, list, tp}

      {:ok, %{status: 200, body: %{"status" => "013"}}} ->
        # 데이터 없음
        :empty

      {:ok, %{status: 200, body: %{"status" => st, "message" => msg}}} ->
        Logger.warning("DART API status=#{st} msg=#{msg}")
        :error

      {:ok, %{status: status}} ->
        Logger.warning("DART HTTP #{status}")
        :error

      {:error, reason} ->
        Logger.error("DART fetch failed: #{inspect(reason)}")
        :error
    end
  end

  # ────────────────────────────────────────────────────────────
  # 정규화
  # ────────────────────────────────────────────────────────────
  defp normalize(
         %{
           "rcept_no" => rcept_no,
           "corp_name" => corp,
           "report_nm" => report,
           "rcept_dt" => rcept_dt
         } = raw
       ) do
    %Event{
      source: :dart,
      external_id: rcept_no,
      title: String.trim(report),
      url: "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=#{rcept_no}",
      published_at: parse_dart_date(rcept_dt),
      ticker: presence(raw["stock_code"]),
      company: corp,
      form_type: raw["pblntf_detail_ty"] || raw["pblntf_ty"],
      items: nil,
      raw: raw
    }
  end

  defp parse_dart_date(<<y::binary-4, m::binary-2, d::binary-2>>) do
    {:ok, dt, _} = DateTime.from_iso8601("#{y}-#{m}-#{d}T00:00:00Z")
    dt
  end

  defp presence(""), do: nil
  defp presence(nil), do: nil
  defp presence(s), do: s
end

defmodule FeedBot.Sources.RSS do
  @moduledoc """
  RSS 2.0 / Atom 통합 클라이언트.

  Floki 로 XML 파싱. 두 포맷 차이를 추상화해서 Event 로 정규화.

  지원:
    - RSS 2.0  : <channel><item>... <title> <link> <pubDate> <description>
    - Atom 1.0 : <feed><entry>... <title> <link href=""> <published> <summary>
    - dc:date  : Dublin Core 날짜 (일부 한국 매체)
  """

  require Logger
  alias FeedBot.Event

  @doc "피드 한 개 fetch → Event 리스트."
  def fetch(feed) do
    ua = Application.get_env(:feed_bot, :http_user_agent, "FeedBot/0.1")

    headers = [
      {"user-agent", ua},
      {"accept",
       "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.8"}
    ]

    case Req.get(feed.url, headers: headers, receive_timeout: 15_000) do
      {:ok, %{status: 200, body: body}} ->
        parse(body, feed)

      {:ok, %{status: 304}} ->
        []

      {:ok, %{status: status}} ->
        Logger.warning("Feed #{feed.name} returned HTTP #{status}")
        []

      {:error, reason} ->
        Logger.warning("Feed #{feed.name} fetch error: #{inspect(reason)}")
        []
    end
  end

  @doc "RSS/Atom XML 문자열을 Event 리스트로 파싱한다."
  def parse(xml, feed) do
    case Floki.parse_document(xml) do
      {:ok, doc} ->
        items = Floki.find(doc, "item") ++ Floki.find(doc, "entry")

        items
        |> Enum.map(&item_to_event(&1, feed))
        |> Enum.reject(&is_nil/1)

      {:error, reason} ->
        Logger.warning("Feed #{feed.name} parse error: #{inspect(reason)}")
        []
    end
  end

  # ──────────────────────────────────────────────────
  defp item_to_event(item, feed) do
    title = item |> Floki.find("title") |> first_text()
    raw_link = extract_link(item)
    pub = extract_pub_date(item)
    desc = extract_description(item)

    with t when is_binary(t) and t != "" <- title,
         l when is_binary(l) <- raw_link do
      url = canonical_url(l)

      %Event{
        source_id: feed.id,
        source_name: feed.name,
        source_tier: feed.tier,
        source_lang: feed.lang,
        external_id: url,
        title: t,
        url: url,
        description: desc,
        published_at: pub || DateTime.utc_now(),
        raw: %{}
      }
    else
      _ -> nil
    end
  end

  defp first_text([]), do: nil

  defp first_text([h | _]) do
    h
    |> Floki.text()
    |> strip_cdata()
    |> String.trim()
    |> presence()
  end

  defp strip_cdata(text) do
    String.replace(text, ~r/^<!\[CDATA\[(.*)\]\]>$/s, "\\1")
  end

  defp presence(""), do: nil
  defp presence(s), do: s

  # ── link: RSS 는 텍스트, Atom 은 href ───────────
  defp extract_link(item) do
    case item |> Floki.find("link") do
      [] ->
        nil

      links ->
        # Atom: <link href="..."/>
        href =
          links
          |> Floki.attribute("href")
          |> List.first()

        if href && href != "" do
          href
        else
          # RSS: <link>url</link>
          links |> first_text()
        end
    end
  end

  # ── description / summary / content ─────────────
  defp extract_description(item) do
    raw =
      item |> Floki.find("description") |> first_text() ||
        item |> Floki.find("summary") |> first_text() ||
        item |> Floki.find("content") |> first_text()

    if raw, do: clean_html(raw), else: nil
  end

  defp clean_html(str) do
    str
    |> String.replace(~r/<[^>]+>/, " ")
    |> String.replace(~r/&[a-z]+;|&#\d+;/i, " ")
    |> String.replace(~r/\s+/, " ")
    |> String.trim()
    |> String.slice(0, 500)
  end

  # ── 날짜 파싱: ISO 8601 / RFC 822 / dc:date ─────
  defp extract_pub_date(item) do
    raw =
      item |> Floki.find("pubDate") |> first_text() ||
        item |> Floki.find("published") |> first_text() ||
        item |> Floki.find("updated") |> first_text() ||
        item |> Floki.find("dc\\:date, date") |> first_text()

    parse_date(raw)
  end

  defp parse_date(nil), do: nil

  defp parse_date(str) do
    case DateTime.from_iso8601(str) do
      {:ok, dt, _} -> dt
      _ -> parse_rfc2822(str)
    end
  end

  # "Mon, 04 Mar 2024 10:00:00 +0900" / "GMT" / "UTC"
  defp parse_rfc2822(str) do
    case Regex.run(
           ~r/(\d{1,2})\s+(\w{3})\s+(\d{4})\s+(\d{2}):(\d{2}):(\d{2})\s+([+\-]\d{4}|\w+)/,
           str
         ) do
      [_, d, mon, y, h, mi, s, tz] ->
        with {:ok, naive} <-
               NaiveDateTime.new(
                 String.to_integer(y),
                 month_num(mon),
                 String.to_integer(d),
                 String.to_integer(h),
                 String.to_integer(mi),
                 String.to_integer(s)
               ),
             {:ok, dt} <- DateTime.from_naive(naive, "Etc/UTC") do
          DateTime.add(dt, -tz_offset(tz), :second)
        else
          _ -> nil
        end

      _ ->
        nil
    end
  end

  for {abbr, num} <-
        Enum.with_index(~w(Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec), 1) do
    defp month_num(unquote(abbr)), do: unquote(num)
  end

  defp month_num(_), do: 1

  defp tz_offset("GMT"), do: 0
  defp tz_offset("UTC"), do: 0
  defp tz_offset("Z"), do: 0

  defp tz_offset("+" <> <<h::binary-2, m::binary-2>>),
    do: String.to_integer(h) * 3600 + String.to_integer(m) * 60

  defp tz_offset("-" <> <<h::binary-2, m::binary-2>>),
    do: -(String.to_integer(h) * 3600 + String.to_integer(m) * 60)

  defp tz_offset(_), do: 0

  # ── URL 정규화 (utm 등 추적 파라미터 제거) ──────
  defp canonical_url(url) do
    case URI.parse(url) do
      %URI{} = uri ->
        uri
        |> Map.update(:query, nil, &strip_tracking/1)
        |> Map.put(:fragment, nil)
        |> URI.to_string()

      _ ->
        url
    end
  rescue
    _ -> url
  end

  defp strip_tracking(nil), do: nil

  defp strip_tracking(query) when is_binary(query) do
    query
    |> URI.decode_query()
    |> Enum.reject(fn {k, _} ->
      String.starts_with?(k, "utm_") or k in ~w(fbclid gclid igshid mc_eid mc_cid)
    end)
    |> case do
      [] -> nil
      pairs -> URI.encode_query(pairs)
    end
  end
end

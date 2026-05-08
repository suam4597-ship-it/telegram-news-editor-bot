defmodule FeedBot.FilterTest do
  use ExUnit.Case, async: true

  alias FeedBot.{Event, Filter}

  defp event(attrs) do
    struct!(
      Event,
      Map.merge(
        %{
          source: :dart,
          external_id: "test-id",
          title: "신규시설투자결정",
          url: "https://dart.fss.or.kr",
          published_at: DateTime.utc_now()
        },
        attrs
      )
    )
  end

  test "categorizes DART capex filings with high base score" do
    ev = Filter.categorize(event(%{title: "신규시설투자결정"}))

    assert ev.category == :capex
    assert ev.base_score == 9
  end

  test "rejects correction filings even when title contains a whitelist keyword" do
    ev = Filter.categorize(event(%{title: "[기재정정]신규시설투자결정"}))

    assert ev.category == :other
    assert ev.base_score == 0
    refute Filter.relevant?(ev)
  end

  test "adds EDGAR title bonus with a cap" do
    ev =
      event(%{
        source: :edgar,
        title: "Company announces acquisition and merger agreement with CEO transition",
        form_type: "8-K",
        items: ["1.01"]
      })
      |> Filter.categorize()

    assert ev.category == :contract
    assert ev.base_score == 10
  end
end

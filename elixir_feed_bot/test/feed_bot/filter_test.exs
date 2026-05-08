defmodule FeedBot.FilterTest do
  use ExUnit.Case, async: true

  alias FeedBot.{Event, Filter}

  defp event(attrs) do
    struct!(
      Event,
      Map.merge(
        %{
          source_id: :test,
          source_name: "테스트",
          source_tier: :major,
          source_lang: :ko,
          external_id: "https://example.com/a",
          title: "삼성전자, AI 반도체 공장 신설 발표",
          url: "https://example.com/a",
          description: ""
        },
        attrs
      )
    )
  end

  test "rejects price and theme style news" do
    ev = event(%{title: "반도체 수혜주 급등, 다음 대장주는?"})

    refute Filter.relevant?(ev)
    assert Filter.categorize(ev).base_score == 0
  end

  test "scores concrete industry events higher" do
    ev = event(%{}) |> Filter.categorize()

    assert ev.category == :capex
    assert ev.base_score >= 7
  end

  test "specialist sources receive tier bonus" do
    specialist = event(%{source_tier: :specialist}) |> Filter.categorize()
    general = event(%{source_tier: :general}) |> Filter.categorize()

    assert specialist.base_score > general.base_score
  end
end

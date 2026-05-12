defmodule FeedBot.TelegramTest do
  use ExUnit.Case, async: true

  alias FeedBot.{Event, Telegram}

  test "formats Telegram HTML and escapes external text" do
    event = %Event{
      source_id: :test,
      source_name: "Test & Source",
      source_tier: :major,
      source_lang: :en,
      external_id: "https://example.com/a",
      title: "Example <launch>",
      url: "https://example.com/a?x=1&y=2",
      category: :product,
      base_score: 8,
      importance: 8,
      summary: "Example, AI chip <launch>",
      impact: "HBM & foundry supply chain 확인 필요",
      delta: "이전 보도보다 일정이 앞당겨짐"
    }

    html = Telegram.format(event)

    assert html =~ "<b>제품/기술</b>"
    assert html =~ "Test &amp; Source"
    assert html =~ "AI chip &lt;launch&gt;"
    assert html =~ "• <b>요약</b>: Example &lt;launch&gt;"
    assert html =~ "HBM &amp; foundry"
    assert html =~ ~s(<a href="https://example.com/a?x=1&amp;y=2">원문</a>)
    refute html =~ "투자 권유"
    assert byte_size(html) <= Telegram.max_length()
  end
end

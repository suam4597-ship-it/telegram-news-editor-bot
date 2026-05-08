defmodule FeedBot.StoryDedupTest do
  use ExUnit.Case, async: false

  alias FeedBot.{Event, StoryDedup}

  setup do
    start_supervised!(StoryDedup)
    :ok
  end

  defp event(title, id) do
    %Event{
      source_id: :test,
      source_name: "테스트",
      source_tier: :major,
      source_lang: :ko,
      external_id: "https://example.com/#{id}",
      title: title,
      url: "https://example.com/#{id}"
    }
  end

  test "detects similar story titles within the window" do
    first = event("삼성전자, 미국 AI 반도체 공장 신설 발표", "a")
    second = event("삼성전자 미국 AI 반도체 공장 신설", "b")

    refute StoryDedup.duplicate?(first)
    assert :ok = StoryDedup.remember(first)
    assert StoryDedup.duplicate?(second)
  end
end

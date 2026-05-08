defmodule FeedBot.FeedsTest do
  use ExUnit.Case, async: true

  alias FeedBot.Sources.Feeds

  test "all feeds have required metadata and url" do
    feeds = Feeds.all()

    assert length(feeds) >= 10

    for feed <- feeds do
      assert is_atom(feed.id)
      assert is_binary(feed.name)
      assert feed.tier in [:specialist, :major, :general]
      assert feed.lang in [:ko, :en]
      assert String.starts_with?(feed.url, "http")
    end
  end
end

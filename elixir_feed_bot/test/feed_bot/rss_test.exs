defmodule FeedBot.RSSTest do
  use ExUnit.Case, async: true

  alias FeedBot.Sources.RSS

  test "strips tracking params from RSS links" do
    feed = %{id: :fixture, name: "Fixture", tier: :major, lang: :en, url: "unused"}

    xml = """
    <?xml version="1.0"?>
    <rss version="2.0">
      <channel>
        <item>
          <title><![CDATA[Example launches new AI chip]]></title>
          <link>https://example.com/story?utm_source=rss&amp;id=1&amp;gclid=abc</link>
          <description><![CDATA[Example <b>announced</b> a new chip.]]></description>
          <pubDate>Fri, 08 May 2026 12:00:00 +0900</pubDate>
        </item>
      </channel>
    </rss>
    """

    [event] = RSS.parse(xml, feed)

    assert event.title == "Example launches new AI chip"
    assert event.url == "https://example.com/story?id=1"
    assert event.description == "Example announced a new chip."
    assert event.source_name == "Fixture"
  end
end

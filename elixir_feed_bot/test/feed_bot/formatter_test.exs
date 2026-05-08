defmodule FeedBot.FormatterTest do
  use ExUnit.Case, async: true

  alias FeedBot.{Event, Formatter}

  test "formats Telegram HTML and escapes generated text" do
    ev = %Event{
      source: :dart,
      external_id: "1",
      title: "신규시설투자결정 & <script>",
      url: "https://example.com?a=1&b=2",
      published_at: DateTime.utc_now(),
      company: "테스트회사",
      form_type: "B001",
      category: :capex,
      base_score: 9,
      summary: "테스트회사, 신규시설투자 결정",
      impact: "생산능력 확대 여부 확인 필요",
      importance: 9
    }

    html = Formatter.telegram_html(ev)

    assert html =~ "<b>테스트회사, 신규시설투자 결정</b>"
    assert html =~ "신규시설투자결정 &amp; &lt;script&gt;"
    assert html =~ ~s(<a href="https://example.com?a=1&amp;b=2">DART</a>)
    assert html =~ "※ 정보 제공 목적이며 투자 권유가 아닙니다."
    assert byte_size(html) <= Formatter.max_length()
  end

  test "limits overly long messages" do
    ev = %Event{
      source: :edgar,
      external_id: "2",
      title: "Material Agreement",
      url: "https://sec.gov/example",
      published_at: DateTime.utc_now(),
      company: "Example",
      category: :contract,
      base_score: 8,
      summary: String.duplicate("긴제목", 2_000),
      impact: String.duplicate("긴영향", 2_000),
      importance: 8
    }

    html = Formatter.telegram_html(ev)

    assert byte_size(html) <= Formatter.max_length()
  end
end

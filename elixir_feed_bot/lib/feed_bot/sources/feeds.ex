defmodule FeedBot.Sources.Feeds do
  @moduledoc """
  RSS/Atom 피드 카탈로그.

  tier (Filter 의 base_score 에 영향):
    :specialist  +1  산업/기술 전문지 (높은 신호밀도)
    :major        0  주요 경제·테크 매체 (산업·기업 섹션 위주로)
    :general     -1  종합지·HN 등 (노이즈 많음)

  운영 메모:
    - 한국 일반 경제지는 '시황·증권' 섹션 말고 '산업·기업·IT' 섹션을 골라야 노이즈가 적다.
    - URL 은 시간이 지나면 바뀌므로 가끔 점검. 깨지면 로그에 경고가 뜬다.
    - 영문은 paywall 매체(WSJ, FT, Bloomberg, The Information) 제외. 필요시 직접 추가.
    - 추가 후보:
        ZDNet Korea, IT조선, 디지털데일리 (한국)
        Reuters Tech, 404 Media, Platformer (영문)
  """

  @feeds [
    # ── 한국 전문지 (specialist) ────────────────────
    %{
      id: :thelec,
      name: "디일렉",
      url: "https://www.thelec.kr/rss/allArticle.xml",
      tier: :specialist,
      lang: :ko,
      focus: "반도체·디스플레이·배터리"
    },

    # ── 한국 경제지 산업·기업 섹션 (major) ──────────
    %{
      id: :hankyung_it,
      name: "한국경제 IT",
      url: "https://www.hankyung.com/feed/it",
      tier: :major,
      lang: :ko,
      focus: "IT·반도체·테크"
    },
    %{
      id: :mk_corp,
      name: "매일경제 기업·경영",
      url: "https://www.mk.co.kr/rss/50100032/",
      tier: :major,
      lang: :ko,
      focus: "기업"
    },
    %{
      id: :etnews,
      name: "전자신문",
      url: "https://rss.etnews.com/Section902.xml",
      tier: :major,
      lang: :ko,
      focus: "산업·IT"
    },
    %{
      id: :fn_industry,
      name: "파이낸셜뉴스 산업",
      url: "https://www.fnnews.com/rss/r20/fn_realnews_industry.xml",
      tier: :major,
      lang: :ko,
      focus: "산업"
    },
    %{
      id: :fn_it,
      name: "파이낸셜뉴스 IT",
      url: "https://www.fnnews.com/rss/r20/fn_realnews_it.xml",
      tier: :major,
      lang: :ko,
      focus: "IT"
    },

    # ── 영문 전문 분석 (specialist) ────────────────
    %{
      id: :stratechery,
      name: "Stratechery",
      url: "https://stratechery.com/feed/",
      tier: :specialist,
      lang: :en,
      focus: "tech strategy"
    },
    %{
      id: :semianalysis,
      name: "SemiAnalysis",
      url: "https://semianalysis.com/feed/",
      tier: :specialist,
      lang: :en,
      focus: "semiconductors"
    },

    # ── 영문 주요 (major) ──────────────────────────
    %{
      id: :techcrunch,
      name: "TechCrunch",
      url: "https://techcrunch.com/feed/",
      tier: :major,
      lang: :en,
      focus: "startup·funding·product"
    },
    %{
      id: :verge,
      name: "The Verge",
      url: "https://www.theverge.com/rss/index.xml",
      tier: :major,
      lang: :en,
      focus: "tech consumer"
    },
    %{
      id: :arstechnica,
      name: "Ars Technica",
      url: "https://feeds.arstechnica.com/arstechnica/index/",
      tier: :major,
      lang: :en,
      focus: "tech depth"
    },
    %{
      id: :wired,
      name: "WIRED",
      url: "https://www.wired.com/feed/rss",
      tier: :major,
      lang: :en,
      focus: "tech culture"
    },

    # ── 커뮤니티 큐레이션 (general, 점수 강하게 보정) ──
    %{
      id: :hn,
      name: "Hacker News (200+)",
      url: "https://hnrss.org/frontpage?points=200",
      tier: :general,
      lang: :en,
      focus: "tech curated"
    }
  ]

  def all, do: @feeds
  def by_id(id), do: Enum.find(@feeds, &(&1.id == id))
end

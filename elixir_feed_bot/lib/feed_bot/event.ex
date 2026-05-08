defmodule FeedBot.Event do
  @moduledoc """
  뉴스 기사의 정규화된 형태.
  파이프라인의 모든 단계에서 이 구조체를 주고받는다.
  """

  @enforce_keys [:source_id, :source_name, :title, :url, :external_id]
  defstruct [
    # 매체 정보 (Feeds.ex 에서 주입)
    # atom, 예: :hankyung_industry
    :source_id,
    # 표시용, 예: "한국경제 산업"
    :source_name,
    # :specialist | :major | :general
    :source_tier,
    # :ko | :en
    :source_lang,

    # 기사 자체
    # canonical URL (utm 파라미터 제거됨) — dedup 키
    :external_id,
    :title,
    :url,
    # RSS 제공 요약 (있을 때만, HTML 제거됨, 500자 컷)
    :description,
    :published_at,
    # 디버그용
    :raw,

    # Filter 가 채움
    # :ma | :capex | :product | :partnership | :ip | :officer | :regulation | :financial | :other
    :category,
    # 0..10 룰 기반 사전 점수
    :base_score,

    # LLM 이 채움
    # 0..10 최종 점수 (컷오프 기준)
    :importance,
    # 한 줄 요약 (텔레그램에 들어가는 본문)
    :summary,
    # 영향 범위
    :impact,
    # 이전 보도 대비 변화 (있으면)
    :delta
  ]

  @type t :: %__MODULE__{}
end

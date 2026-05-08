defmodule FeedBot.Event do
  @moduledoc """
  공시·이벤트의 정규화된 형태.
  파이프라인의 모든 단계에서 이 구조체를 주고받는다.
  """

  @enforce_keys [:source, :external_id, :title, :url, :published_at]
  defstruct [
    # :dart | :edgar
    :source,
    # 소스별 고유 ID (rcept_no, accession_number 등)
    :external_id,
    # 공시 제목 / 양식명
    :title,
    # 1차 자료 링크
    :url,
    # DateTime
    :published_at,
    # 종목 코드 (있으면)
    :ticker,
    # 기업명
    :company,
    # "8-K", "B001" 등
    :form_type,
    # 8-K Items 리스트, DART 상세타입 등
    :items,
    # 원본 페이로드 (디버그·재처리용)
    :raw,

    # Filter가 채우는 것
    # :ma | :capex | :contract | :officer | ...
    :category,
    # 0..10. 룰 기반 사전 점수 → LLM에 anchor로 전달
    :base_score,

    # LLM이 채우는 것
    # 0..10. 최종 컷오프에 사용
    :importance,
    # 한 줄 요약
    :summary,
    # 영향 범위
    :impact,
    # 이전 대비 변화 (있으면)
    :delta
  ]

  @type t :: %__MODULE__{}
end

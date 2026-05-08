defmodule FeedBot.Pipeline do
  @moduledoc """
  Broadway 메인 파이프라인.

  Producer → handle_message:
    1. URL Dedup (이미 본 기사면 drop)
    2. Filter.relevant?  (블랙리스트 키워드 체크)
    3. StoryDedup        (최근 6시간 내 같은 사건 보도면 drop)
    4. Filter.categorize (category, base_score)
    5. LLM.enrich        (summary, impact, delta, importance)
    6. importance 컷오프 통과시 발행
  """

  use Broadway
  require Logger

  alias Broadway.Message
  alias FeedBot.{Dedup, Event, Filter, LLM, StoryDedup, Telegram}

  def start_link(_opts) do
    Broadway.start_link(__MODULE__,
      name: __MODULE__,
      producer: [
        module: {FeedBot.Sources.Producer, []},
        concurrency: 1,
        transformer: {__MODULE__, :transform, []}
      ],
      processors: [
        default: [concurrency: 4, max_demand: 10]
      ]
    )
  end

  @doc false
  def transform(%Event{} = event, _opts) do
    %Message{
      data: event,
      acknowledger: Broadway.NoopAcknowledger.init()
    }
  end

  @impl true
  def handle_message(_processor, %Message{data: %Event{} = event} = msg, _ctx) do
    threshold = Application.get_env(:feed_bot, :importance_threshold, 7)

    cond do
      Dedup.seen?(event) ->
        Message.failed(msg, "url_duplicate")

      not Filter.relevant?(event) ->
        Dedup.mark(event)
        Message.failed(msg, "filtered_out")

      StoryDedup.duplicate?(event) ->
        Dedup.mark(event)
        Logger.debug("Story dup: #{event.title}")
        Message.failed(msg, "story_duplicate")

      true ->
        event = event |> Filter.categorize() |> LLM.enrich()

        if event.importance >= threshold do
          Dedup.mark(event)
          StoryDedup.remember(event)
          Telegram.publish(event)

          Logger.info("Published [#{event.importance}] #{event.source_name}: #{event.title}")

          Message.put_data(msg, event)
        else
          Dedup.mark(event)
          Logger.debug("Below threshold (#{event.importance}): #{event.title}")
          Message.failed(msg, "below_threshold")
        end
    end
  end
end

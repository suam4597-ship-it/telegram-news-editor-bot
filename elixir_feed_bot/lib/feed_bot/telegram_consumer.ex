defmodule FeedBot.TelegramConsumer do
  @moduledoc """
  Producer에서 들어온 이벤트를 필터링, LLM 보강, 텔레그램 발행까지 처리하는 Consumer.

  처리 흐름:
    Event -> Filter.categorize -> LLM.enrich -> Formatter.telegram_html -> Telegram.sendMessage

  성공/폐기된 이벤트는 Dedup에 영속 마킹한다.
  텔레그램 발행 실패 이벤트는 영속 마킹하지 않아 재시작 후 재시도 여지를 남긴다.
  """

  use GenStage
  require Logger

  alias FeedBot.{Dedup, Event, Filter, Formatter, LLM, Telegram}

  def start_link(opts \\ []) do
    GenStage.start_link(__MODULE__, opts, name: __MODULE__)
  end

  @impl true
  def init(opts) do
    producer = Keyword.get(opts, :producer, FeedBot.Sources.Producer)

    state = %{
      min_importance:
        Keyword.get(opts, :min_importance, Application.get_env(:feed_bot, :min_importance, 7)),
      dry_run: Keyword.get(opts, :dry_run, Application.get_env(:feed_bot, :dry_run, false))
    }

    {:consumer, state, subscribe_to: [producer]}
  end

  @impl true
  def handle_events(events, _from, state) do
    Enum.each(events, &handle_event(&1, state))
    {:noreply, [], state}
  end

  defp handle_event(%Event{} = ev, state) do
    ev = Filter.categorize(ev)

    cond do
      ev.base_score == 0 ->
        Logger.debug("Rejected by filter: #{ev.title}")
        Dedup.mark(ev)

      true ->
        ev
        |> LLM.enrich()
        |> maybe_publish(state)
    end
  rescue
    e ->
      Logger.error(
        "TelegramConsumer failed for #{inspect(ev.external_id)}: #{Exception.message(e)}"
      )
  end

  defp maybe_publish(%Event{importance: importance} = ev, %{min_importance: min} = state)
       when is_integer(importance) and importance >= min do
    message = Formatter.telegram_html(ev)

    if state.dry_run do
      Logger.info("DRY_RUN Telegram message:\n#{message}")
      Dedup.mark(ev)
    else
      case Telegram.send_message(message) do
        {:ok, response} ->
          message_id = get_in(response, ["result", "message_id"])
          Logger.info("Published #{ev.external_id} to Telegram message_id=#{inspect(message_id)}")
          Dedup.mark(ev)

        {:error, reason} ->
          Logger.error("Telegram publish failed for #{ev.external_id}: #{inspect(reason)}")
      end
    end
  end

  defp maybe_publish(%Event{} = ev, %{min_importance: min}) do
    Logger.debug(
      "Skipped low-importance event #{ev.external_id}: #{inspect(ev.importance)}/10 < #{min}"
    )

    Dedup.mark(ev)
  end
end

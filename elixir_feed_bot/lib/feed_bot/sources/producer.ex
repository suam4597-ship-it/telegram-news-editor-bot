defmodule FeedBot.Sources.Producer do
  @moduledoc """
  설정된 모든 RSS 피드를 병렬 폴링하는 GenStage producer.

  - 첫 폴은 warmup: fetch만 하고 emit 안 함, 모두 Dedup 에 마크.
    (콜드스타트에 LLM/텔레그램 폭주 방지)
  - 두 번째 폴부터 새 항목만 emit.
  - in-memory seen 은 같은 세션 내 빠른 패스용 (10,000건 LRU).
  """

  use GenStage
  require Logger

  alias FeedBot.Dedup
  alias FeedBot.Sources.{Feeds, RSS}

  @max_seen 10_000

  def start_link(opts), do: GenStage.start_link(__MODULE__, opts, name: __MODULE__)

  @impl true
  def init(_) do
    interval = Application.get_env(:feed_bot, :poll_interval_ms, 5 * 60 * 1_000)
    Process.send_after(self(), :poll, 5_000)

    {:producer,
     %{
       interval: interval,
       seen: MapSet.new(),
       seen_order: :queue.new(),
       warmup_done: false
     }}
  end

  @impl true
  def handle_demand(_demand, state), do: {:noreply, [], state}

  # ── 첫 폴: warmup ──
  @impl true
  def handle_info(:poll, %{warmup_done: false} = state) do
    Process.send_after(self(), :poll, state.interval)
    events = fetch_all_feeds()

    state =
      Enum.reduce(events, state, fn ev, st ->
        Dedup.mark(ev)
        remember(st, ev.external_id)
      end)

    Logger.info("Producer warmup complete: marked #{length(events)} articles as seen")
    {:noreply, [], %{state | warmup_done: true}}
  end

  # ── 정상 폴 ──
  @impl true
  def handle_info(:poll, state) do
    Process.send_after(self(), :poll, state.interval)
    events = fetch_all_feeds()

    {new_events, state} =
      Enum.reduce(events, {[], state}, fn ev, {acc, st} ->
        cond do
          MapSet.member?(st.seen, ev.external_id) ->
            {acc, st}

          Dedup.seen?(ev) ->
            {acc, remember(st, ev.external_id)}

          true ->
            {[ev | acc], remember(st, ev.external_id)}
        end
      end)

    if new_events != [],
      do: Logger.info("Producer emitting #{length(new_events)} new articles")

    {:noreply, Enum.reverse(new_events), state}
  end

  # ──────────────────────────────────────────────────
  defp fetch_all_feeds do
    Feeds.all()
    |> Enum.map(fn feed -> Task.async(fn -> safe_fetch(feed) end) end)
    |> Enum.flat_map(&Task.await(&1, 30_000))
  end

  defp safe_fetch(feed) do
    RSS.fetch(feed)
  rescue
    e ->
      Logger.error("Feed #{feed.name} raised: #{Exception.message(e)}")
      []
  end

  defp remember(state, id) do
    seen = MapSet.put(state.seen, id)
    queue = :queue.in(id, state.seen_order)

    if MapSet.size(seen) > @max_seen do
      {{:value, old}, q2} = :queue.out(queue)
      %{state | seen: MapSet.delete(seen, old), seen_order: q2}
    else
      %{state | seen: seen, seen_order: queue}
    end
  end
end

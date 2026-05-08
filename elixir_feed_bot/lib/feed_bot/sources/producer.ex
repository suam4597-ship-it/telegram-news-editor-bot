defmodule FeedBot.Sources.Producer do
  @moduledoc """
  여러 소스를 통합 폴링하는 GenStage producer.

  - poll_interval_ms 마다 DART, EDGAR 병렬 호출
  - 첫 폴은 'warmup': fetch만 하고 emit 하지 않는다.
    (DETS dedup 이 비어 있는 cold-start에서 2일치 공시가 한꺼번에
     LLM·텔레그램으로 쏟아지는 것을 방지)
  - 두 번째 폴부터 새 이벤트만 emit
  - in-memory seen은 5,000건 LRU (Dedup 영속화와 별도, 같은 세션 내 빠른 패스용)
  """

  use GenStage
  require Logger

  alias FeedBot.Dedup
  alias FeedBot.Sources.{DART, EDGAR}

  @max_seen 5_000

  def start_link(opts) do
    GenStage.start_link(__MODULE__, opts, name: __MODULE__)
  end

  @impl true
  def init(_opts) do
    interval = Application.get_env(:feed_bot, :poll_interval_ms, 60_000)
    Process.send_after(self(), :poll, 1_000)

    state = %{
      interval: interval,
      seen: MapSet.new(),
      seen_order: :queue.new(),
      warmup_done: false
    }

    {:producer, state}
  end

  @impl true
  def handle_demand(_demand, state), do: {:noreply, [], state}

  # ── 첫 폴: warmup ─────────────────────────────────────
  @impl true
  def handle_info(:poll, %{warmup_done: false} = state) do
    Process.send_after(self(), :poll, state.interval)
    events = fetch_all()

    # 모두 'seen' 으로 표시 (in-memory + Dedup DETS 양쪽).
    # emit 은 하지 않음.
    state =
      Enum.reduce(events, state, fn ev, st ->
        Dedup.mark(ev)
        remember(st, ev.external_id)
      end)

    Logger.info("Producer warmup complete, marked #{length(events)} events as seen")
    {:noreply, [], %{state | warmup_done: true}}
  end

  # ── 이후 폴: 정상 ─────────────────────────────────────
  @impl true
  def handle_info(:poll, state) do
    Process.send_after(self(), :poll, state.interval)
    events = fetch_all()

    {new_events, state} =
      Enum.reduce(events, {[], state}, fn ev, {acc, st} ->
        cond do
          MapSet.member?(st.seen, ev.external_id) ->
            {acc, st}

          Dedup.seen?(ev) ->
            # 다른 노드/이전 세션에서 본 것 → in-memory만 갱신
            {acc, remember(st, ev.external_id)}

          true ->
            {[ev | acc], remember(st, ev.external_id)}
        end
      end)

    if new_events != [] do
      Logger.info("Producer emitting #{length(new_events)} new events")
    end

    {:noreply, Enum.reverse(new_events), state}
  end

  # ────────────────────────────────────────────────────────────
  defp fetch_all do
    [DART, EDGAR]
    |> Enum.map(fn mod -> Task.async(fn -> safe_source(mod) end) end)
    |> Enum.flat_map(&Task.await(&1, 60_000))
  end

  defp safe_source(mod) do
    if Code.ensure_loaded?(mod) and function_exported?(mod, :fetch_recent, 0) do
      safe(fn -> mod.fetch_recent() end)
    else
      Logger.debug("#{inspect(mod)}.fetch_recent/0 not available, skipping source")
      []
    end
  end

  defp safe(fun) do
    fun.()
  rescue
    e ->
      Logger.error("Source raised: #{Exception.message(e)}")
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

defmodule FeedBot.Dedup do
  @moduledoc """
  external_id 기반 중복 감지.

  설계
    - Hot path (seen?): ETS in-memory lookup
    - Persistence:      DETS 파일 (auto_save 60s)
    - 시작 시 DETS → ETS 로 로드 → 재시작 후에도 중복 발송 없음
    - TTL 7일, 1시간마다 sweep

  운영 단계에서 더 큰 신뢰성이 필요하면 DETS 부분을
  Postgres / Redis 로 교체하면 됨 (인터페이스 동일).
  """

  use GenServer
  require Logger

  alias FeedBot.Event

  @ets :feed_bot_dedup_cache
  @dets :feed_bot_dedup_disk
  @ttl_ms 7 * 24 * 60 * 60 * 1_000
  @sweep_interval 60 * 60 * 1_000
  @path "./feed_bot_dedup.dets"

  def start_link(_opts), do: GenServer.start_link(__MODULE__, [], name: __MODULE__)

  @doc "이미 본 이벤트인지 (ETS만 조회 → 마이크로초 단위)."
  @spec seen?(Event.t()) :: boolean
  def seen?(%Event{external_id: id}), do: :ets.member(@ets, id)

  @doc "이벤트를 seen 으로 표시 (ETS + DETS 양쪽)."
  @spec mark(Event.t()) :: :ok
  def mark(%Event{external_id: id}) do
    now = System.system_time(:millisecond)
    :ets.insert(@ets, {id, now})
    :dets.insert(@dets, {id, now})
    :ok
  end

  # ────────────────────────────────────────────────────────────
  @impl true
  def init(_) do
    :ets.new(@ets, [:named_table, :public, :set, read_concurrency: true])

    {:ok, _} =
      :dets.open_file(@dets,
        type: :set,
        file: String.to_charlist(@path),
        auto_save: 60_000
      )

    # DETS → ETS 로드, 그 과정에서 만료된 것도 정리
    cutoff = System.system_time(:millisecond) - @ttl_ms

    {loaded, expired} =
      :dets.foldl(
        fn {id, ts} = entry, {l, e} ->
          if ts < cutoff do
            :dets.delete(@dets, id)
            {l, e + 1}
          else
            :ets.insert(@ets, entry)
            {l + 1, e}
          end
        end,
        {0, 0},
        @dets
      )

    Logger.info("Dedup loaded #{loaded} entries (expired #{expired})")
    Process.send_after(self(), :sweep, @sweep_interval)
    {:ok, %{}}
  end

  @impl true
  def handle_info(:sweep, state) do
    cutoff = System.system_time(:millisecond) - @ttl_ms
    match = [{{:_, :"$1"}, [{:<, :"$1", cutoff}], [true]}]

    e = :ets.select_delete(@ets, match)
    d = :dets.select_delete(@dets, match)
    if e + d > 0, do: Logger.debug("Dedup sweep: ets=#{e} dets=#{d}")

    Process.send_after(self(), :sweep, @sweep_interval)
    {:noreply, state}
  end

  @impl true
  def terminate(_reason, _state) do
    :dets.sync(@dets)
    :dets.close(@dets)
    :ok
  end
end

defmodule FeedBot.StoryDedup do
  @moduledoc """
  같은 사건을 여러 매체가 보도할 때 중복 발행 방지.

  방법
    - 정규화된 제목의 trigram(3-gram) Set 으로 시그너처 생성
    - 6시간 윈도우 내 Jaccard 유사도 ≥ 0.55 이면 중복으로 판단
    - First-come-first-served. 더 좋은 매체로 교체하려면
      hold-and-release 로직(5분 hold 후 best 선택)을 추가하면 됨.

  한계
    - URL 기반 Dedup 과 별개 (URL 은 다르지만 내용 같은 케이스 잡음)
    - 짧은 제목(< 5 trigram)은 비교 안 함 (오탐 방지)
    - in-memory 만 — 재시작 시 6시간 윈도우 비워짐 (영속화 비용 대비 가치 낮음)
  """

  use GenServer
  require Logger

  alias FeedBot.Event

  @ets :feed_bot_story_sigs
  @ttl_ms 6 * 60 * 60 * 1_000
  @sweep_interval 30 * 60 * 1_000
  @sim_threshold 0.55
  @min_shingles 5

  def start_link(_opts), do: GenServer.start_link(__MODULE__, [], name: __MODULE__)

  @doc "이미 본 스토리와 유사한가? 발행 직전에 호출."
  @spec duplicate?(Event.t()) :: boolean
  def duplicate?(%Event{title: title}) do
    sig = shingles(title)

    if MapSet.size(sig) < @min_shingles do
      false
    else
      cutoff = System.system_time(:millisecond) - @ttl_ms

      :ets.foldl(
        fn {_, sigs, ts}, acc ->
          cond do
            acc -> acc
            ts < cutoff -> false
            jaccard(sig, sigs) >= @sim_threshold -> true
            true -> false
          end
        end,
        false,
        @ets
      )
    end
  end

  @doc "이 스토리를 봤다고 표시 (발행 후 호출)."
  @spec remember(Event.t()) :: :ok
  def remember(%Event{external_id: id, title: title}) do
    sig = shingles(title)

    if MapSet.size(sig) >= @min_shingles do
      :ets.insert(@ets, {id, sig, System.system_time(:millisecond)})
    end

    :ok
  end

  # ────────────────────────────────────────────
  @impl true
  def init(_) do
    :ets.new(@ets, [:named_table, :public, :set, read_concurrency: true])
    Process.send_after(self(), :sweep, @sweep_interval)
    {:ok, %{}}
  end

  @impl true
  def handle_info(:sweep, state) do
    cutoff = System.system_time(:millisecond) - @ttl_ms
    deleted = :ets.select_delete(@ets, [{{:_, :_, :"$1"}, [{:<, :"$1", cutoff}], [true]}])
    if deleted > 0, do: Logger.debug("StoryDedup sweep: removed #{deleted}")
    Process.send_after(self(), :sweep, @sweep_interval)
    {:noreply, state}
  end

  # ────────────────────────────────────────────
  defp shingles(text) do
    text
    |> normalize()
    |> String.codepoints()
    |> Enum.chunk_every(3, 1, :discard)
    |> Enum.map(&Enum.join/1)
    |> MapSet.new()
  end

  # 영문은 lowercase + 알파넘만, 한글은 그대로 유지
  defp normalize(s) do
    s
    |> String.downcase()
    |> String.replace(~r/[^\p{L}\p{N}]+/u, "")
  end

  defp jaccard(a, b) do
    inter = MapSet.intersection(a, b) |> MapSet.size()
    union = MapSet.union(a, b) |> MapSet.size()
    if union == 0, do: 0.0, else: inter / union
  end
end

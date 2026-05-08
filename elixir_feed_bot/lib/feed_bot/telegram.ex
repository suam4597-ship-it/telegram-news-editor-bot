defmodule FeedBot.Telegram do
  @moduledoc """
  텔레그램 봇 발행자.

  Telegram HTML parse mode만 사용한다. 모델/외부 입력에서 온 텍스트는 이 모듈에서
  escape한 뒤 태그를 붙인다.
  """

  use GenServer
  require Logger

  alias FeedBot.Event

  @endpoint "https://api.telegram.org/bot"
  @rate_ms 1_200
  @max_length 3_500

  def start_link(_opts), do: GenServer.start_link(__MODULE__, [], name: __MODULE__)

  @doc "이벤트를 발행 큐에 넣는다 (비동기)."
  def publish(%Event{} = ev), do: GenServer.cast(__MODULE__, {:publish, ev})

  @doc "Telegram HTML 메시지를 deterministic하게 생성한다."
  @spec format(Event.t()) :: String.t()
  def format(%Event{} = ev) do
    delta_line =
      case present(ev.delta) do
        nil -> nil
        delta -> "• <b>변화</b>: #{esc(delta)}"
      end

    [
      "<b>#{esc(cat_label(ev.category))}</b> · <i>#{esc(ev.source_name)}</i>",
      "",
      "<b>#{esc(ev.summary || ev.title)}</b>",
      "",
      "• <b>시사점</b>: #{esc(ev.impact || "원문 확인이 필요합니다.")}",
      delta_line,
      "",
      "출처: <a href=\"#{esc_attr(ev.url)}\">원문</a>",
      "※ 정보 제공 목적이며 투자 권유가 아닙니다."
    ]
    |> Enum.reject(&(&1 in [nil, ""]))
    |> Enum.join("\n")
    |> trim_to_limit()
  end

  @spec max_length() :: pos_integer()
  def max_length, do: @max_length

  @impl true
  def init(_) do
    schedule_tick()
    {:ok, %{queue: :queue.new()}}
  end

  @impl true
  def handle_cast({:publish, ev}, state) do
    {:noreply, %{state | queue: :queue.in(ev, state.queue)}}
  end

  @impl true
  def handle_info(:tick, state) do
    schedule_tick()

    case :queue.out(state.queue) do
      {{:value, ev}, q2} ->
        send_message(ev)
        {:noreply, %{state | queue: q2}}

      {:empty, _} ->
        {:noreply, state}
    end
  end

  defp send_message(%Event{} = ev) do
    message = format(ev)

    if Application.get_env(:feed_bot, :dry_run, false) do
      Logger.info("DRY_RUN Telegram message:\n#{message}")
      :ok
    else
      do_send_message(message)
    end
  end

  defp do_send_message(message) do
    token = Application.get_env(:feed_bot, :telegram_bot_token)
    chat_id = Application.get_env(:feed_bot, :telegram_chat_id)

    cond do
      is_nil(token) or token == "" ->
        Logger.warning("Telegram credentials missing — would have sent:\n#{message}")
        :ok

      is_nil(chat_id) or chat_id == "" ->
        Logger.warning("Telegram chat id missing — would have sent:\n#{message}")
        :ok

      true ->
        url = @endpoint <> token <> "/sendMessage"

        body = %{
          chat_id: chat_id,
          text: message,
          parse_mode: "HTML",
          disable_web_page_preview: false
        }

        case Req.post(url, json: body, receive_timeout: 15_000) do
          {:ok, %{status: 200}} ->
            :ok

          {:ok, %{status: 429, body: %{"parameters" => %{"retry_after" => seconds}}}} ->
            wait_ms = min(seconds * 1_000, 30_000)
            Logger.warning("Telegram rate limited, retrying after #{wait_ms}ms")
            Process.sleep(wait_ms)
            Req.post(url, json: body, receive_timeout: 15_000)
            :ok

          {:ok, %{status: status, body: body}} ->
            Logger.warning("Telegram #{status}: #{inspect(body)}")
            :ok

          {:error, reason} ->
            Logger.error("Telegram error: #{inspect(reason)}")
            :ok
        end
    end
  end

  defp cat_label(:ma), do: "M&A"
  defp cat_label(:capex), do: "CAPEX"
  defp cat_label(:product), do: "제품/기술"
  defp cat_label(:partnership), do: "협력"
  defp cat_label(:ip), do: "특허/IP"
  defp cat_label(:officer), do: "임원"
  defp cat_label(:regulation), do: "규제"
  defp cat_label(:financial), do: "재무"
  defp cat_label(:other), do: "산업 뉴스"
  defp cat_label(_), do: "뉴스"

  defp present(nil), do: nil
  defp present(""), do: nil
  defp present(value) when is_binary(value), do: String.trim(value) |> empty_to_nil()
  defp present(value), do: value

  defp empty_to_nil(""), do: nil
  defp empty_to_nil(value), do: value

  defp esc(value) do
    value
    |> to_string()
    |> String.replace("&", "&amp;")
    |> String.replace("<", "&lt;")
    |> String.replace(">", "&gt;")
  end

  defp esc_attr(value) do
    value
    |> esc()
    |> String.replace("\"", "&quot;")
  end

  defp trim_to_limit(text) when byte_size(text) <= @max_length, do: text

  defp trim_to_limit(text) do
    ellipsis = "…"
    limit = @max_length - byte_size(ellipsis)

    {graphemes, _bytes} =
      text
      |> String.graphemes()
      |> Enum.reduce_while({[], 0}, fn grapheme, {acc, bytes} ->
        next_bytes = bytes + byte_size(grapheme)

        if next_bytes > limit do
          {:halt, {acc, bytes}}
        else
          {:cont, {[grapheme | acc], next_bytes}}
        end
      end)

    graphemes
    |> Enum.reverse()
    |> Enum.join()
    |> Kernel.<>(ellipsis)
  end

  defp schedule_tick, do: Process.send_after(self(), :tick, @rate_ms)
end

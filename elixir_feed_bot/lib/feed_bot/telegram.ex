defmodule FeedBot.Telegram do
  @moduledoc """
  Telegram Bot API sendMessage 클라이언트.

  설정:
    config :feed_bot,
      telegram_bot_token: System.get_env("TELEGRAM_BOT_TOKEN"),
      telegram_chat_id: System.get_env("TELEGRAM_CHANNEL_ID")
  """

  require Logger

  @endpoint "https://api.telegram.org/bot"

  @doc "HTML parse mode로 텔레그램 채널/채팅에 메시지를 보낸다."
  @spec send_message(String.t(), keyword()) :: {:ok, map()} | {:error, term()}
  def send_message(text, opts \\ []) when is_binary(text) do
    token = Keyword.get(opts, :token) || Application.get_env(:feed_bot, :telegram_bot_token)

    chat_id =
      Keyword.get(opts, :chat_id) ||
        Application.get_env(:feed_bot, :telegram_chat_id) ||
        Application.get_env(:feed_bot, :telegram_channel_id)

    cond do
      is_nil(token) or token == "" ->
        {:error, :missing_telegram_bot_token}

      is_nil(chat_id) or chat_id == "" ->
        {:error, :missing_telegram_chat_id}

      true ->
        do_send(token, chat_id, text, opts, true)
    end
  end

  defp do_send(token, chat_id, text, opts, retry?) do
    url = @endpoint <> token <> "/sendMessage"

    body = %{
      chat_id: chat_id,
      text: text,
      parse_mode: "HTML",
      disable_web_page_preview: Keyword.get(opts, :disable_web_page_preview, false)
    }

    case Req.post(url, json: body, receive_timeout: 15_000) do
      {:ok, %{status: 200, body: %{"ok" => true} = response}} ->
        {:ok, response}

      {:ok, %{status: 429, body: %{"parameters" => %{"retry_after" => seconds}}}}
      when retry? and is_integer(seconds) ->
        wait_ms = min(seconds * 1_000, 30_000)
        Logger.warning("Telegram rate limited, retrying after #{wait_ms}ms")
        Process.sleep(wait_ms)
        do_send(token, chat_id, text, opts, false)

      {:ok, %{status: status, body: body}} ->
        {:error, {:telegram_http, status, body}}

      {:error, reason} ->
        {:error, reason}
    end
  end
end

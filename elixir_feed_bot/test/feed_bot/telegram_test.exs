defmodule FeedBot.TelegramTest do
  use ExUnit.Case, async: true

  test "returns a clear error when token is missing" do
    assert {:error, :missing_telegram_bot_token} =
             FeedBot.Telegram.send_message("test", token: nil, chat_id: "@channel")
  end
end

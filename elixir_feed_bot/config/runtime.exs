import Config

config :feed_bot,
  dart_api_key: System.get_env("DART_API_KEY"),
  anthropic_api_key: System.get_env("ANTHROPIC_API_KEY"),
  llm_model: System.get_env("ANTHROPIC_MODEL") || "claude-haiku-4-5-20251001",
  telegram_bot_token: System.get_env("TELEGRAM_BOT_TOKEN"),
  telegram_chat_id:
    System.get_env("TELEGRAM_CHANNEL_ID") ||
      System.get_env("TELEGRAM_PUBLIC_CHANNEL_ID"),
  poll_interval_ms:
    System.get_env("POLL_INTERVAL_MS", "60000")
    |> String.to_integer(),
  min_importance:
    System.get_env("MIN_IMPORTANCE", "7")
    |> String.to_integer(),
  dry_run:
    System.get_env("DRY_RUN", "false")
    |> String.downcase()
    |> Kernel.==("true")

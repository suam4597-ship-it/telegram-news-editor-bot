import Config

config :feed_bot,
  anthropic_api_key: System.get_env("ANTHROPIC_API_KEY"),
  llm_model:
    System.get_env("LLM_MODEL") ||
      System.get_env("ANTHROPIC_MODEL") ||
      "claude-haiku-4-5-20251001",
  http_user_agent:
    System.get_env("HTTP_USER_AGENT") ||
      "FeedBot/0.1 contact@example.com",
  telegram_bot_token: System.get_env("TELEGRAM_BOT_TOKEN"),
  telegram_chat_id:
    System.get_env("TELEGRAM_CHAT_ID") ||
      System.get_env("TELEGRAM_CHANNEL_ID") ||
      System.get_env("TELEGRAM_PUBLIC_CHANNEL_ID"),
  poll_interval_ms:
    System.get_env("POLL_INTERVAL_MS", "300000")
    |> String.to_integer(),
  importance_threshold:
    (System.get_env("IMPORTANCE_THRESHOLD") ||
       System.get_env("MIN_IMPORTANCE") ||
       "7")
    |> String.to_integer(),
  dry_run:
    System.get_env("DRY_RUN", "false")
    |> String.downcase()
    |> Kernel.==("true")

import Config

config :feed_bot,
  start_pipeline: config_env() != :test

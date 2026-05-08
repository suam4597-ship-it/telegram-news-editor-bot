defmodule FeedBot.Application do
  @moduledoc false
  use Application

  @impl true
  def start(_type, _args) do
    children =
      if Application.get_env(:feed_bot, :start_pipeline, true) do
        [
          FeedBot.Dedup,
          FeedBot.StoryDedup,
          FeedBot.Telegram,
          FeedBot.Pipeline
        ]
      else
        []
      end

    opts = [strategy: :one_for_one, name: FeedBot.Supervisor]
    Supervisor.start_link(children, opts)
  end
end

defmodule FeedBot.Application do
  @moduledoc """
  FeedBot supervision tree 예시.

  기존 프로젝트에 Application 모듈이 이미 있다면 children만 병합하면 된다.
  """

  use Application

  @impl true
  def start(_type, _args) do
    children = pipeline_children()

    Supervisor.start_link(children, strategy: :one_for_one, name: FeedBot.Supervisor)
  end

  defp pipeline_children do
    if Application.get_env(:feed_bot, :start_pipeline, true) do
      [
        FeedBot.Dedup,
        {FeedBot.Sources.Producer, []},
        {FeedBot.TelegramConsumer, []}
      ]
    else
      []
    end
  end
end

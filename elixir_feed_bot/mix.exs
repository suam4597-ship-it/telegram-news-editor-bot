defmodule ElixirFeedBot.MixProject do
  use Mix.Project

  def project do
    [
      app: :feed_bot,
      version: "0.1.0",
      elixir: "~> 1.18",
      start_permanent: Mix.env() == :prod,
      deps: deps()
    ]
  end

  # Run "mix help compile.app" to learn about applications.
  def application do
    [
      extra_applications: [:logger],
      mod: {FeedBot.Application, []}
    ]
  end

  # Run "mix help deps" to learn about dependencies.
  defp deps do
    [
      {:gen_stage, "~> 1.2"},
      {:broadway, "~> 1.2"},
      {:floki, "~> 0.37"},
      {:jason, "~> 1.4"},
      {:req, "~> 0.5"}
    ]
  end
end

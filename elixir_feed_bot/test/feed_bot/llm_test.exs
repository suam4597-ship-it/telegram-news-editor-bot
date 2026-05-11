defmodule FeedBot.LLMTest do
  use ExUnit.Case, async: false

  alias FeedBot.LLM

  setup do
    original_provider = Application.get_env(:feed_bot, :llm_provider)
    original_openai_key = Application.get_env(:feed_bot, :openai_api_key)
    original_anthropic_key = Application.get_env(:feed_bot, :anthropic_api_key)

    on_exit(fn ->
      restore_env(:llm_provider, original_provider)
      restore_env(:openai_api_key, original_openai_key)
      restore_env(:anthropic_api_key, original_anthropic_key)
    end)

    :ok
  end

  test "auto provider prefers OpenAI when OPENAI_API_KEY is configured" do
    Application.put_env(:feed_bot, :llm_provider, "auto")
    Application.put_env(:feed_bot, :openai_api_key, "test-openai-key")
    Application.delete_env(:feed_bot, :anthropic_api_key)

    assert LLM.provider() == :openai
  end

  test "auto provider falls back to Anthropic when OpenAI key is absent" do
    Application.put_env(:feed_bot, :llm_provider, "auto")
    Application.delete_env(:feed_bot, :openai_api_key)
    Application.put_env(:feed_bot, :anthropic_api_key, "test-anthropic-key")

    assert LLM.provider() == :anthropic
  end

  test "explicit provider setting is honored" do
    Application.put_env(:feed_bot, :llm_provider, "anthropic")
    Application.put_env(:feed_bot, :openai_api_key, "test-openai-key")

    assert LLM.provider() == :anthropic
  end

  defp restore_env(key, nil), do: Application.delete_env(:feed_bot, key)
  defp restore_env(key, value), do: Application.put_env(:feed_bot, key, value)
end

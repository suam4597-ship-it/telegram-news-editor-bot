from __future__ import annotations

import json
from typing import Any

import httpx

from app.config import settings


class OpenAIUnavailable(RuntimeError):
    pass


class OpenAIResponseError(RuntimeError):
    pass


class OpenAIResponsesClient:
    endpoint = "https://api.openai.com/v1/responses"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key if api_key is not None else settings.openai_api_key
        self.model = model or settings.openai_model

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    async def structured_json(
        self,
        *,
        schema_name: str,
        schema: dict[str, Any],
        prompt: str,
        instructions: str | None = None,
        strict: bool = True,
    ) -> dict[str, Any]:
        if not self.api_key:
            raise OpenAIUnavailable("OPENAI_API_KEY is not configured")
        payload: dict[str, Any] = {
            "model": self.model,
            "input": prompt,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "schema": schema,
                    "strict": strict,
                }
            },
            "store": False,
        }
        if instructions:
            payload["instructions"] = instructions

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                self.endpoint,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
            )
        if response.status_code >= 400:
            raise OpenAIResponseError(f"OpenAI API error {response.status_code}: {response.text[:500]}")
        text = extract_output_text(response.json())
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise OpenAIResponseError(f"OpenAI returned non-JSON text: {text[:500]}") from exc


def extract_output_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    chunks: list[str] = []
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    if not chunks:
        raise OpenAIResponseError("OpenAI response did not contain output_text")
    return "".join(chunks)


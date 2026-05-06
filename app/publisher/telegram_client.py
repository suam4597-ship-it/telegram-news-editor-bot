from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from app.config import settings
from app.publisher.formatter import truncate_telegram_text


class TelegramError(RuntimeError):
    pass


class TelegramClient:
    _send_lock = asyncio.Lock()
    _last_send_at_by_chat: dict[str, float] = {}

    def __init__(self, token: str | None = None):
        self.token = token if token is not None else settings.telegram_bot_token

    @property
    def available(self) -> bool:
        return bool(self.token)

    @property
    def base_url(self) -> str:
        if not self.token:
            raise TelegramError("TELEGRAM_BOT_TOKEN is not configured")
        return f"https://api.telegram.org/bot{self.token}"

    async def send_message(
        self,
        *,
        chat_id: str,
        text: str,
        reply_markup: dict[str, Any] | None = None,
        disable_web_page_preview: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": truncate_telegram_text(text),
            "parse_mode": "HTML",
            "disable_web_page_preview": disable_web_page_preview,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        await self._throttle_chat(chat_id)
        return await self._post("sendMessage", payload)

    async def edit_message_text(
        self,
        *,
        chat_id: str,
        message_id: int | str,
        text: str,
        reply_markup: dict[str, Any] | None = None,
        disable_web_page_preview: bool = True,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": truncate_telegram_text(text),
            "parse_mode": "HTML",
            "disable_web_page_preview": disable_web_page_preview,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        await self._throttle_chat(chat_id)
        return await self._post("editMessageText", payload)

    async def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text[:200]
        return await self._post("answerCallbackQuery", payload)

    async def edit_message_reply_markup(
        self,
        *,
        chat_id: str,
        message_id: int | str,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"chat_id": chat_id, "message_id": message_id}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        return await self._post("editMessageReplyMarkup", payload)

    async def _post(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/{method}"
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(url, json=payload)
            if response.status_code == 429:
                retry_after = response.json().get("parameters", {}).get("retry_after", 1)
                await asyncio.sleep(min(float(retry_after), 30.0))
                response = await client.post(url, json=payload)
        if response.status_code >= 400:
            raise TelegramError(f"Telegram {method} failed {response.status_code}: {response.text[:500]}")
        payload = response.json()
        if not payload.get("ok", False):
            raise TelegramError(f"Telegram {method} returned ok=false: {payload}")
        return payload

    async def _throttle_chat(self, chat_id: str) -> None:
        async with self._send_lock:
            now = time.monotonic()
            last_send_at = self._last_send_at_by_chat.get(str(chat_id), 0.0)
            wait_seconds = 1.0 - (now - last_send_at)
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)
            self._last_send_at_by_chat[str(chat_id)] = time.monotonic()

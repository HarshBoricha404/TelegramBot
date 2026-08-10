from __future__ import annotations

from typing import Any

import httpx


class TelegramError(RuntimeError):
    """Raised when the Telegram Bot API request fails."""


def _api_call(
    bot_token: str,
    method: str,
    *,
    payload: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> dict:
    url = f"https://api.telegram.org/bot{bot_token}/{method}"
    try:
        if payload is not None:
            response = httpx.post(url, json=payload, timeout=timeout)
        else:
            response = httpx.get(url, params=params, timeout=timeout)
        data = response.json()
    except httpx.HTTPError as exc:
        raise TelegramError(f"Telegram request failed: {exc}") from exc
    except ValueError as exc:
        raise TelegramError(f"Telegram returned invalid JSON: {exc}") from exc

    if not data.get("ok"):
        description = data.get("description", "unknown error")
        raise TelegramError(f"Telegram API error: {description}")

    return data


def get_me(bot_token: str, timeout: float = 30.0) -> dict:
    """Verify the bot token and return bot profile info."""
    return _api_call(bot_token, "getMe", timeout=timeout)["result"]


def get_updates(
    bot_token: str,
    *,
    offset: int | None = None,
    timeout: int = 25,
) -> list[dict]:
    """Long-poll for incoming messages."""
    params: dict[str, Any] = {"timeout": timeout}
    if offset is not None:
        params["offset"] = offset
    # HTTP timeout must exceed Telegram long-poll timeout
    data = _api_call(bot_token, "getUpdates", params=params, timeout=float(timeout + 10))
    return data.get("result", [])


def send_message(
    bot_token: str,
    chat_id: str,
    text: str,
    timeout: float = 30.0,
) -> dict:
    """Post a plain-text message to a Telegram chat or channel."""
    return _api_call(
        bot_token,
        "sendMessage",
        payload={
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        },
        timeout=timeout,
    )

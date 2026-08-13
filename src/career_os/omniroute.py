"""Optional OmniRoute OpenAI-compatible gateway integration.

OmniRoute is deliberately an optional layer. When OMNIROUTE_BASE_URL and
OMNIROUTE_API_KEY are configured, Career OS tries OmniRoute first and then
falls back to the existing provider stack. If OmniRoute is not configured,
Career OS behaves exactly as before.

Important: a local OmniRoute URL (for example http://localhost:20128/v1) is
reachable only from the same machine. GitHub Actions needs a reachable,
secured OmniRoute endpoint if it is to use this integration.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from typing import Any

import httpx


ChatFn = Callable[..., Awaitable[str]]


class OmniRouteClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("OMNIROUTE_BASE_URL", "").strip().rstrip("/")
        self.api_key = os.getenv("OMNIROUTE_API_KEY", "").strip()
        self.model = os.getenv("OMNIROUTE_MODEL", "auto").strip() or "auto"
        self.timeout = float(os.getenv("OMNIROUTE_TIMEOUT_SECONDS", "120"))

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.api_key)

    def _endpoint(self) -> str:
        base = self.base_url
        if not base.endswith("/v1"):
            base += "/v1"
        return f"{base}/chat/completions"

    async def chat(
        self,
        system: str,
        user: str,
        *,
        json_mode: bool = False,
        max_tokens: int = 4000,
    ) -> str:
        if not self.enabled:
            raise RuntimeError(
                "OmniRoute is not configured. Set OMNIROUTE_BASE_URL and "
                "OMNIROUTE_API_KEY to enable it."
            )

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.1,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self._endpoint(), headers=headers, json=payload
            )

            # Some OpenAI-compatible upstreams do not implement response_format.
            # Retry once without it rather than failing a JSON-producing agent.
            if response.status_code == 400 and json_mode:
                retry_payload = dict(payload)
                retry_payload.pop("response_format", None)
                response = await client.post(
                    self._endpoint(), headers=headers, json=retry_payload
                )

            response.raise_for_status()
            data = response.json()

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                f"OmniRoute returned an unexpected response: {data}"
            ) from exc

        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("OmniRoute returned an empty model response")
        return content.strip()


def install_omniroute_fallback(runtime: Any) -> bool:
    """Wrap AgentRuntime._chat with OmniRoute-first fallback behavior.

    Returns True when the wrapper is active. The original _chat method is
    retained and called whenever OmniRoute is unavailable or fails.
    """

    client = OmniRouteClient()
    if not client.enabled:
        return False

    original_chat: ChatFn = runtime._chat

    async def routed_chat(
        system: str,
        user: str,
        *,
        json_mode: bool = False,
        max_tokens: int = 4000,
    ) -> str:
        try:
            result = await client.chat(
                system,
                user,
                json_mode=json_mode,
                max_tokens=max_tokens,
            )
            runtime.last_provider_used = f"omniroute:{client.model}"
            return result
        except Exception as exc:
            try:
                fallback = await original_chat(
                    system,
                    user,
                    json_mode=json_mode,
                    max_tokens=max_tokens,
                )
                runtime.last_provider_used = (
                    f"fallback-after-omniroute:{runtime.last_provider_used or 'unknown'}"
                )
                return fallback
            except Exception as fallback_exc:
                raise RuntimeError(
                    "OmniRoute failed and the configured Career OS fallback also failed. "
                    f"OmniRoute: {exc} | Fallback: {fallback_exc}"
                ) from fallback_exc

    runtime._chat = routed_chat
    runtime.omniroute = client
    return True

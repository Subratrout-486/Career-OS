"""Client adapter for a Career OS local model gateway.

The harness sees the same ModelExecutor seam whether the model is on the same
machine or on an owner-controlled worker host. No provider fallback is allowed.
"""
from __future__ import annotations

import httpx


class LocalGatewayUnavailable(RuntimeError):
    """Raised when the owner-controlled local model gateway cannot execute."""


class RemoteLocalModelExecutor:
    def __init__(self, *, base_url: str, token: str, model: str = "qwen2.5:7b", timeout: float = 180.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.model = model
        self.timeout = timeout

    async def generate(self, *, system: str, user: str, json_mode: bool = False, max_tokens: int = 4000) -> str:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/generate",
                    headers={"Authorization": f"Bearer {self.token}"},
                    json={
                        "system": system,
                        "user": user,
                        "json_mode": json_mode,
                        "max_tokens": max_tokens,
                    },
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise LocalGatewayUnavailable(f"local model gateway unavailable: {type(exc).__name__}") from exc
        text = data.get("text")
        if not isinstance(text, str) or not text.strip():
            raise LocalGatewayUnavailable("local model gateway returned no usable text")
        if data.get("fallback") is not False:
            raise LocalGatewayUnavailable("local gateway did not attest strict no-fallback execution")
        return text


__all__ = ["RemoteLocalModelExecutor", "LocalGatewayUnavailable"]

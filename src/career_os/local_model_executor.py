"""Local model adapter for the Career OS harness.

This follows the DeepSeek Harness LLM seam: the harness owns agent/session/tool
lifecycle while this adapter owns only model transport. Ollama is a local,
non-paid execution option; no cloud API key is required.
"""
from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class LocalModelUnavailable(RuntimeError):
    """Raised when the configured local model server cannot execute."""


class OllamaModelExecutor:
    """Execute model requests against a local Ollama HTTP server."""

    def __init__(self, *, model: str = "qwen2.5:7b", base_url: str = "http://127.0.0.1:11434") -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")

    async def generate(self, *, system: str, user: str, json_mode: bool = False, max_tokens: int = 4000) -> str:
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "options": {"num_predict": max_tokens},
        }
        if json_mode:
            payload["format"] = "json"
        request = Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=180) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise LocalModelUnavailable(
                f"Local Ollama model '{self.model}' is unavailable at {self.base_url}: {exc}"
            ) from exc
        message = body.get("message") or {}
        text = message.get("content")
        if not isinstance(text, str) or not text.strip():
            raise LocalModelUnavailable("Local model returned no usable message content")
        return text


__all__ = ["OllamaModelExecutor", "LocalModelUnavailable"]

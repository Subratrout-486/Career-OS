"""Optional OmniRoute runtime adapter.

OmniRoute exposes an OpenAI-compatible /v1/chat/completions endpoint. This
adapter keeps the existing AgentRuntime implementation intact and swaps only
the primary chat transport when AI_PROVIDER=omniroute.

For GitHub Actions, OMNIROUTE_BASE_URL must be reachable from the runner.
A localhost OmniRoute instance on the user's PC cannot be reached by a hosted
GitHub runner.
"""

from __future__ import annotations

import os

import httpx

from .agents import AgentRuntime


class OmniRouteAgentRuntime(AgentRuntime):
    """AgentRuntime using a remote/local OmniRoute OpenAI-compatible gateway."""

    def __init__(self):
        # Keep all existing provider configuration and validation.
        super().__init__()
        self.omniroute_key = os.getenv("OMNIROUTE_API_KEY")
        self.omniroute_model = os.getenv("OMNIROUTE_MODEL", "auto")
        self.omniroute_base_url = os.getenv(
            "OMNIROUTE_BASE_URL", "http://127.0.0.1:20128/v1"
        ).rstrip("/")

        if self.provider == "omniroute" and not self.omniroute_key:
            raise RuntimeError("OMNIROUTE_API_KEY is required when AI_PROVIDER=omniroute")

    async def _chat(self, system, user, *, json_mode=False, max_tokens=4000):
        """Use OmniRoute as the primary OpenAI-compatible chat transport."""
        if self.provider != "omniroute":
            return await super()._chat(
                system, user, json_mode=json_mode, max_tokens=max_tokens
            )

        payload = {
            "model": self.omniroute_model,
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
            "Authorization": f"Bearer {self.omniroute_key}",
            "Content-Type": "application/json",
        }
        endpoint = f"{self.omniroute_base_url}/chat/completions"

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        try:
            self.last_provider_used = f"omniroute:{self.omniroute_model}"
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                f"OmniRoute returned an unexpected response: {data}"
            ) from exc

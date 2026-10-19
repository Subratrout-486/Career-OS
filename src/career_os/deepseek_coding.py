"""DeepSeek-backed coding proposer for the isolated Career OS repair agent.

This is deliberately a thin provider adapter: it asks DeepSeek for a unified
patch and leaves all filesystem mutation, test execution, rollback, and approval
logic to :class:`career_os.coding_agent.CodingRepairAgent`.

Credentials are read only from ``DEEPSEEK_API_KEY``. No credential is persisted
or included in prompts, logs, patches, or source control.
"""

from __future__ import annotations

import os
import re
from typing import Any

import httpx

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-pro"


class DeepSeekCodingError(RuntimeError):
    """Raised when the DeepSeek coding provider cannot produce a patch."""


def _extract_patch(content: str) -> str:
    """Extract a unified diff from model output without executing it."""
    text = content.strip()
    fenced = re.search(r"```(?:diff|patch)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()

    start = text.find("diff --git ")
    if start >= 0:
        text = text[start:]
    else:
        # Accept a standard unified diff that starts with ---/+++ when the
        # provider omits git's extended header.
        marker = text.find("--- ")
        if marker >= 0 and "+++ " in text[marker:]:
            text = text[marker:]

    if not text.startswith(("diff --git ", "--- ")):
        raise DeepSeekCodingError("DeepSeek response did not contain a unified diff")
    return text.rstrip() + "\n"


class DeepSeekCodingProposer:
    """OpenAI-compatible DeepSeek adapter for ``CodingRepairAgent``."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float = 120.0,
    ) -> None:
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.model = model or os.getenv("DEEPSEEK_CODING_MODEL", DEFAULT_MODEL)
        self.base_url = (base_url or os.getenv("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
        self.timeout = httpx.Timeout(timeout_seconds)
        if not self.api_key:
            raise DeepSeekCodingError("DEEPSEEK_API_KEY is not configured")

    def propose_patch(self, prompt: str, failure: str) -> str:
        """Return only a validated unified diff; never execute model output."""
        system = (
            "You are a repository coding-repair proposer for Career OS. "
            "Return ONLY a unified git diff. Never return shell commands, "
            "secrets, deployment changes, credentials, or prose. Make the "
            "smallest safe change required by the supplied failure. Do not "
            "modify tests merely to hide a failure."
        )
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"{prompt}\n\nLATEST FAILURE:\n{failure}"},
            ],
            "stream": False,
            "thinking": {"type": "enabled"},
            "reasoning_effort": "high",
            "max_tokens": 16000,
        }

        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise DeepSeekCodingError("DeepSeek returned a non-text response")
            return _extract_patch(content)
        except httpx.HTTPError as exc:
            raise DeepSeekCodingError(f"DeepSeek request failed: {exc}") from exc
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise DeepSeekCodingError("DeepSeek returned an unexpected response shape") from exc

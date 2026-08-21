"""Strict direct-provider runtime for Career OS.

Unlike the legacy resilient provider stack, this adapter never cascades from
one provider to another. The configured provider is the only primary model
allowed to execute fit/resume generation. Independent challenger logic remains
owned by AgentRuntime and is allowed to report unavailable rather than
silently switching the primary provider.
"""
from __future__ import annotations

from .agents import AgentRuntime


class DirectProviderRuntime(AgentRuntime):
    """Fail-closed primary runtime pinned to exactly one provider."""

    SUPPORTED = {"manus", "gemini", "xai", "deepseek", "anthropic"}

    def __init__(self) -> None:
        super().__init__()
        if self.provider not in self.SUPPORTED:
            raise RuntimeError(
                "DirectProviderRuntime requires AI_PROVIDER to be pinned to one of: "
                "manus, gemini, xai, deepseek, anthropic"
            )

    def _excluded(self, extra=None):
        return set(extra or set()) | (self.SUPPORTED - {self.provider}) | {"github"}

    async def _chat(self, system, user, *, json_mode=False, max_tokens=4000, exclude_providers=None):
        return await super()._chat(
            system,
            user,
            json_mode=json_mode,
            max_tokens=max_tokens,
            exclude_providers=self._excluded(exclude_providers),
        )

    async def _chat_prefer(self, preferred, system, user, *, json_mode=False, max_tokens=4000, exclude_providers=None):
        # Ignore specialty-provider preference for the primary pipeline. The
        # owner-selected provider is the only primary execution path.
        return await self._chat(
            system,
            user,
            json_mode=json_mode,
            max_tokens=max_tokens,
            exclude_providers=exclude_providers,
        )

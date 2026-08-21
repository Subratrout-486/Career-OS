"""Self-sufficient direct-provider runtime for Career OS.

Conductor is deliberately not required for this runtime. A stage has a
specialist role and a bounded provider chain. The first healthy configured
provider handles the request; a provider failure is recorded and the same
request is retried with the next configured provider.

The engineering role can use the optional OpenHands coding agent. OpenHands
is isolated to repository/code tasks and is never required by the normal job
processing path.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

from .agents import AgentRuntime
from .department_agents import provider_order


class DirectProviderRuntime(AgentRuntime):
    """Direct runtime with role-aware, bounded provider fallback."""

    SUPPORTED = {"manus", "gemini", "xai", "deepseek", "anthropic", "github", "pool"}

    def __init__(self) -> None:
        requested = os.getenv("AI_PROVIDER", "pool").lower()
        if requested == "auto":
            raise RuntimeError("DirectProviderRuntime rejects AI_PROVIDER=auto; use pool for bounded fallback")
        if requested not in self.SUPPORTED:
            raise RuntimeError(
                "AI_PROVIDER must be one of: pool, manus, gemini, xai, deepseek, anthropic, github"
            )

        self.requested_provider = requested
        self._role = "fit"
        self.provider_failures: list[dict[str, Any]] = []
        self.provider_attempts: list[str] = []

        if requested == "pool":
            candidates = provider_order("fit")
            if not candidates:
                raise RuntimeError("No configured AI provider is available for the self-sufficient agent pool")
            original = os.environ.get("AI_PROVIDER")
            os.environ["AI_PROVIDER"] = candidates[0]
            try:
                super().__init__()
            finally:
                if original is None:
                    os.environ.pop("AI_PROVIDER", None)
                else:
                    os.environ["AI_PROVIDER"] = original
            self.provider = "pool"
        else:
            super().__init__()

    def _excluded(self, extra=None):
        return set(extra or set()) | {"github"}

    def _ordered_providers(self) -> tuple[str, ...]:
        if self.requested_provider == "pool":
            return provider_order(self._role)
        role_order = provider_order(self._role)
        return (self.requested_provider,) + tuple(p for p in role_order if p != self.requested_provider)

    def _child(self, provider: str) -> AgentRuntime:
        cache = getattr(self, "_children", None)
        if cache is None:
            cache = {}
            self._children = cache
        if provider in cache:
            return cache[provider]

        original = os.environ.get("AI_PROVIDER")
        os.environ["AI_PROVIDER"] = provider
        try:
            child = AgentRuntime()
        finally:
            if original is None:
                os.environ.pop("AI_PROVIDER", None)
            else:
                os.environ["AI_PROVIDER"] = original
        cache[provider] = child
        return child

    async def _chat(self, system, user, *, json_mode=False, max_tokens=4000, exclude_providers=None):
        """Run the specialist pool and never let legacy exclusions empty it."""
        if self.requested_provider == "pool":
            excluded = {"github"}
        else:
            excluded = set(exclude_providers or set()) | {"github"}

        errors: list[str] = []
        for provider in self._ordered_providers():
            if provider in excluded or provider == "openhands":
                continue
            self.provider_attempts.append(provider)
            try:
                child = self._child(provider)
                result = await child._chat(
                    system,
                    user,
                    json_mode=json_mode,
                    max_tokens=max_tokens,
                    exclude_providers=set(),
                )
                self.last_provider_used = child.last_provider_used
                return result
            except Exception as exc:
                self.provider_failures.append({
                    "provider": provider,
                    "error_type": type(exc).__name__,
                })
                errors.append(f"{provider}:{type(exc).__name__}")
                continue

        diagnostics = {
            "requested_provider": self.requested_provider,
            "role": self._role,
            "provider_order": list(self._ordered_providers()),
            "attempts": list(self.provider_attempts),
            "failures": list(self.provider_failures),
        }
        raise RuntimeError(
            "All configured AI providers failed for the current specialist agent. "
            + " | ".join(errors)
            + f" | diagnostics={diagnostics}"
        )

    async def _chat_prefer(self, preferred, system, user, *, json_mode=False, max_tokens=4000, exclude_providers=None):
        return await self._chat(
            system,
            user,
            json_mode=json_mode,
            max_tokens=max_tokens,
            exclude_providers=exclude_providers,
        )

    async def fit(self, *args, **kwargs):
        self._role = "fit"
        return await super().fit(*args, **kwargs)

    async def resume(self, *args, **kwargs):
        self._role = "resume"
        return await super().resume(*args, **kwargs)

    async def challenge(self, *args, **kwargs):
        self._role = "challenge"
        return await super().challenge(*args, **kwargs)

    async def engineering(self, task: str, workspace: str) -> dict[str, Any]:
        """Run a repository repair task through OpenHands when enabled.

        OpenHands is intentionally a separate execution mechanism because it
        edits files and runs shell commands, unlike the text-only provider
        pool. The normal job pipeline never calls this method.
        """
        self._role = "engineering"
        ordered = provider_order("engineering")
        if "openhands" in ordered:
            from .openhands_coding_agent import run_coding_task

            self.provider_attempts.append("openhands")
            try:
                result = await asyncio.to_thread(run_coding_task, task, workspace)
                self.last_provider_used = f"openhands:{result['model']}"
                return result
            except Exception as exc:
                self.provider_failures.append({
                    "provider": "openhands",
                    "error_type": type(exc).__name__,
                })

        fallback = tuple(p for p in ordered if p != "openhands")
        if not fallback:
            raise RuntimeError(
                "No OpenHands coding agent is configured and no fallback AI provider is available for engineering"
            )

        result = await self._chat(
            "You are the Career OS engineering repair planner. Do not claim that you edited files. "
            "Return a precise repair plan with commands/tests for the following repository task.",
            task,
            max_tokens=4000,
            exclude_providers={"openhands"},
        )
        self.last_provider_used = self.last_provider_used or "provider-pool-plan-only"
        return {
            "status": "plan_only",
            "agent": "provider-pool",
            "provider": self.last_provider_used,
            "plan": result,
            "workspace": workspace,
        }

    def diagnostics(self) -> dict[str, object]:
        return {
            "runtime": "department-agent-pool-v2",
            "requested_provider": self.requested_provider,
            "active_role": self._role,
            "provider_order": list(self._ordered_providers()),
            "provider_attempts": list(self.provider_attempts),
            "provider_failures": list(self.provider_failures),
            "last_provider_used": self.last_provider_used,
        }

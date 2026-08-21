from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_pool_ignores_legacy_exclusions_for_configured_specialist(monkeypatch):
    """Regression for the failed E2E where DeepSeek was excluded from fit/resume."""
    monkeypatch.setenv("AI_PROVIDER", "pool")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy")

    from career_os.direct_provider_runtime import DirectProviderRuntime

    runtime = DirectProviderRuntime()

    class Healthy:
        last_provider_used = "deepseek:deepseek-chat"

        async def _chat(self, *args, **kwargs):
            return "deepseek-response"

    monkeypatch.setattr(runtime, "_child", lambda provider: Healthy())

    result = await runtime._chat(
        "system",
        "user",
        exclude_providers={"deepseek", "gemini"},
    )

    assert result == "deepseek-response"
    assert runtime.provider_attempts == ["deepseek"]
    assert runtime.last_provider_used == "deepseek:deepseek-chat"


@pytest.mark.asyncio
async def test_pool_records_provider_failure_and_falls_forward(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "pool")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy")
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")

    from career_os.direct_provider_runtime import DirectProviderRuntime

    runtime = DirectProviderRuntime()

    class Broken:
        last_provider_used = None

        async def _chat(self, *args, **kwargs):
            raise RuntimeError("simulated outage")

    class Healthy:
        last_provider_used = "gemini:gemini-3.1-flash-lite"

        async def _chat(self, *args, **kwargs):
            return "healthy-response"

    children = {"deepseek": Broken(), "gemini": Healthy()}
    monkeypatch.setattr(runtime, "_child", lambda provider: children[provider])

    result = await runtime._chat("system", "user")

    assert result == "healthy-response"
    assert runtime.provider_attempts[:2] == ["deepseek", "gemini"]
    assert runtime.provider_failures[0]["provider"] == "deepseek"

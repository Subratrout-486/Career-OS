from __future__ import annotations

import pytest


def test_direct_provider_runtime_rejects_auto(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "auto")
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    from career_os.direct_provider_runtime import DirectProviderRuntime

    try:
        DirectProviderRuntime()
    except RuntimeError as exc:
        assert "rejects AI_PROVIDER=auto" in str(exc)
    else:
        raise AssertionError("DirectProviderRuntime must reject unbounded auto selection")


def test_direct_provider_runtime_pool_uses_configured_specialist_order(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "pool")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy")
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")
    from career_os.direct_provider_runtime import DirectProviderRuntime

    runtime = DirectProviderRuntime()
    assert runtime.requested_provider == "pool"
    assert runtime._ordered_providers()[:3] == ("deepseek", "gemini", "anthropic")


def test_direct_provider_runtime_pinned_provider_remains_primary(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy")
    from career_os.direct_provider_runtime import DirectProviderRuntime

    runtime = DirectProviderRuntime()
    assert runtime._ordered_providers()[0] == "gemini"
    assert "deepseek" in runtime._ordered_providers()
    assert "github" not in runtime._ordered_providers()


@pytest.mark.asyncio
async def test_direct_provider_runtime_falls_forward_after_provider_error(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "pool")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy")
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    from career_os.direct_provider_runtime import DirectProviderRuntime

    runtime = DirectProviderRuntime()

    class Broken:
        last_provider_used = None
        async def _chat(self, *args, **kwargs):
            raise RuntimeError("simulated DeepSeek outage")

    class Healthy:
        last_provider_used = "gemini:gemini-3.1-flash-lite"
        async def _chat(self, *args, **kwargs):
            return "healthy-response"

    children = {"deepseek": Broken(), "gemini": Healthy()}
    monkeypatch.setattr(runtime, "_child", lambda provider: children[provider])
    result = await runtime._chat("system", "user")
    assert result == "healthy-response"
    assert runtime.last_provider_used == "gemini:gemini-3.1-flash-lite"
    assert runtime.provider_attempts[:2] == ["deepseek", "gemini"]

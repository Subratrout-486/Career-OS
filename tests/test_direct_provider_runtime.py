from __future__ import annotations


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

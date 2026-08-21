from __future__ import annotations


def test_direct_provider_runtime_rejects_auto(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "auto")
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    from career_os.direct_provider_runtime import DirectProviderRuntime

    try:
        DirectProviderRuntime()
    except RuntimeError as exc:
        assert "AI_PROVIDER to be pinned" in str(exc)
    else:
        raise AssertionError("DirectProviderRuntime must reject auto provider selection")


def test_direct_provider_runtime_excludes_every_other_primary_provider(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    from career_os.direct_provider_runtime import DirectProviderRuntime

    runtime = DirectProviderRuntime()
    excluded = runtime._excluded()
    assert "gemini" not in excluded
    assert "manus" in excluded
    assert "xai" in excluded
    assert "deepseek" in excluded
    assert "anthropic" in excluded
    assert "github" in excluded

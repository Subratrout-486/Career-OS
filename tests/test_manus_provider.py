from __future__ import annotations

import pytest

from career_os.agents import AgentRuntime


@pytest.mark.asyncio
async def test_auto_uses_manus_when_external_providers_are_missing(monkeypatch):
    for name in (
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "DEEPSEEK_API_KEY",
        "XAI_API_KEY",
        "GITHUB_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AI_PROVIDER", "auto")
    monkeypatch.setenv("OPENAI_API_KEY", "manus-test-key")
    monkeypatch.setenv("OPENAI_API_BASE", "https://manus.test/v1")
    monkeypatch.setenv("MANUS_MODEL", "gpt-5-mini")

    runtime = AgentRuntime()
    calls = []

    async def fake_manus(system, user, *, json_mode, max_tokens):
        calls.append((system, user, json_mode, max_tokens))
        runtime.last_provider_used = "manus:gpt-5-mini"
        return '{"ok": true}'

    runtime._chat_manus = fake_manus
    result = await runtime._chat("system", "user", json_mode=True, max_tokens=123)

    assert result == '{"ok": true}'
    assert runtime.last_provider_used == "manus:gpt-5-mini"
    assert calls == [("system", "user", True, 123)]


def test_pinned_manus_requires_managed_endpoint(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "manus")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY and OPENAI_API_BASE"):
        AgentRuntime()

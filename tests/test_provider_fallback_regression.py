import pytest

from career_os.agents import AgentRuntime
from career_os.specialist_routing import _specialist_fit, _specialist_resume_draft
from career_os.models import FitReport


@pytest.mark.asyncio
async def test_fit_deepseek_failure_falls_back_to_gemini(monkeypatch):
    runtime = object.__new__(AgentRuntime)
    runtime.provider = "auto"
    runtime.manus_key = None
    runtime.manus_endpoint = None
    runtime.github_token = None
    runtime.gemini_key = "configured"
    runtime.deepseek_key = "configured"
    runtime.xai_key = None
    runtime.last_provider_used = None
    runtime.gemini_model = "gemini-test"
    runtime.gemini_diagnostic = {}

    async def fail_deepseek(*args, **kwargs):
        raise RuntimeError("402 Payment Required")

    async def gemini_success(*args, **kwargs):
        runtime.last_provider_used = "gemini:gemini-test"
        return '{"fit_score": 82, "recommendation": "APPLY", "band": "A", "must_have_matches": [], "gaps": [], "blockers": [], "evidence": [], "keywords": [], "risks": [], "rationale": "fallback", "requirement_matches": [], "confirmation_requests": []}'

    monkeypatch.setattr(runtime, "_chat_deepseek", fail_deepseek)
    monkeypatch.setattr(runtime, "_chat_gemini", gemini_success)

    result = await _specialist_fit(runtime, "profile", object(), [], {})

    assert result.fit_score == 82
    assert runtime.last_provider_used == "gemini:gemini-test"


@pytest.mark.asyncio
async def test_resume_xai_and_deepseek_failure_falls_back_to_gemini(monkeypatch):
    runtime = object.__new__(AgentRuntime)
    runtime.provider = "auto"
    runtime.manus_key = None
    runtime.manus_endpoint = None
    runtime.github_token = None
    runtime.gemini_key = "configured"
    runtime.deepseek_key = "configured"
    runtime.xai_key = "configured"
    runtime.last_provider_used = None
    runtime.gemini_model = "gemini-test"
    runtime.gemini_diagnostic = {}

    async def fail_xai(*args, **kwargs):
        raise RuntimeError("403 Forbidden")

    async def fail_deepseek(*args, **kwargs):
        raise RuntimeError("402 Payment Required")

    async def gemini_success(*args, **kwargs):
        runtime.last_provider_used = "gemini:gemini-test"
        return '{"title":"Business Analyst","summary":"Fallback","skills":["Excel"],"experience":[],"education":[],"changes":[],"unsupported_claims":[],"evidence_trace":[]}'

    monkeypatch.setattr(runtime, "_chat_xai", fail_xai)
    monkeypatch.setattr(runtime, "_chat_deepseek", fail_deepseek)
    monkeypatch.setattr(runtime, "_chat_gemini", gemini_success)

    fit = FitReport(fit_score=80, recommendation="APPLY", band="A")
    result = await _specialist_resume_draft(runtime, "profile", object(), fit, [], {})

    assert result.title == "Business Analyst"
    assert runtime.last_provider_used == "gemini:gemini-test"

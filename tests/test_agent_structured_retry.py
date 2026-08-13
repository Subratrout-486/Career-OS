"""AgentRuntime structured-output retry path."""

from __future__ import annotations

import json

import pytest

from career_os.agents import AgentRuntime
from career_os.models import FitReport, TailoredResume


@pytest.fixture
def runtime(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-used")
    return AgentRuntime()


@pytest.mark.asyncio
async def test_structured_call_succeeds_on_second_attempt(runtime):
    good = {
        "fit_score": 70,
        "recommendation": "APPLY",
        "band": "B",
        "must_have_matches": [],
        "gaps": [],
        "blockers": [],
        "evidence": [],
        "keywords": [],
        "risks": [],
        "rationale": "ok",
        "requirement_matches": [],
        "confirmation_requests": [],
    }
    calls = {"n": 0}

    async def chat_fn2(system, user, *, json_mode, max_tokens):
        calls["n"] += 1
        if calls["n"] == 1:
            return "NOT JSON AT ALL"
        return json.dumps(good)

    result = await runtime._structured_call(
        chat_fn=chat_fn2,
        system="sys",
        user="user",
        model_cls=FitReport,
        max_attempts=2,
    )
    assert isinstance(result, FitReport)
    assert result.fit_score == 70
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_clean_json_ignores_trailing_object(runtime):
    first = {
        "title": "PSE",
        "summary": "s",
        "skills": [],
        "experience": [],
        "education": [],
        "changes": [],
        "unsupported_claims": [],
        "evidence_trace": [],
    }
    raw = json.dumps(first) + "\n" + json.dumps({"noise": 1})
    cleaned = runtime._clean_json(raw)
    assert json.loads(cleaned)["title"] == "PSE"
    TailoredResume.model_validate_json(cleaned)

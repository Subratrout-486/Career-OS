"""Independent challenger must use DeepSeek or xAI only, never a primary provider."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from career_os.agents import AgentRuntime  # noqa: E402
from career_os.models import FitReport, Job, TailoredResume  # noqa: E402


def _minimal_job() -> Job:
    return Job(
        title="Product Support Engineer",
        company="HighRadius",
        location="Hyderabad, India",
        url="https://example.com/job",
        source="test",
        description="Support SaaS products. SQL preferred.",
    )


def _minimal_fit() -> FitReport:
    return FitReport(
        fit_score=80,
        recommendation="APPLY",
        band="B",
        rationale="Test",
        must_have_matches=["application support"],
        gaps=[],
        blockers=[],
        risks=[],
        confirmation_requests=[],
    )


def _minimal_resume() -> TailoredResume:
    return TailoredResume(
        title="Product Support Engineer",
        summary="Test",
        skills=["SQL"],
        experience=[],
        changes=[],
        unsupported_claims=[],
        evidence_trace=[],
    )


@pytest.mark.asyncio
async def test_challenger_reports_missing_independent_provider_keys(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.setenv("AI_PROVIDER", "auto")
    # Ensure primary providers exist so AgentRuntime can construct
    monkeypatch.setenv("GITHUB_TOKEN", "dummy")
    runtime = AgentRuntime()
    assert not runtime.xai_key
    notes = await runtime.challenge(
        profile="profile",
        job=_minimal_job(),
        fit=_minimal_fit(),
        resume=_minimal_resume(),
        evidence_pack=[],
    )
    assert "INDEPENDENT CHALLENGER NOT RUN" in notes
    assert "deepseek is not configured" in notes
    assert "xai is not configured" in notes
    assert "must not be treated as recruiter approval" in notes


@pytest.mark.asyncio
async def test_challenger_does_not_fallback_on_xai_403(monkeypatch):
    """Even when Gemini/GitHub are available, challenger must not switch providers."""
    monkeypatch.setenv("XAI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-dummy")
    monkeypatch.setenv("GITHUB_TOKEN", "github-dummy")
    monkeypatch.setenv("AI_PROVIDER", "auto")
    runtime = AgentRuntime()

    async def boom(*_a, **_k):
        raise RuntimeError(
            "xAI 403: API key or team lacks permission for model 'grok-4.6' "
            "or the chat completions endpoint."
        )

    with patch.object(runtime, "_chat_xai", new=AsyncMock(side_effect=boom)):
        with patch.object(runtime, "_chat_gemini", new=AsyncMock()) as gem:
            with patch.object(runtime, "_chat_github", new=AsyncMock()) as gh:
                notes = await runtime.challenge(
                    profile="profile",
                    job=_minimal_job(),
                    fit=_minimal_fit(),
                    resume=_minimal_resume(),
                    evidence_pack=[],
                )
    assert "INDEPENDENT CHALLENGER NOT RUN" in notes
    assert "403" in notes or "permission" in notes.lower()
    assert "must not be treated as recruiter approval" in notes
    gem.assert_not_called()
    gh.assert_not_called()


def test_xai_default_model_is_current_flagship(monkeypatch):
    monkeypatch.delenv("XAI_MODEL", raising=False)
    monkeypatch.delenv("GROK_MODEL", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "dummy")
    monkeypatch.setenv("AI_PROVIDER", "auto")
    runtime = AgentRuntime()
    assert runtime.xai_model == "grok-4.6"
    assert runtime.xai_endpoint == "https://api.x.ai/v1/chat/completions"

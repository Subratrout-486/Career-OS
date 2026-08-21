"""Mandatory adversarial challenger must use independent Gemini only."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from career_os.agents import AgentRuntime  # noqa: E402
from career_os.models import FitReport, Job, TailoredResume  # noqa: E402
from career_os.recruiter_review import classify_recruiter_review  # noqa: E402


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
    assert "mandatory xAI/Grok adversarial review was unavailable" in notes
    assert "xAI/Grok is not configured" in notes
    assert "must not be treated as recruiter approval" in notes


@pytest.mark.asyncio
async def test_challenger_does_not_fallback_when_xai_fails(monkeypatch):
    """A failed xAI/Grok adversarial call must not be silently replaced."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("XAI_API_KEY", "xai-dummy")
    monkeypatch.setenv("GITHUB_TOKEN", "github-dummy")
    monkeypatch.setenv("AI_PROVIDER", "auto")
    runtime = AgentRuntime()

    async def boom(*_a, **_k):
        raise RuntimeError("xAI 503: temporary service failure")

    with patch.object(runtime, "_chat_xai", new=AsyncMock(side_effect=boom)) as xai:
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
    assert "503" not in notes
    assert "xAI/Grok" in notes
    assert "must not be treated as recruiter approval" in notes
    assert runtime.xai_diagnostic["credential_available"] is True
    assert runtime.xai_diagnostic["provider_call_succeeded"] is False
    assert runtime.xai_diagnostic["status"] == "CALL_FAILED"
    xai.assert_awaited_once()
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


@pytest.mark.asyncio
async def test_gemini_preflight_reports_missing_credential_without_secret(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "dummy")
    runtime = AgentRuntime()
    diagnostic = await runtime.gemini_preflight()
    assert diagnostic == {
        "credential_available": False,
        "configured_model": runtime.gemini_model,
        "provider_call_succeeded": False,
        "status": "CREDENTIAL_MISSING",
    }
    assert "key" not in " ".join(str(value) for value in diagnostic.values()).lower()


@pytest.mark.asyncio
async def test_gemini_preflight_reports_reachable_provider_without_secret(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-secret-not-output")
    monkeypatch.setenv("GITHUB_TOKEN", "dummy")
    runtime = AgentRuntime()
    runtime.last_provider_used = "manus:gpt-5-mini"
    with patch.object(runtime, "_chat_gemini", return_value="READY"):
        diagnostic = await runtime.gemini_preflight()
    assert diagnostic["credential_available"] is True
    assert diagnostic["provider_call_succeeded"] is True
    assert diagnostic["status"] == "READY"
    assert "test-secret-not-output" not in str(diagnostic)
    assert runtime.last_provider_used == "manus:gpt-5-mini"


def test_gemini_availability_alone_is_not_recruiter_approval():
    review = classify_recruiter_review("VERDICT: PASS", "xai:grok-4.6")
    assert review.status == "PASS"
    assert review.recommendation == "APPLY"


@pytest.mark.asyncio
async def test_primary_generation_reserves_gemini_for_independent_reviewer(monkeypatch):
    """A primary fallback must not consume Gemini before the challenger runs."""
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-dummy")
    monkeypatch.setenv("XAI_API_KEY", "xai-dummy")
    monkeypatch.setenv("AI_PROVIDER", "auto")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    runtime = AgentRuntime()

    with patch.object(runtime, "_chat_gemini", new=AsyncMock()) as gem:
        with patch.object(runtime, "_chat_xai", new=AsyncMock(return_value="primary")) as xai:
            response = await runtime._chat(
                "system",
                "user",
                exclude_providers={"gemini"},
            )

    assert response == "primary"
    gem.assert_not_called()
    xai.assert_awaited_once()


@pytest.mark.asyncio
async def test_real_xai_reviewer_result_can_pass_only_with_explicit_verdict(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "xai-dummy")
    monkeypatch.setenv("AI_PROVIDER", "auto")
    runtime = AgentRuntime()

    async def successful_review(*_args, **_kwargs):
        runtime.xai_diagnostic = {
            "credential_available": True,
            "configured_model": runtime.xai_model,
            "provider_call_succeeded": True,
            "status": "READY",
        }
        runtime.last_provider_used = f"xai:{runtime.xai_model}"
        return "VERDICT: PASS\\nISSUES: None\\nREQUIRED_FIXES: None"

    with patch.object(runtime, "_chat_xai", new=successful_review):
        notes = await runtime.challenge(
            profile="profile",
            job=_minimal_job(),
            fit=_minimal_fit(),
            resume=_minimal_resume(),
            evidence_pack=[],
        )

    review = classify_recruiter_review(notes, runtime.last_provider_used)
    assert runtime.xai_diagnostic["provider_call_succeeded"] is True
    assert review.status == "PASS"
    assert review.recommendation == "APPLY"


@pytest.mark.asyncio
async def test_malformed_gemini_response_stays_review_required(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "xai-dummy")
    monkeypatch.setenv("AI_PROVIDER", "auto")
    runtime = AgentRuntime()

    class MalformedResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"candidates": [{"content": {"parts": []}}]}

    class MalformedClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            return MalformedResponse()

    with patch("career_os.agents.httpx.AsyncClient", return_value=MalformedClient()):
        notes = await runtime.challenge(
            profile="profile",
            job=_minimal_job(),
            fit=_minimal_fit(),
            resume=_minimal_resume(),
            evidence_pack=[],
        )

    review = classify_recruiter_review(notes, runtime.last_provider_used)
    assert runtime.xai_diagnostic["status"] == "MALFORMED_RESPONSE"
    assert runtime.xai_diagnostic["provider_call_succeeded"] is False
    assert review.status == "NOT_RUN"
    assert review.recommendation == "REVIEW"

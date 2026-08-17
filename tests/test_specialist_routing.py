import pytest

from career_os import specialist_routing
from career_os.agents import AgentRuntime
from career_os.models import FitReport, Job, TailoredResume


def _runtime(*, deepseek=True, xai=True):
    runtime = object.__new__(AgentRuntime)
    runtime.provider = "auto"
    runtime.deepseek_key = "configured" if deepseek else None
    runtime.deepseek_model = "deepseek-test"
    runtime.xai_key = "configured" if xai else None
    runtime.xai_model = "grok-test"
    runtime.last_provider_used = None
    return runtime


def _job():
    return Job(
        title="Test Role",
        company="Test Company",
        location="Remote",
        description="Test job description",
    )


@pytest.mark.asyncio
async def test_fit_routes_to_deepseek_when_configured(monkeypatch):
    calls = []

    async def fake_fit(*args, **kwargs):
        calls.append("deepseek-fit")
        return FitReport(fit_score=88, recommendation="APPLY", band="A")

    monkeypatch.setattr(specialist_routing, "_specialist_fit", fake_fit)
    runtime = _runtime(deepseek=True, xai=False)

    result = await runtime.fit("profile", _job(), [], {})

    assert result.fit_score == 88
    assert calls == ["deepseek-fit"]
    assert runtime.last_provider_used == "deepseek:fit"


@pytest.mark.asyncio
async def test_resume_routes_grok_draft_then_deepseek_review(monkeypatch):
    calls = []
    draft = TailoredResume(title="Grok draft")
    reviewed = TailoredResume(title="DeepSeek reviewed")

    async def fake_draft(*args, **kwargs):
        calls.append("grok-draft")
        runtime.last_provider_used = "xai:grok-draft"
        return draft

    async def fake_review(*args, **kwargs):
        calls.append("deepseek-review")
        return reviewed

    runtime = _runtime(deepseek=True, xai=True)
    monkeypatch.setattr(specialist_routing, "_specialist_resume_draft", fake_draft)
    monkeypatch.setattr(specialist_routing, "_specialist_resume_review", fake_review)

    result = await runtime.resume("profile", _job(), FitReport(), [], {})

    assert result.title == "DeepSeek reviewed"
    assert calls == ["grok-draft", "deepseek-review"]
    assert runtime.last_provider_used == "xai:grok-draft+deepseek:review"


@pytest.mark.asyncio
async def test_resume_keeps_grok_draft_when_deepseek_review_fails(monkeypatch):
    draft = TailoredResume(title="Grok draft")

    async def fake_draft(*args, **kwargs):
        runtime.last_provider_used = "xai:grok-draft"
        return draft

    async def failing_review(*args, **kwargs):
        raise RuntimeError("DeepSeek unavailable")

    runtime = _runtime(deepseek=True, xai=True)
    monkeypatch.setattr(specialist_routing, "_specialist_resume_draft", fake_draft)
    monkeypatch.setattr(specialist_routing, "_specialist_resume_review", failing_review)

    result = await runtime.resume("profile", _job(), FitReport(), [], {})

    assert result.title == "Grok draft"
    assert runtime.last_provider_used == "xai:grok-draft"

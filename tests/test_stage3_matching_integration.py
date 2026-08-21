import json

import pytest

from career_os.agents import AgentRuntime
from career_os.models import FitReport
from scripts.sequential_stage_worker import process_matching


@pytest.fixture
def jd_ready_record():
    return {
        "job_id": "stage3-fixture-1",
        "status": "JD_READY",
        "pipeline_status": "JD_READY",
        "title": "Application Support Engineer",
        "company": "Fixture Systems",
        "location": "Hyderabad",
        "url": "https://fixture.example/jobs/1",
        "description": "Support incidents, SQL, APIs, and customer escalations.",
        "jd_text": "Support incidents, SQL, APIs, and customer escalations.",
        "jd_status": "complete",
    }


@pytest.mark.asyncio
async def test_stage3_calls_real_agent_runtime_fit_and_stops(tmp_path, monkeypatch, jd_ready_record):
    profile_path = tmp_path / "master_profile.md"
    profile_path.write_text("Confirmed professional evidence: support, SQL, APIs.\n", encoding="utf-8")

    monkeypatch.setenv("AI_PROVIDER", "auto")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_BASE", "https://provider.invalid/v1")
    runtime = AgentRuntime()

    async def controlled_chat(system, user, *, json_mode, max_tokens, exclude_providers=None):
        assert json_mode is True
        assert "Fixture Systems" in user
        runtime.last_provider_used = "controlled-fixture"
        return json.dumps({
            "fit_score": 84,
            "recommendation": "APPLY-STRETCH",
            "band": "B",
            "must_have_matches": ["SQL", "support"],
            "gaps": [],
            "blockers": [],
            "evidence": ["support and SQL are confirmed in the controlled profile"],
            "keywords": ["SQL", "APIs"],
            "risks": [],
            "rationale": "Controlled matching result.",
            "requirement_matches": [],
            "confirmation_requests": [],
        })

    monkeypatch.setattr(runtime, "_chat", controlled_chat)
    result = await process_matching(
        jd_ready_record,
        profile_path=str(profile_path),
        runtime=runtime,
        vault=[],
    )

    assert result["status"] == "MATCHED"
    assert result["pipeline_status"] == "MATCHED"
    assert result["current_stage"] == "MATCHING"
    assert result["match_score"] == 84
    assert result["matching_recommendation"] == "APPLY-STRETCH"
    assert result["matching_provider"] == "controlled-fixture"
    assert result["last_error"] is None
    assert "resume" not in result
    assert "notion_page_id" not in result


@pytest.mark.asyncio
async def test_stage3_failure_keeps_retryable_match_pending(tmp_path, monkeypatch, jd_ready_record):
    profile_path = tmp_path / "master_profile.md"
    profile_path.write_text("Confirmed professional evidence: support.\n", encoding="utf-8")

    class FailingRuntime:
        last_provider_used = None

        async def fit(self, profile, job, evidence_pack, jd_analysis):
            raise RuntimeError("controlled provider failure")

    result = await process_matching(
        jd_ready_record,
        profile_path=str(profile_path),
        runtime=FailingRuntime(),
        vault=[],
    )

    assert result["status"] == "MATCH_PENDING"
    assert result["pipeline_status"] == "MATCH_PENDING"
    assert result["current_stage"] == "MATCHING"
    assert result["error_code"] == "MATCHING_FAILED"
    assert "controlled provider failure" in result["last_error"]
    assert result["attempt_count"] == 1
    assert result["jd_status"] == "complete"

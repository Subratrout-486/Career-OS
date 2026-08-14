from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from career_os.application_mode import ApplicationMode
from career_os.browser_execution_state import BrowserExecutionStateStore, ExecutionStateError
from career_os.browser_preflight import _SAFETY_FLAGS, build_preflight_request, evaluate_preflight_observation


def _pipeline_result(tmp_path: Path) -> tuple[dict, Path]:
    resume = tmp_path / "Subrat_Rout_TCS_Service-Desk_Resume.pdf"
    resume.write_bytes(b"exact TCS JD-tailored resume")
    result = {
        "application_page_id": "notion-tcs-application-123",
        "resume_library_page_id": "notion-tcs-resume-456",
        "review_status": "READY_FOR_REVIEW",
        "job": {
            "company": "TCS",
            "title": "Service Desk Analyst",
            "url": "https://www.linkedin.com/jobs/view/tcs-easy-apply-123",
        },
        "job_verification": {
            "active": True,
            "status": "ACTIVE",
            "application_url": "https://www.linkedin.com/jobs/view/tcs-easy-apply-123",
            "ghost_job_risk": {"level": "ACCEPTABLE", "acceptable": True},
        },
        "fit": {"recommendation": "APPLY", "band": "B"},
        "primary_recommendation_provider": "manus:verified",
        "primary_recommendation": "APPLY",
        "resume": {"summary": "truthful TCS-tailored resume"},
        "resume_files": {"pdf": str(resume)},
        "ats": {"passed": True},
        "recruiter_review": {"status": "PASS", "recommendation": "APPLY", "provider": "gemini"},
        "design_qa": {"passed": True},
        "errors": [],
        # This is an explicit user-approved answer, not a Career OS inference.
        "application_questions": [{
            "question": "How many years of engineering experience do you have?",
            "required": True,
            "user_answer": "0",
            "status": "USER_APPROVED",
        }],
    }
    return result, resume


def _observation(resume: Path, **overrides: object) -> dict:
    digest = hashlib.sha256(resume.read_bytes()).hexdigest()
    observation = {
        "status": "PREFLIGHT_READY",
        "application_type": "easy_apply",
        "application_method": "linkedin_easy_apply",
        "observed_application_url": "https://www.linkedin.com/jobs/view/tcs-easy-apply-123",
        "application_url_verified": True,
        "complete_form_verified": True,
        "required_answers_verified": True,
        "required_questions": [{
            "question": "How many years of engineering experience do you have?",
            "required": True,
            "approved_answer": "0",
            "approval_status": "USER_APPROVED",
        }],
        "normal_upload_attempted": True,
        "normal_upload_succeeded": True,
        "file_chooser_retry_attempted": False,
        "input_retry_attempted": False,
        "selected_resume_filename": resume.name,
        "selected_resume_sha256": digest,
        "resume_attachment_visible": True,
        "safety_flags": {flag: False for flag in _SAFETY_FLAGS},
        "blockers": [],
        "application_record_id": "notion-tcs-application-123",
    }
    observation.update(overrides)
    return observation


def test_tcs_easy_apply_preflight_accepts_only_approved_zero_engineering_years(tmp_path: Path):
    result, resume = _pipeline_result(tmp_path)

    evaluation = evaluate_preflight_observation(result, _observation(resume))

    assert evaluation.status == "AUTO_APPLY_READY"
    assert evaluation.decision.mode is ApplicationMode.AUTO_APPLY
    assert evaluation.browser_context["required_answers_verified"] is True
    assert not evaluation.browser_context["human_controlled_blockers"]


def test_tcs_preflight_does_not_reinterpret_technical_support_as_engineering(tmp_path: Path):
    result, resume = _pipeline_result(tmp_path)
    observation = _observation(resume)
    observation["required_questions"][0]["approved_answer"] = "2"

    evaluation = evaluate_preflight_observation(result, observation)

    assert evaluation.status == "REVIEW_REQUIRED"
    assert evaluation.decision.mode is ApplicationMode.REVIEW_REQUIRED
    assert any("does not match approved answer" in blocker for blocker in evaluation.browser_context["human_controlled_blockers"])
    assert evaluation.browser_context["unknown_required_question"] is True


def test_force_resume_upload_fallback_is_required_after_normal_upload_failure(tmp_path: Path):
    result, resume = _pipeline_result(tmp_path)
    failed_upload = _observation(resume, normal_upload_succeeded=False)

    blocked = evaluate_preflight_observation(result, failed_upload)
    assert blocked.status == "REVIEW_REQUIRED"
    assert any("force-resume-upload fallback" in blocker for blocker in blocked.browser_context["human_controlled_blockers"])

    retried_upload = _observation(
        resume,
        normal_upload_succeeded=False,
        file_chooser_retry_attempted=True,
        file_chooser_retry_succeeded=True,
    )
    accepted = evaluate_preflight_observation(result, retried_upload)
    assert accepted.status == "AUTO_APPLY_READY"
    assert accepted.browser_context["resume_upload_fallback_used"] is True


def test_preflight_request_exposes_the_exact_current_tcs_resume_and_approved_zero(tmp_path: Path):
    result, resume = _pipeline_result(tmp_path)

    request = build_preflight_request(result)

    assert request["resume_filename"] == resume.name
    assert request["resume_sha256"] == hashlib.sha256(resume.read_bytes()).hexdigest()
    assert request["approved_questions"] == [{
        "question": "How many years of engineering experience do you have?",
        "answer": "0",
        "status": "USER_APPROVED",
        "required": True,
    }]


def test_durable_state_blocks_duplicate_tasks_and_fingerprint_drift(tmp_path: Path):
    store = BrowserExecutionStateStore(tmp_path / "state.json")
    record = {
        "application_id": "application-1",
        "job_url": "https://www.linkedin.com/jobs/view/tcs-easy-apply-123",
        "resume_sha256": "a" * 64,
    }

    reserved, _ = store.reserve(record, stage="preflight")
    assert reserved
    store.record_task(record, stage="preflight", task_id="preflight-1")
    duplicate, existing = store.reserve(record, stage="preflight")
    assert not duplicate
    assert existing["preflight"]["task_id"] == "preflight-1"

    with pytest.raises(ExecutionStateError, match="fingerprint changed"):
        store.reserve({**record, "resume_sha256": "b" * 64}, stage="preflight")

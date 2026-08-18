from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from career_os.application_questions import ApplicationQuestionStore
from career_os.applications import (
    APPLICATION_STATUS_READY,
    APPLICATION_STATUS_REVIEW,
    ApplicationsTracker,
)
from career_os.readiness import evaluate_readiness


def test_question_id_is_stable_for_whitespace_and_case_variants():
    first = ApplicationQuestionStore.question_id("app-1", "  Are you authorized to work? ")
    second = ApplicationQuestionStore.question_id("app-1", "are   you authorized to work?")
    assert first == second


def test_ready_requires_questions_and_resume_review():
    assert ApplicationsTracker.readiness_status(questions_ready=False, resume_review_approved=False) == APPLICATION_STATUS_REVIEW
    assert ApplicationsTracker.readiness_status(questions_ready=True, resume_review_approved=False) == APPLICATION_STATUS_REVIEW
    assert ApplicationsTracker.readiness_status(questions_ready=False, resume_review_approved=True) == APPLICATION_STATUS_REVIEW
    assert ApplicationsTracker.readiness_status(questions_ready=True, resume_review_approved=True) == APPLICATION_STATUS_READY


def test_sensitive_question_contract_is_human_controlled():
    question = {"type": "Sensitive", "needs_confirmation": False, "ai_draft": "Yes", "evidence": "Profile"}
    draft, evidence, status = ApplicationQuestionStore.safe_question_fields(question, "Sensitive")
    assert draft == ""
    assert evidence == ""
    assert status == "BLOCKED"


def test_ready_to_apply_requires_application_url():
    job = {
        "company": "Example",
        "title": "Support Engineer",
        "source_url": "https://example.com/careers/job-1",
        "jd_status": "complete",
        "jd_text": "Support engineer role requiring troubleshooting.",
    }
    result = {
        "fit": {"fit_score": 90, "rationale": "Strong fit."},
        "resume": {"title": "Product Support Resume"},
        "errors": [],
    }
    state, blockers = evaluate_readiness(job, result)
    assert state == "RESUME_READY"
    assert "verified application URL is missing" in blockers

    job["apply_url"] = "https://example.com/apply/job-1"
    state, blockers = evaluate_readiness(job, result)
    assert state == "READY_TO_APPLY"
    assert blockers == []

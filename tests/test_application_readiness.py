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

from pathlib import Path

import pytest

from career_os.application_mode import ApplicationMode, decide_application_mode
from career_os.browser_executor import (
    build_verified_browser_context,
    select_current_resume,
    verify_resume_attachment,
    verify_resume_hash,
)


def _result():
    return {
        "review_status": "READY_FOR_REVIEW",
        "job_verification": {"active": True, "status": "ACTIVE", "ghost_job_risk": {"level": "ACCEPTABLE", "acceptable": True}},
        "fit": {"recommendation": "APPLY", "band": "B"},
        "primary_recommendation_provider": "manus:gpt-5-mini",
        "primary_recommendation": "APPLY",
        "resume": {"summary": "truthful"},
        "ats": {"score": 100, "passed": True},
        "recruiter_review": {"status": "PASS", "recommendation": "APPLY", "provider": "deepseek:deepseek-chat"},
        "design_qa": {"passed": True},
        "errors": [],
    }


def test_resume_selection_uses_current_pdf_then_current_docx_only(tmp_path: Path):
    pdf = tmp_path / "Subrat_Rout_TCS_Service-Desk_Resume.pdf"
    docx = tmp_path / "Subrat_Rout_TCS_Service-Desk_Resume.docx"
    pdf.touch()
    docx.touch()

    plan = select_current_resume({"pdf": str(pdf), "docx": str(docx)})

    assert plan.primary == pdf
    assert plan.retries == (docx,)


def test_resume_selection_rejects_master_or_unrelated_artifacts(tmp_path: Path):
    master = tmp_path / "master_resume.pdf"
    unrelated = tmp_path / "Subrat_Rout_Unrelated_Job_Resume.pdf"
    master.touch()
    unrelated.touch()

    with pytest.raises(ValueError, match="current Career OS tailored"):
        select_current_resume({"pdf": str(master), "docx": str(unrelated)})


def test_resume_hash_requires_exact_current_artifact(tmp_path: Path):
    pdf = tmp_path / "Subrat_Rout_TCS_Service-Desk_Resume.pdf"
    pdf.write_bytes(b"current tailored resume")
    plan = select_current_resume({"pdf": str(pdf)})

    import hashlib

    assert verify_resume_hash(plan, hashlib.sha256(b"current tailored resume").hexdigest())
    assert not verify_resume_hash(plan, "0" * 64)


def test_attachment_requires_exact_filename_visible_in_form(tmp_path: Path):
    pdf = tmp_path / "Subrat_Rout_TCS_Service-Desk_Resume.pdf"
    pdf.touch()
    plan = select_current_resume({"pdf": str(pdf)})

    assert verify_resume_attachment(
        plan,
        selected_filename=pdf.name,
        form_text=f"Attached file: {pdf.name}",
        attached=True,
    )
    assert not verify_resume_attachment(
        plan,
        selected_filename="master_resume.pdf",
        form_text="Attached file: master_resume.pdf",
        attached=True,
    )
    assert not verify_resume_attachment(
        plan,
        selected_filename=pdf.name,
        form_text="",
        attached=True,
    )


def test_browser_context_requires_complete_form_and_resume_attachment():
    context = build_verified_browser_context(
        application_type="easy_apply",
        application_url_verified=True,
        resume_attachment_verified=True,
        complete_form_verified=True,
        resume_sha256_verified=True,
        required_questions=[
            {
                "required": True,
                "user_answer": "0",
                "status": "USER_APPROVED",
            }
        ],
    )

    decision = decide_application_mode(_result(), browser_context=context)

    assert decision.mode is ApplicationMode.AUTO_APPLY
    assert context["required_answers_verified"] is True


def test_incomplete_form_or_resume_attachment_stays_review_required():
    context = build_verified_browser_context(
        application_type="easy_apply",
        application_url_verified=True,
        resume_attachment_verified=False,
        complete_form_verified=False,
        required_questions=[
            {
                "required": True,
                "user_answer": "0",
                "status": "USER_APPROVED",
            }
        ],
    )

    decision = decide_application_mode(_result(), browser_context=context)

    assert decision.mode is ApplicationMode.REVIEW_REQUIRED
    assert "complete application form is not verified" in decision.blockers
    assert "current Career OS tailored resume attachment is not verified" in decision.blockers


def test_unapproved_required_answer_stays_review_required():
    context = build_verified_browser_context(
        application_type="easy_apply",
        application_url_verified=True,
        resume_attachment_verified=True,
        complete_form_verified=True,
        resume_sha256_verified=True,
        required_questions=[
            {
                "required": True,
                "user_answer": "0",
                "status": "NEEDS_REVIEW",
            }
        ],
    )

    decision = decide_application_mode(_result(), browser_context=context)

    assert decision.mode is ApplicationMode.REVIEW_REQUIRED
    assert "not all required answers are verified profile data" in decision.blockers

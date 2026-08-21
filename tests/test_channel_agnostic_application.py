from pathlib import Path

import pytest

from career_os.application_mode import ApplicationMode, decide_application_mode
from career_os.browser_executor import (
    build_verified_browser_context,
    select_current_resume,
    sha256_file,
    verify_application_destination,
    verify_resume_attachment,
    verify_submission_confirmation,
)


def _result():
    return {
        "review_status": "READY_FOR_REVIEW",
        "job_verification": {
            "active": True,
            "status": "ACTIVE",
            "ghost_job_risk": {"acceptable": True, "level": "ACCEPTABLE"},
        },
        "fit": {"recommendation": "APPLY", "band": "B"},
        "resume": {"summary": "truthful"},
        "ats": {"score": 100, "passed": True},
        "primary_recommendation_provider": "manus-primary",
        "primary_recommendation": "APPLY",
        "recruiter_review": {"status": "PASS", "provider": "deepseek:deepseek-chat", "recommendation": "APPLY"},
        "design_qa": {"passed": True},
        "errors": [],
    }


def _destination(channel: str, *, final_url: str | None = None, suspicious: bool = False):
    requested = "https://jobs.example.test/careers/support-role"
    return {
        "expected_url": requested,
        "requested_url": requested,
        "final_url": final_url or requested,
        "application_channel": channel,
        "redirect_chain": [requested, final_url or requested],
        "suspicious_redirect": suspicious,
    }


def _context(destination, *, questions=None, flow_pages_verified=True, **extra):
    return build_verified_browser_context(
        application_url=destination["requested_url"],
        final_application_url=destination["final_url"],
        application_destination=destination,
        resume_attachment_verified=True,
        complete_form_verified=True,
        resume_sha256_verified=True,
        flow_pages_verified=flow_pages_verified,
        required_questions=questions or [
            {"required": True, "user_answer": "Hyderabad", "status": "USER_APPROVED"}
        ],
        extra=extra,
    )


@pytest.mark.parametrize(
    "channel",
    [
        "linkedin_easy_apply",
        "greenhouse",
        "lever",
        "workday",
        "employer_hosted_form",
    ],
)
def test_legitimate_channels_are_descriptive_and_can_reach_auto_apply(channel):
    context = _context(_destination(channel), page_count=1)

    decision = decide_application_mode(_result(), browser_context=context)

    assert decision.mode is ApplicationMode.AUTO_APPLY
    assert context["application_channel"] == channel
    assert context["application_type"] == channel


def test_direct_employer_career_site_to_ats_is_supported():
    destination = _destination("employer_career_site")
    context = _context(destination, final_application_url="https://boards.greenhouse.io/acme/jobs/123")
    context["application_channel"] = "greenhouse"
    context["application_type"] = "greenhouse"

    assert decide_application_mode(_result(), browser_context=context).mode is ApplicationMode.AUTO_APPLY


def test_multi_page_flow_requires_all_pages_to_be_verified():
    context = _context(_destination("workday"), page_count=4, flow_pages_verified=False)

    decision = decide_application_mode(_result(), browser_context=context)

    assert decision.mode is ApplicationMode.REVIEW_REQUIRED
    assert "not every application-flow page is verified" in decision.blockers


def test_safe_non_easy_apply_flow_reaches_submission_only_after_confirmation(tmp_path: Path):
    resume = tmp_path / "Subrat_Rout_Greenhouse_Support_Resume.pdf"
    resume.write_bytes(b"current tailored resume")
    plan = select_current_resume({"pdf": str(resume)}, preferred="pdf")
    context = _context(_destination("greenhouse"), page_count=3)

    decision = decide_application_mode(_result(), browser_context=context)

    assert decision.mode is ApplicationMode.AUTO_APPLY
    assert verify_submission_confirmation(
        plan,
        confirmation_verified=True,
        submitted_filename=resume.name,
        submitted_sha256=sha256_file(resume),
    )
    assert not verify_submission_confirmation(
        plan,
        confirmation_verified=False,
        submitted_filename=resume.name,
        submitted_sha256=sha256_file(resume),
    )


@pytest.mark.parametrize("blocker", ["captcha", "otp", "login_or_identity_challenge", "assessment_or_test"])
def test_non_easy_apply_human_control_blockers_stay_review_required(blocker):
    context = _context(_destination("workday"), **{blocker: True})

    decision = decide_application_mode(_result(), browser_context=context)

    assert decision.mode is ApplicationMode.REVIEW_REQUIRED


def test_suspicious_redirect_stays_review_required():
    destination = _destination("employer_hosted_form", final_url="https://suspicious.example.test/collect", suspicious=True)
    context = _context(destination)

    assert not verify_application_destination(
        requested_url=destination["requested_url"],
        final_url=destination["final_url"],
        application_channel=destination["application_channel"],
        redirect_chain=destination["redirect_chain"],
        suspicious_redirect=True,
    )
    decision = decide_application_mode(_result(), browser_context=context)

    assert decision.mode is ApplicationMode.REVIEW_REQUIRED
    assert "application destination is suspicious" in decision.blockers


def test_browser_must_open_career_os_application_url():
    destination = _destination("greenhouse")

    assert not verify_application_destination(
        expected_application_url=destination["requested_url"],
        requested_url="https://unrelated.example.test/apply",
        final_url=destination["final_url"],
        application_channel=destination["application_channel"],
    )


def test_unknown_required_question_stays_review_required():
    context = _context(
        _destination("lever"),
        questions=[{"required": True, "user_answer": "", "status": "NEEDS_REVIEW"}],
    )

    decision = decide_application_mode(_result(), browser_context=context)

    assert decision.mode is ApplicationMode.REVIEW_REQUIRED
    assert "not all required answers are verified profile data" in decision.blockers


def test_non_easy_apply_resume_upload_fallback_accepts_only_current_docx(tmp_path: Path):
    pdf = tmp_path / "Subrat_Rout_Workday_Support_Resume.pdf"
    docx = tmp_path / "Subrat_Rout_Workday_Support_Resume.docx"
    pdf.write_bytes(b"pdf artifact")
    docx.write_bytes(b"docx artifact")
    plan = select_current_resume({"pdf": str(pdf), "docx": str(docx)}, preferred="pdf")

    assert verify_resume_attachment(
        plan,
        selected_filename=docx.name,
        form_text=f"Uploaded resume: {docx.name}",
        attached=True,
    )
    assert not verify_resume_attachment(
        plan,
        selected_filename="master_resume.pdf",
        form_text="Uploaded resume: master_resume.pdf",
        attached=True,
    )

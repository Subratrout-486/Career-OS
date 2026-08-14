from scripts.reconcile_manus_browser_execution import _normalise_outcome
from career_os.browser_outcomes import decide_browser_outcome


APPLICATION_ID = "notion-tcs-application-123"
RESUME_HASH = "a" * 64


def _outcome(**overrides):
    value = {
        "status": "SUBMITTED",
        "submitted": True,
        "confirmation_source": "linkedin",
        "confirmation_evidence": "LinkedIn displays: Application submitted for TCS Service Desk Analyst.",
        "confirmation_url": "https://www.linkedin.com/jobs/application-confirmation/123",
        "resume_attachment_verified": True,
        "resume_sha256_verified": True,
        "selected_resume_sha256": RESUME_HASH,
        "normal_upload_attempted": True,
        "normal_upload_succeeded": True,
        "file_chooser_retry_attempted": False,
        "file_chooser_retry_succeeded": False,
        "input_retry_attempted": False,
        "input_retry_succeeded": False,
        "application_record_id": APPLICATION_ID,
        "blockers": [],
    }
    value.update(overrides)
    return value


def test_tcs_execution_marks_applied_only_after_linkedin_confirmation_and_exact_resume_proof():
    prepared = _normalise_outcome(APPLICATION_ID, RESUME_HASH, _outcome())
    decision = decide_browser_outcome(prepared)

    assert decision.application_status == "Applied"
    assert prepared["selected_resume_sha256"] == RESUME_HASH


def test_task_success_without_real_confirmation_stays_review():
    prepared = _normalise_outcome(
        APPLICATION_ID,
        RESUME_HASH,
        _outcome(status="NOT_SUBMITTED", submitted=False, confirmation_source="none", confirmation_evidence="", confirmation_url=""),
    )
    decision = decide_browser_outcome(prepared)

    assert decision.application_status == "Review"
    assert "browser executor did not confirm submission" in decision.blockers
    assert "independent employer/ATS/LinkedIn confirmation source is missing" in decision.blockers


def test_resume_hash_mismatch_or_failed_force_retry_stays_review():
    hash_mismatch = _normalise_outcome(APPLICATION_ID, RESUME_HASH, _outcome(selected_resume_sha256="b" * 64))
    assert decide_browser_outcome(hash_mismatch).application_status == "Review"
    assert "browser-selected resume SHA-256 does not match the dispatched tailored resume" in hash_mismatch["blockers"]

    fallback_failed = _normalise_outcome(
        APPLICATION_ID,
        RESUME_HASH,
        _outcome(
            normal_upload_succeeded=False,
            file_chooser_retry_attempted=True,
            file_chooser_retry_succeeded=False,
        ),
    )
    assert decide_browser_outcome(fallback_failed).application_status == "Review"
    assert "force-resume-upload fallback did not confirm a successful exact tailored-resume upload" in fallback_failed["blockers"]

from career_os.browser_outcomes import decide_browser_outcome


def _confirmed_submission(**overrides):
    outcome = {
        "status": "SUBMITTED",
        "submitted": True,
        "confirmation_source": "ats",
        "confirmation_evidence": "ATS confirmation page states: Application received, reference 12345.",
        "confirmation_url": "https://jobs.example/confirmation/12345",
        "resume_attachment_verified": True,
        "resume_sha256_verified": True,
        "blockers": [],
    }
    outcome.update(overrides)
    return outcome


def test_explicit_independent_confirmation_with_exact_resume_marks_applied():
    decision = decide_browser_outcome(_confirmed_submission())
    assert decision.application_status == "Applied"
    assert not decision.blockers


def test_navigation_or_task_success_without_confirmation_stays_review():
    decision = decide_browser_outcome(
        {
            "status": "COMPLETED",
            "submitted": False,
            "confirmation_evidence": "",
            "blockers": [],
        }
    )
    assert decision.application_status == "Review"
    assert "browser executor did not confirm submission" in decision.blockers
    assert "employer/ATS/LinkedIn confirmation evidence is missing" in decision.blockers


def test_submission_without_independent_source_or_resume_proof_stays_review():
    decision = decide_browser_outcome(_confirmed_submission(confirmation_source="none", resume_sha256_verified=False))
    assert decision.application_status == "Review"
    assert "independent employer/ATS/LinkedIn confirmation source is missing" in decision.blockers
    assert "exact tailored-resume SHA-256 was not verified" in decision.blockers


def test_any_human_blocker_prevents_applied_transition():
    decision = decide_browser_outcome(
        _confirmed_submission(blockers=["salary expectation required a user decision"])
    )
    assert decision.application_status == "Review"
    assert "salary expectation required a user decision" in decision.blockers

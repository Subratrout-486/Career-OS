from career_os.browser_outcomes import decide_browser_outcome


def test_explicit_submission_with_confirmation_marks_applied():
    decision = decide_browser_outcome(
        {
            "status": "SUBMITTED",
            "submitted": True,
            "confirmation_evidence": "ATS confirmation page states: Application received, reference 12345.",
            "blockers": [],
        }
    )
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
    assert "employer/ATS confirmation evidence is missing" in decision.blockers


def test_any_human_blocker_prevents_applied_transition():
    decision = decide_browser_outcome(
        {
            "status": "SUBMITTED",
            "submitted": True,
            "confirmation_evidence": "Confirmation page displayed.",
            "blockers": ["salary expectation required a user decision"],
        }
    )
    assert decision.application_status == "Review"
    assert "salary expectation required a user decision" in decision.blockers

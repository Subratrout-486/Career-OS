from career_os.application_mode import ApplicationMode, decide_application_mode


def _result(**overrides):
    result = {
        "review_status": "READY_FOR_REVIEW",
        "job_verification": {"active": True, "status": "ACTIVE"},
        "fit": {"recommendation": "APPLY", "band": "B"},
        "resume": {"summary": "truthful"},
        "ats": {"score": 90},
        "errors": [],
    }
    result.update(overrides)
    return result


def test_default_pipeline_requires_human_review():
    decision = decide_application_mode(_result())
    assert decision.mode is ApplicationMode.REVIEW_REQUIRED
    assert "browser context not supplied" in decision.blockers


def test_truth_guard_failure_blocks_application():
    decision = decide_application_mode(_result(errors=["TRUTH_GUARD: unsupported claim"]))
    assert decision.mode is ApplicationMode.DO_NOT_APPLY
    assert any("Truth Guard failed" in blocker for blocker in decision.blockers)


def test_omitted_unconfirmed_jd_gaps_do_not_block_application():
    result = _result(
        resume={
            "summary": "truthful",
            "unsupported_claims": ["Windows", "BMC Helix", "GCP"],
        }
    )
    context = {
        "application_type": "easy_apply",
        "application_url_verified": True,
        "required_answers_verified": True,
    }
    decision = decide_application_mode(result, browser_context=context)
    assert decision.mode is ApplicationMode.AUTO_APPLY


def test_actual_unsupported_resume_claim_still_blocks_application():
    decision = decide_application_mode(
        _result(errors=["TRUTH_GUARD: Tool 'GCP' appears in the resume but is unsupported."])
    )
    assert decision.mode is ApplicationMode.DO_NOT_APPLY


def test_unknown_work_conditions_require_review_not_do_not_apply():
    context = {
        "application_type": "easy_apply",
        "application_url_verified": True,
        "required_answers_verified": True,
        "on_site_availability_unknown": True,
        "shift_availability_unknown": True,
    }
    decision = decide_application_mode(_result(), browser_context=context)
    assert decision.mode is ApplicationMode.REVIEW_REQUIRED
    assert "on-site availability requires user confirmation" in decision.blockers
    assert "shift availability requires user confirmation" in decision.blockers


def test_verified_browser_context_can_be_auto_apply():
    context = {
        "application_type": "easy_apply",
        "application_url_verified": True,
        "required_answers_verified": True,
    }
    decision = decide_application_mode(_result(), browser_context=context)
    assert decision.mode is ApplicationMode.AUTO_APPLY


def test_sensitive_browser_questions_require_review():
    context = {
        "application_type": "easy_apply",
        "application_url_verified": True,
        "required_answers_verified": True,
        "salary_or_ctc_question": True,
    }
    decision = decide_application_mode(_result(), browser_context=context)
    assert decision.mode is ApplicationMode.REVIEW_REQUIRED
    assert "salary/CTC answer remains user-controlled" in decision.blockers

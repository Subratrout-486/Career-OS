from career_os.application_mode import ApplicationMode, decide_application_mode
from career_os.models import FitReport


def _result(**overrides):
    result = {
        "review_status": "READY_FOR_REVIEW",
        "job_verification": {"active": True, "status": "ACTIVE"},
        "fit": {"recommendation": "APPLY", "band": "B"},
        "resume": {"summary": "truthful"},
        "ats": {"score": 90, "passed": True},
        "recruiter_review": {"status": "PASS"},
        "design_qa": {"passed": True},
        "errors": [],
    }
    result.update(overrides)
    return result


def _verified_context(**overrides):
    context = {
        "application_type": "easy_apply",
        "application_url_verified": True,
        "required_answers_verified": True,
        "complete_form_verified": True,
        "resume_attachment_verified": True,
    }
    context.update(overrides)
    return context


def test_default_pipeline_requires_human_review():
    decision = decide_application_mode(_result())
    assert decision.mode is ApplicationMode.REVIEW_REQUIRED
    assert "browser context not supplied" in decision.blockers


def test_truth_guard_failure_blocks_application():
    decision = decide_application_mode(_result(errors=["TRUTH_GUARD: unsupported claim"]))
    assert decision.mode is ApplicationMode.DO_NOT_APPLY
    assert any("Truth Guard failed" in blocker for blocker in decision.blockers)


def test_fit_report_normalizes_list_valued_requirement_match_fields():
    fit = FitReport.model_validate(
        {
            "fit_score": 70,
            "recommendation": "APPLY",
            "band": "B",
            "requirement_matches": [
                {
                    "requirement": "technical support",
                    "status": "MATCH",
                    "employer": ["FactSet Systems India Pvt. Ltd.", "IGT Solutions"],
                    "role": [],
                }
            ],
        }
    )
    assert fit.requirement_matches[0].employer == "FactSet Systems India Pvt. Ltd.; IGT Solutions"
    assert fit.requirement_matches[0].role == ""


def test_omitted_unconfirmed_jd_gaps_do_not_block_application():
    result = _result(
        resume={
            "summary": "truthful",
            "unsupported_claims": ["Windows", "BMC Helix", "GCP"],
        }
    )
    decision = decide_application_mode(result, browser_context=_verified_context())
    assert decision.mode is ApplicationMode.AUTO_APPLY


def test_actual_unsupported_resume_claim_still_blocks_application():
    decision = decide_application_mode(
        _result(errors=["TRUTH_GUARD: Tool 'GCP' appears in the resume but is unsupported."])
    )
    assert decision.mode is ApplicationMode.DO_NOT_APPLY


def test_unknown_work_conditions_require_review_not_do_not_apply():
    context = _verified_context(
        on_site_availability_unknown=True,
        shift_availability_unknown=True,
    )
    decision = decide_application_mode(_result(), browser_context=context)
    assert decision.mode is ApplicationMode.REVIEW_REQUIRED
    assert "on-site availability requires user confirmation" in decision.blockers
    assert "shift availability requires user confirmation" in decision.blockers


def test_verified_browser_context_can_be_auto_apply():
    decision = decide_application_mode(_result(), browser_context=_verified_context())
    assert decision.mode is ApplicationMode.AUTO_APPLY


def test_missing_quality_gates_require_review_even_with_verified_browser_context():
    decision = decide_application_mode(
        _result(
            ats={"score": 90, "passed": False},
            recruiter_review={"status": "NOT_RUN"},
            design_qa={"passed": False},
        ),
        browser_context=_verified_context(),
    )
    assert decision.mode is ApplicationMode.REVIEW_REQUIRED
    assert "ATS final check has not passed" in decision.blockers
    assert "independent recruiter review has not passed" in decision.blockers
    assert "resume design QA has not passed" in decision.blockers


def test_sensitive_browser_questions_require_review():
    context = _verified_context(salary_or_ctc_question=True)
    decision = decide_application_mode(_result(), browser_context=context)
    assert decision.mode is ApplicationMode.REVIEW_REQUIRED
    assert "salary/CTC answer remains user-controlled" in decision.blockers


def test_missing_complete_form_or_resume_attachment_requires_review():
    context = _verified_context(
        complete_form_verified=False,
        resume_attachment_verified=False,
    )
    decision = decide_application_mode(_result(), browser_context=context)
    assert decision.mode is ApplicationMode.REVIEW_REQUIRED
    assert "complete application form is not verified" in decision.blockers
    assert "current Career OS tailored resume attachment is not verified" in decision.blockers

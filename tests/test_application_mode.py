from career_os.application_mode import ApplicationMode, decide_application_mode
from career_os.models import FitReport


def _result(**overrides):
    result = {
        "review_status": "READY_FOR_REVIEW",
        "job_verification": {"active": True, "status": "ACTIVE", "ghost_job_risk": {"level": "ACCEPTABLE", "acceptable": True}},
        "fit": {"recommendation": "APPLY", "band": "B"},
        "primary_recommendation_provider": "manus:gpt-5-mini",
        "primary_recommendation": "APPLY",
        "resume": {"summary": "truthful"},
        "ats": {"score": 90, "passed": True},
        "recruiter_review": {"status": "PASS", "recommendation": "APPLY", "provider": "deepseek:deepseek-chat"},
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
        "resume_sha256_verified": True,
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
    assert "mandatory DeepSeek adversarial review has not passed" in decision.blockers
    assert "resume design QA has not passed" in decision.blockers


def test_non_gemini_recruiter_pass_requires_review():
    decision = decide_application_mode(
        _result(recruiter_review={"status": "PASS", "recommendation": "APPLY", "provider": "gemini:gemini-3.1-flash-lite"}),
        browser_context=_verified_context(),
    )
    assert decision.mode is ApplicationMode.REVIEW_REQUIRED
    assert "mandatory DeepSeek adversarial review provenance is missing" in decision.blockers


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


def test_missing_acceptable_ghost_job_risk_requires_review():
    decision = decide_application_mode(
        _result(job_verification={"active": True, "status": "ACTIVE", "ghost_job_risk": {"level": "REVIEW", "acceptable": False}}),
        browser_context=_verified_context(),
    )
    assert decision.mode is ApplicationMode.REVIEW_REQUIRED
    assert "ghost-job risk has not been assessed as acceptable" in decision.blockers


def test_non_manus_primary_recommendation_requires_review():
    decision = decide_application_mode(
        _result(primary_recommendation_provider="deepseek:deepseek-chat", primary_recommendation="APPLY"),
        browser_context=_verified_context(),
    )
    assert decision.mode is ApplicationMode.REVIEW_REQUIRED
    assert "mandatory Manus primary recommendation provenance is missing" in decision.blockers


def test_non_apply_gemini_adversarial_recommendation_requires_review():
    decision = decide_application_mode(
        _result(recruiter_review={"status": "PASS", "recommendation": "REVIEW", "provider": "deepseek:deepseek-chat"}),
        browser_context=_verified_context(),
    )
    assert decision.mode is ApplicationMode.REVIEW_REQUIRED
    assert "mandatory DeepSeek adversarial recommendation is not APPLY" in decision.blockers


def test_missing_resume_hash_verification_requires_review():
    decision = decide_application_mode(_result(), browser_context=_verified_context(resume_sha256_verified=False))
    assert decision.mode is ApplicationMode.REVIEW_REQUIRED
    assert "exact current Career OS tailored resume SHA-256 is not verified" in decision.blockers

from career_os.ghost_job_risk import assess_ghost_job_risk


def _verified_posting(**overrides):
    posting = {
        "active": True,
        "status": "ACTIVE",
        "http_status": 200,
        "title_ok": True,
        "company_ok": True,
        "location_ok": True,
        "description_ok": True,
        "responsibilities_found": True,
        "application_url": "https://jobs.example.com/123",
    }
    posting.update(overrides)
    return posting


def test_verified_active_employer_posting_has_acceptable_risk():
    result = assess_ghost_job_risk(_verified_posting(), source="Employer ATS — Greenhouse")
    assert result.level == "ACCEPTABLE"
    assert result.acceptable is True


def test_missing_freshness_or_identity_signal_requires_review():
    result = assess_ghost_job_risk(_verified_posting(http_status=None), source="Employer ATS — Greenhouse")
    assert result.level == "REVIEW"
    assert result.acceptable is False
    assert "employer posting did not return a successful HTTP response" in result.reasons


def test_identified_non_employer_source_requires_review():
    result = assess_ghost_job_risk(_verified_posting(), source="Third-party aggregator")
    assert result.level == "REVIEW"
    assert "posting source is not identified as an employer/ATS source" in result.reasons

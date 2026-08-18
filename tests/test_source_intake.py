from career_os.source_intake import (
    deduplicate_source_jobs,
    normalize_source_job,
    source_capability,
)


def _job(url="https://jobs.example.com/roles/123?utm_source=jobright"):
    return {
        "title": "Technical Support Analyst",
        "company": "Acme",
        "location": "Hyderabad, India",
        "url": url,
        "description": "Support production applications and investigate incidents.",
        "job_id": "JR-123",
    }


def test_jobright_normalization_preserves_authorized_browser_provenance():
    normalized = normalize_source_job(
        _job(), source="jobright", intake_method="authorized_browser_capture"
    )

    assert normalized["source"] == "Jobright — authorized browser capture"
    assert normalized["discovery_channel"] == "authorized_browser_capture"
    assert normalized["source_job_id"] == "JR-123"
    assert normalized["url"] == "https://jobs.example.com/roles/123"
    assert normalized["dedupe_key"]


def test_specialist_source_capabilities_do_not_claim_an_api():
    for source in ("jobright", "simplify"):
        capability = source_capability(source)
        assert capability["public_api_supported"] is False
        assert capability["status"] == "ACCESS_REQUIRED"
        assert "authorized_browser_capture" in capability["supported_intake"]


def test_deduplication_collapses_cross_source_tracking_url_variants():
    jobright = normalize_source_job(
        _job(), source="jobright", intake_method="authorized_browser_capture"
    )
    simplify = normalize_source_job(
        _job("https://jobs.example.com/roles/123?ref=simplify"),
        source="simplify",
        intake_method="authorized_browser_capture",
    )

    accepted, duplicates = deduplicate_source_jobs([jobright, simplify])

    assert len(accepted) == 1
    assert len(duplicates) == 1
    assert duplicates[0]["source"].startswith("Simplify")


def test_specialist_source_preserves_missing_job_description_for_retry():
    payload = _job()
    payload.pop("description")
    normalized = normalize_source_job(
        payload, source="simplify", intake_method="authorized_json_export"
    )
    assert normalized["jd_status"] == "unavailable"
    assert normalized["ready_state"] == "JD_PENDING"
    assert normalized["ingestion_status"] == "JD_PENDING"

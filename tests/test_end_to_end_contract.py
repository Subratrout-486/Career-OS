from __future__ import annotations

from career_os.readiness import apply_readiness_to_job, evaluate_readiness
from career_os.source_intake import normalize_source_job


def test_job_with_missing_jd_is_preserved_and_retryable():
    job = normalize_source_job(
        {"title": "Support Analyst", "company": "Acme", "url": "https://acme.example/jobs/1", "apply_url": "https://acme.example/apply/1"},
        source="employer_ats",
        intake_method="public_ats_feed",
    )
    assert job["jd_status"] == "unavailable"
    assert job["ready_state"] == "JD_PENDING"
    assert job["apply_url"].endswith("/apply/1")


def test_ready_to_apply_requires_jd_match_and_resume():
    job = {
        "company": "Acme", "title": "Support Analyst", "location": "Hyderabad",
        "source_url": "https://acme.example/jobs/1", "jd_status": "complete",
        "jd_text": "Support incidents, SQL, and customer escalations.",
    }
    result = {"fit": {"fit_score": 82, "rationale": "Strong support and SQL evidence."}, "resume": {"title": "Technical Support Resume"}}
    state, blockers = evaluate_readiness(job, result)
    assert state == "RESUME_READY"
    assert "verified application URL is missing" in blockers
    job["apply_url"] = "https://acme.example/apply/1"
    result.update({
        "application_destination_verified": True,
        "truth_guard_passed": True,
        "ats": {"passed": True},
        "independent_ats": {"passed": True},
        "recruiter_review": {"status": "PASS"},
        "evidence_count": 2,
        "usable_evidence_count": 2,
    })
    state, blockers = evaluate_readiness(job, result)
    assert state == "READY_TO_APPLY"
    assert blockers == []
    updated = apply_readiness_to_job(job, result)
    assert updated["ready_state"] == "READY_TO_APPLY"
    assert updated["recommended_resume"] == "Technical Support Resume"


def test_unresolved_error_prevents_ready_to_apply():
    job = {
        "company": "Acme", "title": "Support Analyst", "source_url": "https://acme.example/jobs/1",
        "jd_status": "complete", "jd_text": "Support incidents and escalations.",
    }
    state, blockers = evaluate_readiness(job, {"fit": {"fit_score": 80}, "resume": {"title": "Support Resume"}, "errors": ["NOTION_WRITE_FAILED"]})
    assert state == "RESUME_READY"
    assert "critical ingestion or pipeline errors remain" in blockers

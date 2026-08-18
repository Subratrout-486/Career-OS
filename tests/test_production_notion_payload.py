from scripts.sync_job_to_notion import ready_status


def test_production_sync_reaches_ready_state_only_with_required_evidence():
    result = {
        "job": {
            "company": "Acme",
            "title": "Support Analyst",
            "location": "Hyderabad",
            "url": "https://acme.example/jobs/1",
            "description": "Support incidents, SQL, and customer escalations.",
            "jd_status": "complete",
        },
        "fit": {"fit_score": 82, "rationale": "Strong support and SQL evidence."},
        "resume": {"title": "Technical Support Resume"},
    }
    assert ready_status(result) == "Resume Ready"
    result["job"]["apply_url"] = "https://acme.example/apply/1"
    result.update({
        "application_destination_verified": True,
        "truth_guard_passed": True,
        "ats": {"passed": True},
        "independent_ats": {"passed": True},
        "recruiter_review": {"status": "PASS"},
        "evidence_count": 2,
        "usable_evidence_count": 2,
    })
    assert ready_status(result) == "Ready to Apply"

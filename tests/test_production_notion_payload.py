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
    assert ready_status(result) == "Ready to Apply"

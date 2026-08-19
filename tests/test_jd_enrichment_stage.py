from pathlib import Path

from scripts import jd_enrichment_stage as stage


def test_discovery_runtime_is_a_stage_2_input(monkeypatch, tmp_path):
    jobs = tmp_path / "jobs"
    discovery = jobs / "discovery_runtime"
    discovery.mkdir(parents=True)
    record = {
        "job_id": "controlled-1",
        "status": "INTAKED",
        "company": "HighRadius",
        "title": "Senior Product Manager",
        "description": "About the role. Responsibilities include product metrics, requirements, qualifications, experience, and skills. " * 8,
    }
    path = discovery / "controlled-1.json"
    path.write_text(__import__("json").dumps(record), encoding="utf-8")
    monkeypatch.setattr(stage, "ROOT", jobs)
    assert stage.discover_inputs() == [Path(path)]


def test_greenhouse_fallback_url_is_derived_from_canonical_source():
    record = {
        "source_url": "https://boards-api.greenhouse.io/v1/boards/highradius/jobs?content=true",
        "source_job_id": "7707536003",
    }
    assert stage.greenhouse_fallback_url(record) == (
        "https://boards-api.greenhouse.io/v1/boards/highradius/jobs/7707536003?content=true"
    )


def test_existing_intake_description_can_make_job_jd_ready(monkeypatch):
    monkeypatch.setattr(stage, "fetch_url", lambda url: (None, "http_403"))
    record = {
        "job_id": "controlled-2",
        "status": "INTAKED",
        "company": "HighRadius",
        "title": "Senior Product Manager",
        "url": "https://example.invalid/job",
        "description": "About the role. Responsibilities include product metrics, requirements, qualifications, experience, and skills. " * 8,
    }
    updated, outcome = stage.enrich(record, Path("controlled-2.json"))
    assert outcome == "JD_READY"
    assert updated["jd_status"] == "complete"
    assert updated["jd_evidence_source"] == "intake_description"
    assert updated["status"] == "JD_READY"


def test_greenhouse_fallback_can_rescue_employer_page_block(monkeypatch):
    employer_url = "https://www.highradius.com/about/careers-list?gh_jid=7707536003"
    greenhouse_url = "https://boards-api.greenhouse.io/v1/boards/highradius/jobs/7707536003?content=true"
    payload = '{"content":"<h2>Responsibilities</h2><p>Requirements include product metrics, qualifications, experience and skills. </p>"}'

    def fake_fetch(url):
        if url == employer_url:
            return None, "http_403"
        if url == greenhouse_url:
            return payload, None
        return None, "unexpected"

    monkeypatch.setattr(stage, "fetch_url", fake_fetch)
    record = {
        "job_id": "controlled-3",
        "status": "INTAKED",
        "source_url": "https://boards-api.greenhouse.io/v1/boards/highradius/jobs?content=true",
        "source_job_id": "7707536003",
        "url": employer_url,
        "description": "too short",
    }
    updated, outcome = stage.enrich(record, Path("controlled-3.json"))
    assert outcome == "JD_READY"
    assert updated["jd_evidence_source"] == "greenhouse_api"

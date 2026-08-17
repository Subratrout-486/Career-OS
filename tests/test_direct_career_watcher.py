import json
from pathlib import Path

import pytest

from scripts.direct_career_watcher import check_company, eligible, load_registry, normalize


JOB = {
    "@type": "JobPosting",
    "title": "Application Support Analyst",
    "description": "Support REST APIs, SQL and incident management for Hyderabad customers.",
    "url": "https://jobs.example.com/apply/123?utm_source=feed",
    "datePosted": "2026-08-17",
    "identifier": {"value": "123"},
    "jobLocation": {"address": {"addressLocality": "Hyderabad", "addressRegion": "Telangana", "addressCountry": "IN"}},
}


def test_normalize_preserves_official_identity_and_hashes():
    item = normalize("Example", JOB, "https://careers.example.com/jobs/123", "2026-08-18T00:00:00+00:00")
    assert item is not None
    assert item["job_id"] == "123"
    assert item["official_job_url"] == "https://jobs.example.com/apply/123"
    assert item["location"] == "Hyderabad Telangana IN"
    assert item["job_status"] == "ACTIVE"
    assert item["content_hash"]
    assert item["source_hash"]


def test_eligibility_prioritizes_india_and_rejects_unrelated_roles():
    assert eligible("Product Support Engineer", "Hyderabad, India", "")
    assert not eligible("Director of Engineering", "Hyderabad, India", "")
    assert not eligible("Marketing Manager", "London, UK", "")


def test_check_company_is_failure_isolated(monkeypatch):
    def fake_fetch(url):
        if "broken" in url:
            raise RuntimeError("blocked")
        return 200, url, '<script type="application/ld+json">' + json.dumps(JOB) + "</script>"

    monkeypatch.setattr("scripts.direct_career_watcher.fetch", fake_fetch)
    good = check_company({"company": "Good", "careers_url": "https://good.example/careers"})
    bad = check_company({"company": "Broken", "careers_url": "https://broken.example/careers"})
    assert good["source_status"] == "AVAILABLE"
    assert len(good["jobs"]) == 1
    assert bad["source_status"] == "UNAVAILABLE"
    assert bad["jobs"] == []


def test_watchlist_contains_requested_companies_and_aliases():
    registry = load_registry()
    names = {item["company"] for item in registry}
    assert len(registry) >= 130
    assert {"Accenture", "Google", "Microsoft"}.issubset(names)
    assert next(item for item in registry if item["company"] == "Hewlett Packard Enterprise")["canonical_name"] == "HPE"
    assert next(item for item in registry if item["company"] == "Xilinx / AMD")["canonical_name"] == "AMD"

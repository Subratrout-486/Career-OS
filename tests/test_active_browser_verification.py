"""Regression coverage for authenticated current-page active-job evidence."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from career_os.job_verify import verify_job_active  # noqa: E402
from career_os.models import Job  # noqa: E402


class _UnavailableClient:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, *args, **kwargs):
        raise RuntimeError("network unavailable")


def _job() -> Job:
    return Job(
        title="Managed Services Client Service Desk Administrator",
        company="NTT DATA, Inc.",
        location="Greater Hyderabad Area, Telangana, India",
        url="https://www.linkedin.com/jobs/view/4450806865/",
        source="LinkedIn",
        source_job_id="4450806865",
        description="A" * 100 + " Responsibilities include service desk support and escalation.",
    )


def _evidence(**overrides):
    evidence = {
        "page_loaded": True,
        "current_listing_evidence": True,
        "page_url": "https://www.linkedin.com/jobs/view/4450806865/",
        "page_title": "Managed Services Client Service Desk Administrator",
        "page_company": "NTT DATA, Inc.",
        "job_id": "4450806865",
        "apply_available": True,
        "apply_label": "Apply on company website",
        "apply_destination_url": "https://careers.example.com/ntt-data/4450806865",
        "application_channel": "Employer career site",
        "listing_text": "Posted 19 hours ago. Responsibilities include service desk support.",
    }
    evidence.update(overrides)
    return evidence


def test_active_linkedin_company_website_apply_uses_authenticated_browser_evidence():
    with patch("career_os.job_verify.httpx.Client", _UnavailableClient):
        result = verify_job_active(_job(), browser_evidence=_evidence())
    assert result.active is True
    assert result.status == "ACTIVE"
    assert result.verification_source == "authenticated_browser"
    assert result.application_url == "https://careers.example.com/ntt-data/4450806865"
    assert result.ghost_job_risk["acceptable"] is True


def test_active_linkedin_easy_apply_uses_job_page_as_verified_destination():
    with patch("career_os.job_verify.httpx.Client", _UnavailableClient):
        result = verify_job_active(
            _job(),
            browser_evidence=_evidence(
                apply_label="Easy Apply",
                application_channel="LinkedIn Easy Apply",
                apply_destination_url=None,
            ),
        )
    assert result.active is True
    assert result.status == "ACTIVE"
    assert result.application_url == "https://www.linkedin.com/jobs/view/4450806865/"
    assert result.application_channel == "LinkedIn Easy Apply"


def test_linkedin_safety_redirect_is_normalized_to_employer_destination():
    with patch("career_os.job_verify.httpx.Client", _UnavailableClient):
        result = verify_job_active(
            _job(),
            browser_evidence=_evidence(
                apply_destination_url="https://www.linkedin.com/safety/go/?url=https%3A%2F%2Fcareers.example.com%2Fntt-data%2F4450806865"
            ),
        )
    assert result.status == "ACTIVE"
    assert result.application_url == "https://careers.example.com/ntt-data/4450806865"
    assert result.ghost_job_risk["acceptable"] is True


def test_current_browser_company_apply_metadata_is_used_when_http_also_succeeds():
    response = type("Response", (), {"status_code": 200, "url": "https://www.linkedin.com/jobs/view/4450806865/", "history": [], "text": "active listing"})()
    client = type("Client", (), {"__enter__": lambda self: self, "__exit__": lambda self, *args: None, "get": lambda self, url: response})
    with patch("career_os.job_verify.httpx.Client", client):
        result = verify_job_active(
            _job(),
            browser_evidence=_evidence(
                apply_destination_url="https://careers.example.com/ntt-data/4450806865"
            ),
        )
    assert result.status == "ACTIVE"
    assert result.verification_source == "authenticated_browser"
    assert result.application_channel == "Employer career site"
    assert result.application_url == "https://careers.example.com/ntt-data/4450806865"
    assert result.browser_listing_evidence is True
    assert result.ghost_job_risk["acceptable"] is True


def test_closed_job_remains_inactive_even_with_apply_control():
    with patch("career_os.job_verify.httpx.Client", _UnavailableClient):
        result = verify_job_active(_job(), browser_evidence=_evidence(closed_signal=True))
    assert result.active is False
    assert result.status == "INACTIVE"


def test_expired_job_remains_inactive():
    with patch("career_os.job_verify.httpx.Client", _UnavailableClient):
        result = verify_job_active(_job(), browser_evidence=_evidence(expired_signal=True))
    assert result.active is False
    assert result.status == "INACTIVE"


def test_mismatched_job_id_and_url_is_not_active():
    with patch("career_os.job_verify.httpx.Client", _UnavailableClient):
        result = verify_job_active(
            _job(),
            browser_evidence=_evidence(
                page_url="https://www.linkedin.com/jobs/view/9999999999/",
                job_id="9999999999",
            ),
        )
    assert result.active is False
    assert result.status == "UNKNOWN"
    assert any("job ID" in note for note in result.notes)


def test_inaccessible_job_is_inactive_not_active_by_field_presence():
    with patch("career_os.job_verify.httpx.Client", _UnavailableClient):
        result = verify_job_active(
            _job(),
            browser_evidence=_evidence(page_loaded=False, inaccessible=True, http_status=403),
        )
    assert result.active is False
    assert result.status == "INACTIVE"

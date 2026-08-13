from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from career_os.models import Job
from career_os.job_verify import verify_job_fields, verify_job_active


def test_missing_fields():
    job = Job(title="", company="", location="", url="", description="short")
    v = verify_job_fields(job)
    assert not v.title_ok
    assert not v.description_ok
    assert v.notes


def test_good_fields():
    job = Job(
        title="Product Support Engineer",
        company="HighRadius",
        location="Hyderabad, India",
        url="https://example.com/jobs/1",
        description="A" * 80 + " Responsibilities include product support and SLA handling.",
    )
    v = verify_job_fields(job)
    assert v.title_ok and v.company_ok and v.location_ok and v.description_ok


def test_invalid_url_inactive():
    job = Job(
        title="Engineer",
        company="Acme",
        location="Hyderabad",
        url="not-a-url",
        description="A" * 80 + " Responsibilities for support.",
    )
    v = verify_job_active(job)
    assert v.status == "INACTIVE"
    assert not v.active


if __name__ == "__main__":
    test_missing_fields()
    test_good_fields()
    test_invalid_url_inactive()
    print("PASS job_verify tests")

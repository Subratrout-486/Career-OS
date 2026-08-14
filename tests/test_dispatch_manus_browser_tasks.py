import hashlib
from pathlib import Path

import pytest

from career_os.manus_browser_runner import ManusApiError
from scripts.dispatch_manus_browser_tasks import validate_record


def _record(resume_path: Path) -> dict[str, object]:
    digest = hashlib.sha256(resume_path.read_bytes()).hexdigest()
    return {
        "application_mode": "AUTO_APPLY",
        "review_status": "READY_FOR_REVIEW",
        "job_active": True,
        "ats_passed": True,
        "recruiter_review_passed": True,
        "design_qa_passed": True,
        "complete_form_verified": True,
        "required_answers_verified": True,
        "resume_attachment_verified": True,
        "human_controlled_blockers": [],
        "company": "Example Co",
        "title": "Production Support Engineer",
        "job_url": "https://jobs.example/apply/123",
        "application_id": "application-123",
        "resume_path": str(resume_path),
        "resume_sha256": digest,
    }


def test_valid_verified_manifest_record_is_accepted(tmp_path):
    resume = tmp_path / "exact-resume.pdf"
    resume.write_bytes(b"verified resume bytes")
    application, resolved_resume, digest = validate_record(_record(resume))
    assert application["application_id"] == "application-123"
    assert resolved_resume == resume
    assert digest == hashlib.sha256(b"verified resume bytes").hexdigest()


def test_manifest_with_human_blocker_is_rejected(tmp_path):
    resume = tmp_path / "exact-resume.pdf"
    resume.write_bytes(b"verified resume bytes")
    record = _record(resume)
    record["human_controlled_blockers"] = ["salary/CTC requires user decision"]
    with pytest.raises(ManusApiError, match="human_controlled_blockers"):
        validate_record(record)


def test_manifest_with_resume_hash_mismatch_is_rejected(tmp_path):
    resume = tmp_path / "exact-resume.pdf"
    resume.write_bytes(b"verified resume bytes")
    record = _record(resume)
    record["resume_sha256"] = "0" * 64
    with pytest.raises(ManusApiError, match="resume_sha256"):
        validate_record(record)

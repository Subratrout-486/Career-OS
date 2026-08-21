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
        "ghost_job_risk_acceptable": True,
        "manus_recommendation_apply": True,
        "truth_guard_passed": True,
        "ats_passed": True,
        "recruiter_review_passed": True,
        "gemini_adversarial_passed": True,
        "gemini_adversarial_apply": True,
        "gemini_adversarial_provider": "deepseek:deepseek-chat",
        "design_qa_passed": True,
        "complete_form_verified": True,
        "required_answers_verified": True,
        "resume_attachment_verified": True,
        "resume_sha256_verified": True,
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


def test_manifest_without_gemini_adversarial_evidence_is_rejected(tmp_path):
    resume = tmp_path / "exact-resume.pdf"
    resume.write_bytes(b"verified resume bytes")
    record = _record(resume)
    record["gemini_adversarial_provider"] = "xai:grok-4.6"
    with pytest.raises(ManusApiError, match="gemini_adversarial_provider"):
        validate_record(record)


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


@pytest.mark.parametrize(
    "field",
    [
        "ghost_job_risk_acceptable",
        "manus_recommendation_apply",
        "truth_guard_passed",
        "gemini_adversarial_apply",
        "resume_sha256_verified",
    ],
)
def test_manifest_without_required_phase_two_evidence_is_rejected(tmp_path, field):
    resume = tmp_path / "exact-resume.pdf"
    resume.write_bytes(b"verified resume bytes")
    record = _record(resume)
    record[field] = False
    with pytest.raises(ManusApiError, match=field):
        validate_record(record)

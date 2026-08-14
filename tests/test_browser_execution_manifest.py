import json

import pytest

from career_os.browser_execution_manifest import (
    MANIFEST_SCHEMA_VERSION,
    ManifestGenerationError,
    generate_browser_execution_manifest,
    validate_browser_execution_record,
)


def _result(resume_path):
    return {
        "job": {
            "title": "Technical Support Analyst",
            "company": "Acme",
            "location": "Hyderabad",
            "url": "https://careers.acme.example/apply/123",
            "source_job_id": "source-123",
        },
        "job_verification": {
            "active": True,
            "status": "ACTIVE",
            "application_url": "https://careers.acme.example/apply/123",
            "ghost_job_risk": {"acceptable": True, "level": "ACCEPTABLE"},
        },
        "fit": {"recommendation": "APPLY", "band": "A"},
        "resume": {"title": "Technical Support Analyst"},
        "ats": {"passed": True},
        "recruiter_review": {"status": "PASS", "provider": "Gemini", "recommendation": "APPLY"},
        "primary_recommendation_provider": "Manus",
        "primary_recommendation": "APPLY",
        "design_qa": {"passed": True},
        "resume_files": {"pdf": str(resume_path)},
        "resume_library_page_id": "3ac8bc1d-ce0e-8051-a553-000bb5f58abe",
        "application_page_id": "a6925702-0d2a-4d68-919b-3401e1d8ff75",
        "application_mode": "AUTO_APPLY",
        "review_status": "READY_FOR_REVIEW",
        "errors": [],
    }


def _context(**overrides):
    context = {
        "application_type": "straightforward_form",
        "application_method": "external employer application",
        "application_url_verified": True,
        "resume_attachment_verified": True,
        "complete_form_verified": True,
        "resume_sha256_verified": True,
        "required_answers_verified": True,
    }
    context.update(overrides)
    return context


def test_generate_manifest_only_for_all_verified_gates(tmp_path):
    resume = tmp_path / "Subrat_Rout_Acme_Technical-Support-Analyst_Resume.pdf"
    resume.write_bytes(b"current tailored resume")
    path = tmp_path / "manifest.json"

    manifest = generate_browser_execution_manifest(
        _result(resume), browser_context=_context(), output_path=path
    )

    assert manifest["schema_version"] == MANIFEST_SCHEMA_VERSION
    assert path.is_file()
    persisted = json.loads(path.read_text(encoding="utf-8"))
    record = persisted["applications"][0]
    assert record["application_mode"] == "AUTO_APPLY"
    assert record["resume_artifact"]["runtime_path"] == str(resume)
    assert record["resume_artifact"]["resume_library_reference"].startswith("https://www.notion.so/")
    assert all(record["all_gate_results"].values())
    validate_browser_execution_record(record)


def test_manifest_blocks_unknown_required_question_even_if_application_mode_is_auto(tmp_path):
    resume = tmp_path / "Subrat_Rout_Acme_Technical-Support-Analyst_Resume.pdf"
    resume.write_bytes(b"current tailored resume")

    with pytest.raises(ManifestGenerationError, match="unknown mandatory question"):
        generate_browser_execution_manifest(
            _result(resume),
            browser_context=_context(unknown_required_question=True),
            output_path=tmp_path / "manifest.json",
        )


def test_manifest_requires_durable_resume_library_record(tmp_path):
    resume = tmp_path / "Subrat_Rout_Acme_Technical-Support-Analyst_Resume.pdf"
    resume.write_bytes(b"current tailored resume")
    result = _result(resume)
    result["resume_library_page_id"] = ""

    with pytest.raises(ManifestGenerationError, match="Resume Library"):
        generate_browser_execution_manifest(
            result, browser_context=_context(), output_path=tmp_path / "manifest.json"
        )


def test_manifest_validation_rejects_flattened_gate_tampering(tmp_path):
    resume = tmp_path / "Subrat_Rout_Acme_Technical-Support-Analyst_Resume.pdf"
    resume.write_bytes(b"current tailored resume")
    record = generate_browser_execution_manifest(
        _result(resume), browser_context=_context(), output_path=tmp_path / "manifest.json"
    )["applications"][0]
    record["ats_passed"] = False

    with pytest.raises(ManifestGenerationError, match="ats_passed"):
        validate_browser_execution_record(record)


def test_manifest_refuses_to_overwrite_incompatible_existing_schema(tmp_path):
    resume = tmp_path / "Subrat_Rout_Acme_Technical-Support-Analyst_Resume.pdf"
    resume.write_bytes(b"current tailored resume")
    path = tmp_path / "manifest.json"
    path.write_text('{"schema_version": "unrecognized"}\n', encoding="utf-8")

    with pytest.raises(ManifestGenerationError, match="incompatible schema"):
        generate_browser_execution_manifest(
            _result(resume), browser_context=_context(), output_path=path
        )

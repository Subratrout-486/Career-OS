"""Regression tests for Applications config and Truth Guard evidence mappings."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import career_os.applications as applications_module  # noqa: E402
from career_os.applications import (  # noqa: E402
    APPLICATION_STATUS_READY,
    DEFAULT_APPLICATIONS_DS,
    ApplicationsTracker,
)
from career_os.evidence import retrieve_evidence  # noqa: E402
from career_os.evidence_vault_snapshot import VAULT_SNAPSHOT  # noqa: E402
from career_os.agents import TRUTH_RULES  # noqa: E402
from career_os.models import FitReport, TailoredResume  # noqa: E402
from career_os.truth_guard import validate_resume_truth  # noqa: E402


def test_applications_data_source_id_is_live_value():
    assert DEFAULT_APPLICATIONS_DS == "a6925702-0d2a-4d68-919b-3401e1d8ff75"
    assert "a7755702" not in DEFAULT_APPLICATIONS_DS
    tracker = ApplicationsTracker()
    # Without env override, tracker uses the live default.
    assert tracker.data_source_id == DEFAULT_APPLICATIONS_DS


def test_application_status_exact_notion_option():
    assert APPLICATION_STATUS_READY == "Ready to Apply"
    assert APPLICATION_STATUS_READY != "READY TO APPLY"


def test_application_tracker_reuses_exact_job_url_before_creating(monkeypatch):
    """A rerun must reuse an exact durable record instead of posting a duplicate."""
    monkeypatch.setenv("NOTION_TOKEN", "test-token")
    calls: list[dict[str, object]] = []

    class Response:
        status_code = 200
        is_error = False
        text = ""

        @staticmethod
        def json():
            return {
                "results": [
                    {
                        "id": "existing-page-id",
                        "properties": {"Job URL": {"url": "https://jobs.example.com/123"}},
                    }
                ]
            }

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def post(self, url, *, headers, json):
            calls.append({"url": url, "headers": headers, "json": json})
            return Response()

    monkeypatch.setattr(applications_module.httpx, "AsyncClient", lambda timeout: Client())
    tracker = ApplicationsTracker()
    page_id = asyncio.run(
        tracker.create_review_record(
            {
                "job": {
                    "company": "Example Co",
                    "title": "Support Engineer",
                    "url": "https://jobs.example.com/123",
                }
            }
        )
    )

    assert page_id == "existing-page-id"
    assert len(calls) == 1
    assert calls[0]["url"].endswith(f"/data_sources/{DEFAULT_APPLICATIONS_DS}/query")
    assert calls[0]["json"] == {
        "filter": {"property": "Job URL", "url": {"equals": "https://jobs.example.com/123"}},
        "page_size": 10,
    }


def test_resume_truth_rules_expose_hard_igt_tool_prohibition():
    assert "HARD IGT RESUME PROHIBITION" in TRUTH_RULES
    for tool in ("Python", "SQL", "Power Query", "Power BI", "REST API testing", "UAT", "Excel"):
        assert tool in TRUTH_RULES


def test_obsolete_applications_ds_env_is_ignored(monkeypatch):
    """Misconfigured Actions var a775... must not override the live DS."""
    monkeypatch.setenv(
        "NOTION_APPLICATIONS_DATA_SOURCE_ID",
        "a7755702-0d2a-4d68-919b-3401e1d8ff75",
    )
    tracker = ApplicationsTracker()
    assert tracker.data_source_id == DEFAULT_APPLICATIONS_DS
    assert "a7755702" not in tracker.data_source_id


def test_python_factset_confirmed_in_snapshot():
    result = retrieve_evidence(
        "Python automation scripting", VAULT_SNAPSHOT, include_diagnostic=True
    )
    factset_matches = [
        m
        for m in result.matched
        if "FactSet" in m.item.employer and "Python" in m.item.claim
    ]
    assert factset_matches, "Expected confirmed Python evidence mapped to FactSet"
    for m in factset_matches:
        assert m.item.is_usable_professional
        assert m.item.professional_status == "Professional-Confirmed"
        assert m.item.confirmation_status in {
            "Confirmed-by-User",
            "Confirmed-by-Document",
        }


def test_excel_not_confirmed_for_igt():
    result = retrieve_evidence(
        "Advanced Excel and data validation", VAULT_SNAPSHOT, include_diagnostic=True
    )
    for m in result.matched:
        assert "Excel" not in m.item.claim, (
            f"Excel must not be usable professional evidence until confirmed: {m.item.claim}"
        )

    excel_related = [
        e
        for e in result.excluded
        if "Excel" in e.item.claim or "excel" in e.item.claim.lower()
    ]
    assert excel_related or not result.has_usable_evidence
    for e in excel_related:
        assert e.item.confirmation_status == "Needs-Confirmation" or (
            e.item.professional_status != "Professional-Confirmed"
        )
        assert not e.item.is_usable_professional


def test_explicit_review_marker_overrides_stale_confirmed_status():
    """A legacy row's explicit review marker must beat stale select values."""
    stale = next(
        item
        for item in VAULT_SNAPSHOT
        if item.claim == "Python for operational reporting and data validation at IGT"
    )
    stale = stale.__class__(
        **{
            **stale.__dict__,
            "professional_status": "Professional-Confirmed",
            "confirmation_status": "Confirmed-by-Document",
            "context": "Phase 1 — Needs-Confirmation; retained for audit only.",
            "safe_wording": "(Do not use on resume until confirmed)",
        }
    )
    assert not stale.is_usable_professional
    result = retrieve_evidence(
        "Python operational reporting", [stale], include_diagnostic=True
    )
    assert not result.has_usable_evidence
    assert result.excluded
    assert any("explicit Needs-Confirmation" in item.exclusion_reason for item in result.excluded)


def test_truth_guard_allows_python_under_factset():
    profile = Path(ROOT / "config" / "master_profile.md").read_text(encoding="utf-8")
    resume = TailoredResume(
        title="Product Support Engineer",
        summary="Support engineer with Python automation experience.",
        skills=["Python", "SQL", "ServiceNow"],
        experience=[
            {
                "title": "Product Support Engineer",
                "company": "FactSet Systems",
                "dates": "Nov 2024 – Jan 2026",
                "bullets": [
                    "Built Python automation for production health checks and log parsing."
                ],
            }
        ],
        changes=[],
        unsupported_claims=[],
        evidence_trace=["Python automation at FactSet"],
    )
    fit = FitReport(
        fit_score=80,
        recommendation="APPLY",
        band="A",
        rationale="Supported by confirmed evidence.",
        must_have_matches=["application support", "SQL"],
        gaps=[],
        blockers=[],
        risks=[],
        confirmation_requests=[],
    )
    issues = validate_resume_truth(
        resume=resume,
        profile=profile,
        fit=fit,
        evidence_pack=VAULT_SNAPSHOT,
    )
    python_issues = [i for i in issues if "python" in i.lower()]
    assert not python_issues, f"Unexpected Python truth issues: {python_issues}"
    assert "Experience entry is not a structured object." not in issues


def test_truth_guard_allows_factset_tools_when_resume_also_lists_igt_history():
    """Shared summary/skills tools remain valid when separately mapped to FactSet."""
    profile = Path(ROOT / "config" / "master_profile.md").read_text(encoding="utf-8")
    resume = TailoredResume(
        title="Application Support Engineer",
        summary="Application support engineer with Python and SQL experience.",
        skills=["Python", "SQL", "REST APIs", "UAT"],
        experience=[
            {
                "title": "Product Support Engineer",
                "company": "FactSet Systems India Pvt. Ltd.",
                "dates": "Nov 2024 – Jan 2026",
                "bullets": [
                    "Built Python automation and used SQL and REST APIs for production support and release validation."
                ],
            },
            {
                "title": "Technical Operations Analyst",
                "company": "IGT Solutions",
                "dates": "Dec 2023 – May 2024",
                "bullets": [
                    "Acted as a technical point of contact for reservation-platform issues and documented workflows."
                ],
            },
        ],
        education=[],
        changes=[],
        unsupported_claims=[],
        evidence_trace=["Python and SQL at FactSet"],
    )
    fit = FitReport(
        fit_score=75,
        recommendation="APPLY",
        band="B",
        rationale="Supported by confirmed FactSet evidence.",
        confirmation_requests=[],
    )
    issues = validate_resume_truth(
        resume=resume,
        profile=profile,
        fit=fit,
        evidence_pack=VAULT_SNAPSHOT,
    )
    assert not any("explicitly disallowed" in issue.lower() for issue in issues), issues


def test_truth_guard_blocks_python_under_igt_even_if_stale_evidence_is_misclassified():
    """A stale Notion row must not override the explicit IGT evidence policy."""
    profile = Path(ROOT / "config" / "master_profile.md").read_text(encoding="utf-8")
    stale_igt_python = next(
        item for item in VAULT_SNAPSHOT if item.claim == "Python for operational reporting and data validation at IGT"
    )
    stale_igt_python = stale_igt_python.__class__(
        **{
            **stale_igt_python.__dict__,
            "professional_status": "Professional-Confirmed",
            "confirmation_status": "Confirmed-by-User",
        }
    )
    resume = TailoredResume(
        title="Technical Operations Analyst",
        summary="Operations analyst with Python reporting experience.",
        skills=["Python", "Salesforce"],
        experience=[
            {
                "title": "Technical Operations Analyst",
                "company": "IGT Solutions",
                "dates": "Dec 2023 – May 2024",
                "bullets": [
                    "Used Python for operational reporting and data validation."
                ],
            }
        ],
        changes=[],
        unsupported_claims=[],
        evidence_trace=[],
    )
    fit = FitReport(
        fit_score=75,
        recommendation="APPLY",
        band="B",
        rationale="Python must remain unconfirmed for IGT.",
        confirmation_requests=[],
    )
    issues = validate_resume_truth(
        resume=resume,
        profile=profile,
        fit=fit,
        evidence_pack=[*VAULT_SNAPSHOT, stale_igt_python],
    )
    assert any("python" in issue.lower() and "igt" in issue.lower() for issue in issues), issues


def test_truth_guard_blocks_excel_under_igt_without_evidence():
    profile = Path(ROOT / "config" / "master_profile.md").read_text(encoding="utf-8")
    resume = TailoredResume(
        title="Technical Operations Analyst",
        summary="Ops analyst with Excel reporting.",
        skills=["Excel", "SQL"],
        experience=[
            {
                "title": "Technical Operations Analyst",
                "company": "IGT Solutions",
                "dates": "Dec 2023 – May 2024",
                "bullets": [
                    "Used Advanced Excel for operational reporting and data validation."
                ],
            }
        ],
        changes=[],
        unsupported_claims=[],
        evidence_trace=[],
    )
    fit = FitReport(
        fit_score=70,
        recommendation="APPLY",
        band="B",
        rationale="Excel unconfirmed.",
        must_have_matches=[],
        gaps=["Excel"],
        blockers=[],
        risks=[],
        confirmation_requests=[
            "JD requires Advanced Excel. Confirm professional use and employer."
        ],
    )
    issues = validate_resume_truth(
        resume=resume,
        profile=profile,
        fit=fit,
        evidence_pack=VAULT_SNAPSHOT,
    )
    assert any("excel" in i.lower() for i in issues), (
        "Truth guard must flag unconfirmed Excel under IGT"
    )


def test_truth_guard_blocks_personal_linux_python_under_concentrix():
    profile = Path(ROOT / "config" / "master_profile.md").read_text(encoding="utf-8")
    resume = TailoredResume(
        title="Support Engineer",
        summary="Support engineer.",
        experience=[
            {
                "title": "Technical Support Representative",
                "company": "Concentrix (Comcast process)",
                "dates": "Nov 2021 – Oct 2022",
                "bullets": [
                    "Built Python log-analysis scripts and used Linux in a personal home lab."
                ],
            }
        ],
    )
    fit = FitReport(
        fit_score=70,
        recommendation="APPLY",
        band="B",
        rationale="",
        must_have_matches=[],
        gaps=[],
        blockers=[],
        risks=[],
        confirmation_requests=[],
    )
    issues = validate_resume_truth(
        resume=resume,
        profile=profile,
        fit=fit,
        evidence_pack=VAULT_SNAPSHOT,
    )
    assert any("python" in issue.lower() for issue in issues)
    assert any("linux" in issue.lower() for issue in issues)


def test_application_notes_use_ats_score_field_and_resume_reference():
    result = {
        "job": {
            "company": "Accenture",
            "title": "Application Support Engineer",
            "location": "Hyderabad",
            "source": "Accenture Careers",
            "url": "https://example.com/job",
        },
        "fit": {"recommendation": "APPLY-STRETCH", "fit_score": 75, "band": "B"},
        "ats": {"score": 100},
        "resume": {"experience": []},
        "resume_library_page_id": "3bb8bc1d-ce0e-8130-a237-da7583ff2db1",
        "resume_files": {
            "pdf": "generated_resumes/example.pdf",
            "docx": "generated_resumes/example.docx",
        },
    }
    tracker = ApplicationsTracker()
    notes = tracker._build_notes(result)
    properties = {}
    # Reuse the production payload construction through the public helper contract.
    assert "ATS score: 100" in notes
    assert "Resume summary:" in notes

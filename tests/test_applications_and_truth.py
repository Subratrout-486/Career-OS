"""Regression tests for Applications config and Truth Guard evidence mappings."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from career_os.applications import (  # noqa: E402
    APPLICATION_STATUS_READY,
    DEFAULT_APPLICATIONS_DS,
    ApplicationsTracker,
)
from career_os.evidence import retrieve_evidence  # noqa: E402
from career_os.evidence_vault_snapshot import VAULT_SNAPSHOT  # noqa: E402
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
        assert "automation" in m.item.claim.lower() or "python" in m.item.claim.lower()


def test_excel_not_confirmed_for_igt():
    result = retrieve_evidence(
        "Advanced Excel and data validation", VAULT_SNAPSHOT, include_diagnostic=True
    )
    # Must not treat Excel as confirmed professional evidence for IGT (or any employer)
    # until employer-specific confirmation exists.
    for m in result.matched:
        assert "Excel" not in m.item.claim, (
            f"Excel must not be usable professional evidence until confirmed: {m.item.claim}"
        )
        assert m.item.employer != "IGT Solutions" or "Excel" not in m.item.claim

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
        assert e.item.employer != "IGT Solutions" or not e.item.is_usable_professional


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
        band="Strong",
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
        band="Moderate",
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


if __name__ == "__main__":
    import traceback

    tests = [name for name in dir() if name.startswith("test_")]
    passed = failed = 0
    for name in tests:
        try:
            globals()[name]()
            print(f"PASS  {name}")
            passed += 1
        except Exception as exc:
            print(f"FAIL  {name}: {exc}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed, {passed + failed} total")
    raise SystemExit(1 if failed else 0)

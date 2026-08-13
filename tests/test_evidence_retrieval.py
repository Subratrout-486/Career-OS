"""Automated tests for the Career Evidence retrieval helper."""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running without install: python tests/test_evidence_retrieval.py from repo root.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from career_os.evidence import (  # noqa: E402
    EvidenceItem,
    retrieve_evidence,
    format_retrieval,
)
from career_os.evidence_vault_snapshot import VAULT_SNAPSHOT  # noqa: E402


def _employers(result) -> set[str]:
    return {m.item.employer for m in result.matched}


def test_servicenow_matches_factset():
    result = retrieve_evidence(
        "Experience with ServiceNow and incident management", VAULT_SNAPSHOT
    )
    assert result.has_usable_evidence
    assert any("ServiceNow" in m.item.claim for m in result.matched)
    assert "FactSet Systems India Pvt. Ltd." in _employers(result)
    for m in result.matched:
        assert m.item.is_usable_professional


def test_sql_matches_confirmed_factset_oracle():
    result = retrieve_evidence(
        "SQL troubleshooting and Oracle database support", VAULT_SNAPSHOT
    )
    assert result.has_usable_evidence
    claims = [m.item.claim for m in result.matched]
    assert any("Oracle" in c or "SQL" in c for c in claims)
    for m in result.matched:
        assert m.item.is_usable_professional
        assert not (
            m.item.employer == "IGT Solutions"
            and m.item.confirmation_status == "Needs-Confirmation"
        )


def test_aws_cloud_matches_factset_not_lab_services():
    result = retrieve_evidence("AWS cloud application support", VAULT_SNAPSHOT)
    assert result.has_usable_evidence
    assert any("AWS / cloud application support" in m.item.claim for m in result.matched)
    for m in result.matched:
        assert m.item.professional_status == "Professional-Confirmed"
        assert "Self-Directed" not in m.item.employer
        assert "EC2" not in m.item.claim


def test_aws_lab_services_excluded_from_professional():
    result = retrieve_evidence(
        "AWS EC2 IAM S3 CloudWatch", VAULT_SNAPSHOT, include_diagnostic=True
    )
    for m in result.matched:
        assert "EC2" not in m.item.claim
        assert m.item.professional_status == "Professional-Confirmed"
    lab = [e for e in result.excluded if "EC2" in e.item.claim]
    if lab:
        assert "Self-Directed" in lab[0].exclusion_reason


def test_technical_support_matches_concentrix_and_or_factset():
    result = retrieve_evidence("Customer-facing technical support", VAULT_SNAPSHOT)
    assert result.has_usable_evidence
    employers = _employers(result)
    assert employers & {
        "FactSet Systems India Pvt. Ltd.",
        "Concentrix (Comcast process)",
    }
    for m in result.matched:
        assert m.item.employer in {
            "FactSet Systems India Pvt. Ltd.",
            "Concentrix (Comcast process)",
            "IGT Solutions",
            "Multiple / Cross-Employer",
        }


def test_group_reservations_matches_igt():
    result = retrieve_evidence("Group reservations and event operations", VAULT_SNAPSHOT)
    assert result.has_usable_evidence
    assert _employers(result) == {"IGT Solutions"}
    assert any("Group reservations" in m.item.claim for m in result.matched)


def test_corporate_governance_matches_factset():
    result = retrieve_evidence(
        "Corporate governance and SEC filings", VAULT_SNAPSHOT
    )
    assert result.has_usable_evidence
    assert "FactSet Systems India Pvt. Ltd." in _employers(result)
    assert any(
        "Corporate governance" in m.item.claim or "SEC" in m.item.claim
        for m in result.matched
    )


def test_power_bi_no_confirmed_but_diagnostic_shows_igt():
    result = retrieve_evidence(
        "Power BI dashboard development", VAULT_SNAPSHOT, include_diagnostic=True
    )
    assert not result.has_usable_evidence
    assert result.has_related_unconfirmed
    assert any(
        "Power BI" in e.item.claim and e.item.employer == "IGT Solutions"
        for e in result.excluded
    )
    for e in result.excluded:
        if "Power BI" in e.item.claim:
            assert (
                "Needs-Confirmation" in e.exclusion_reason
                or "Unconfirmed" in e.exclusion_reason
            )


def test_cross_employer_results_remain_separate():
    result = retrieve_evidence(
        "technical support ticket triage incident management", VAULT_SNAPSHOT
    )
    for m in result.matched:
        assert m.item.employer
        assert " + " not in m.item.employer
        assert " and FactSet" not in m.item.employer


def test_rejected_evidence_excluded():
    rejected = EvidenceItem(
        claim="Fabricated Kubernetes cluster ownership",
        category="Tool",
        employer="FactSet Systems India Pvt. Ltd.",
        role="Product Support Engineer",
        employment_period="Nov 2024 – Jan 2026",
        professional_status="Unconfirmed",
        usage_level="Unknown",
        context="Rejected claim",
        evidence_source="test",
        confirmation_status="Rejected",
        safe_wording="(rejected)",
    )
    vault = list(VAULT_SNAPSHOT) + [rejected]
    result = retrieve_evidence(
        "Kubernetes cluster ownership", vault, include_diagnostic=True
    )
    assert not result.has_usable_evidence
    assert any(e.item.confirmation_status == "Rejected" for e in result.excluded)


def test_self_directed_aws_services_excluded():
    result = retrieve_evidence(
        "AWS cloud application support", VAULT_SNAPSHOT, include_diagnostic=True
    )
    assert any(
        m.item.claim.startswith("AWS / cloud application support") for m in result.matched
    )
    for m in result.matched:
        assert m.item.professional_status != "Self-Directed"
        assert "EC2" not in m.item.claim


def test_empty_vs_unconfirmed_distinction():
    empty = retrieve_evidence("Quantum computing quantum annealer", VAULT_SNAPSHOT)
    assert not empty.has_usable_evidence
    assert not empty.has_related_unconfirmed
    assert "NO EVIDENCE FOUND" in empty.summary()

    power = retrieve_evidence(
        "Power BI dashboard development", VAULT_SNAPSHOT, include_diagnostic=True
    )
    assert not power.has_usable_evidence
    assert power.has_related_unconfirmed
    assert "NO CONFIRMED PROFESSIONAL EVIDENCE" in power.summary()


def test_employer_filter():
    result = retrieve_evidence(
        "technical support", VAULT_SNAPSHOT, employer="Concentrix"
    )
    assert result.has_usable_evidence
    for m in result.matched:
        assert "Concentrix" in m.item.employer


def test_rest_apis_json():
    result = retrieve_evidence("REST APIs and JSON", VAULT_SNAPSHOT)
    assert result.has_usable_evidence
    assert any("REST" in m.item.claim for m in result.matched)
    for m in result.matched:
        assert m.item.employer == "FactSet Systems India Pvt. Ltd."


def test_excel_data_validation():
    result = retrieve_evidence(
        "Advanced Excel and data validation", VAULT_SNAPSHOT, include_diagnostic=True
    )
    # Excel is intentionally UNCONFIRMED until employer-specific confirmation exists.
    assert not any(
        "Excel" in m.item.claim and m.item.is_usable_professional for m in result.matched
    )
    excel_excluded = [e for e in result.excluded if "Excel" in e.item.claim]
    assert excel_excluded, "Expected Excel to appear as related but excluded evidence"
    for e in excel_excluded:
        assert e.item.confirmation_status == "Needs-Confirmation"
        assert e.item.professional_status != "Professional-Confirmed"


def test_format_retrieval_smoke():
    result = retrieve_evidence(
        "ServiceNow and incident management", VAULT_SNAPSHOT, include_diagnostic=True
    )
    text = format_retrieval(result)
    assert "JD REQUIREMENT:" in text
    assert "MATCHED EVIDENCE" in text or "RELATED EVIDENCE" in text


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

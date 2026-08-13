from career_os.evidence import EvidenceItem
from career_os.orchestrator import collect_relevant_evidence


def _item(claim: str, *, usable: bool = True) -> EvidenceItem:
    return EvidenceItem(
        claim=claim,
        category="Tool",
        employer="FactSet Systems India Pvt. Ltd.",
        role="Product Support Engineer",
        employment_period="2024-2026",
        professional_status="Professional-Confirmed" if usable else "Unconfirmed",
        usage_level="Frequent",
        context=f"Used {claim} for support work.",
        evidence_source="Career Profile",
        confirmation_status="Confirmed-by-User" if usable else "Needs-Confirmation",
        safe_wording=f"Used {claim} in supported work." if usable else "(Do not use)",
    )


def test_fit_context_can_exclude_unrelated_usable_evidence():
    vault = [_item("ServiceNow"), _item("Oracle"), _item("Python")]
    narrowed = collect_relevant_evidence(["ServiceNow"], vault, include_all_usable=False)
    assert [item.claim for item in narrowed] == ["ServiceNow"]


def test_existing_full_evidence_behavior_remains_default():
    vault = [_item("ServiceNow"), _item("Oracle")]
    full = collect_relevant_evidence(["ServiceNow"], vault)
    assert {item.claim for item in full} == {"ServiceNow", "Oracle"}


def test_retrieval_requirements_drop_noisy_long_responsibility_blob():
    from career_os.jd_analyzer import requirements_for_retrieval
    from career_os.models import JDAnalysis

    noisy = "Responsibilities: " + ("support applications and monitor systems; " * 30)
    analysis = JDAnalysis(
        responsibilities=[noisy],
        mandatory=["ServiceNow"],
        technical_skills=["Technical Support"],
        tools=["ServiceNow"],
    )
    requirements = requirements_for_retrieval(analysis)
    assert noisy not in requirements
    assert "ServiceNow" in requirements
    assert "Technical Support" in requirements

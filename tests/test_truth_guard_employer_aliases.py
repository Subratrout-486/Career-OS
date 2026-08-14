from career_os.evidence import EvidenceItem
from career_os.models import FitReport, TailoredResume
from career_os.truth_guard import validate_resume_truth


def test_shortened_concentrix_label_matches_canonical_evidence():
    resume = TailoredResume(
        title="Technical Support Representative",
        summary="Technical support professional.",
        skills=["CRM"],
        experience=[
            {
                "title": "Technical Support Representative",
                "company": "Concentrix",
                "dates": "Nov 2021 – Oct 2022",
                "bullets": ["Managed CRM and ticketing workflow for customer support cases."],
            }
        ],
        education=[],
        changes=[],
        unsupported_claims=[],
        evidence_trace=[],
    )
    evidence = [
        EvidenceItem(
            claim="CRM / ticketing workflow for support cases",
            category="Process",
            employer="Concentrix (Comcast process)",
            role="Technical Support Representative",
            employment_period="Nov 2021 – Oct 2022",
            professional_status="Professional-Confirmed",
            usage_level="Daily/Core",
            context="Support case workflow.",
            evidence_source="Career Evidence Vault",
            confirmation_status="Confirmed-by-User",
            safe_wording="Created, updated, and closed support cases in CRM/ticketing systems.",
        )
    ]
    fit = FitReport(
        fit_score=70,
        recommendation="APPLY",
        band="B",
        must_have_matches=[],
        gaps=[],
        blockers=[],
        evidence=[],
        keywords=[],
        risks=[],
        rationale="",
        requirement_matches=[],
        confirmation_requests=[],
    )

    issues = validate_resume_truth(
        resume=resume,
        profile="Concentrix Technical Support Representative Nov 2021 – Oct 2022",
        fit=fit,
        evidence_pack=evidence,
    )

    assert not any("no usable professional evidence" in issue for issue in issues)


def test_concentrix_xfinity_display_label_matches_canonical_evidence():
    resume = TailoredResume(
        title="Technical Support Representative",
        summary="Technical support professional.",
        skills=["CRM"],
        experience=[
            {
                "title": "Technical Support Representative",
                "company": "Concentrix (Comcast/Xfinity process)",
                "dates": "Nov 2021 – Oct 2022",
                "bullets": ["Managed CRM and ticketing workflow for customer support cases."],
            }
        ],
        education=[],
        changes=[],
        unsupported_claims=[],
        evidence_trace=[],
    )
    evidence = [
        EvidenceItem(
            claim="CRM / ticketing workflow for support cases",
            category="Process",
            employer="Concentrix (Comcast process)",
            role="Technical Support Representative",
            employment_period="Nov 2021 – Oct 2022",
            professional_status="Professional-Confirmed",
            usage_level="Daily/Core",
            context="Support case workflow.",
            evidence_source="Career Evidence Vault",
            confirmation_status="Confirmed-by-User",
            safe_wording="Created, updated, and closed support cases in CRM/ticketing systems.",
        )
    ]
    fit = FitReport(
        fit_score=70,
        recommendation="APPLY",
        band="B",
        rationale="",
    )

    issues = validate_resume_truth(
        resume=resume,
        profile="Concentrix (Comcast) Technical Support Representative Nov 2021 – Oct 2022",
        fit=fit,
        evidence_pack=evidence,
    )

    assert not any("Experience company is not present" in issue for issue in issues)
    assert not any("no usable professional evidence" in issue for issue in issues)


def test_date_dash_variant_matches_profile_period():
    resume = TailoredResume(
        title="Product Support Engineer",
        summary="Support professional.",
        experience=[
            {
                "title": "Product Support Engineer",
                "company": "FactSet Systems",
                "dates": "Nov 2024 - Jan 2026",
                "bullets": ["Supported Oracle application issues."],
            }
        ],
    )
    evidence = [
        EvidenceItem(
            claim="Oracle / PL/SQL application investigation",
            category="Tool",
            employer="FactSet Systems India Pvt. Ltd.",
            role="Product Support Engineer",
            employment_period="Nov 2024 – Jan 2026",
            professional_status="Professional-Confirmed",
            usage_level="Frequent",
            context="Application support.",
            evidence_source="Career Evidence Vault",
            confirmation_status="Confirmed-by-User",
            safe_wording="Supported Oracle application issues.",
        )
    ]
    issues = validate_resume_truth(
        resume=resume,
        profile="FactSet Systems India Pvt. Ltd. Nov 2024 – Jan 2026",
        fit=FitReport(fit_score=70, recommendation="APPLY", band="B"),
        evidence_pack=evidence,
    )
    assert not any("Experience dates are not present" in issue for issue in issues)


def test_control_character_date_separator_is_normalized_before_truth_guard():
    resume = TailoredResume(
        title="Product Support Engineer",
        summary="Support professional.",
        experience=[
            {
                "title": "Product Support Engineer",
                "company": "FactSet Systems",
                "dates": "Nov 2024 \x131 Jan 2026",
                "bullets": ["Supported Oracle application issues."],
            }
        ],
    )
    assert resume.experience[0].dates == "Nov 2024 - Jan 2026"

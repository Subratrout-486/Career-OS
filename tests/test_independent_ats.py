from career_os.independent_ats import audit_independent_ats
from career_os.models import ExperienceEntry, JDAnalysis, TailoredResume


def test_independent_ats_rewards_keyword_and_section_coverage():
    jd = JDAnalysis(
        technical_skills=["SQL", "REST APIs"],
        tools=["ServiceNow"],
        raw_keywords=["incident management"],
    )
    resume = TailoredResume(
        title="Technical Support Engineer",
        summary="Technical support professional focused on troubleshooting and incident management.",
        skills=["SQL", "REST APIs", "ServiceNow"],
        experience=[
            ExperienceEntry(
                title="Product Support Engineer",
                company="Example Co",
                dates="2024 - 2026",
                bullets=["Resolved customer incidents using SQL and REST APIs."],
            )
        ],
        education=["Bachelor's degree"],
    )

    result = audit_independent_ats(jd=jd, resume=resume)

    assert result.passed is True
    assert result.keyword_coverage == 100
    assert result.section_score == 100
    assert not result.missing_keywords


def test_independent_ats_flags_parser_risk_without_inventing_keywords():
    jd = JDAnalysis(technical_skills=["Python", "SQL"])
    resume = TailoredResume(
        title="Analyst",
        summary="Support analyst\x01",
        skills=["SQL"],
        education=["Bachelor's degree"],
    )

    result = audit_independent_ats(jd=jd, resume=resume)

    assert "Python" in result.missing_keywords
    assert result.parseability_score == 50
    assert any("control characters" in issue for issue in result.issues)

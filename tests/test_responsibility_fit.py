from career_os.responsibility_fit import Evidence, assess_requirement, qualify_job


def test_sql_is_transferable_across_database_implementations():
    result = assess_requirement(
        "PostgreSQL / SQL querying",
        [Evidence("Professional SQL queries and Oracle database troubleshooting at FactSet", employer="FactSet")],
    )
    assert result.status in {"MATCH", "TRANSFERABLE"}


def test_unrelated_specialist_requirement_is_blocker():
    result = assess_requirement(
        "Salesforce Apex development",
        [Evidence("L1/L2 enterprise application support, SQL, ServiceNow", employer="FactSet")],
    )
    assert result.status == "BLOCKER"


def test_responsibilities_are_weighted_more_than_title():
    result = qualify_job(
        responsibilities=[
            "Investigate application incidents and resolve tickets",
            "Use SQL to diagnose production data issues",
            "Document RCA and coordinate with engineering",
        ],
        required_skills=["SQL", "Linux"],
        preferred_skills=["Jira"],
        evidence=[
            Evidence("L1/L2 application support, ServiceNow tickets, RCA and engineering escalation", employer="FactSet"),
            Evidence("SQL queries, Oracle and Unix/Linux troubleshooting", employer="FactSet"),
        ],
        years_required=2,
        years_candidate=2.2,
    )
    assert result.recommendation == "APPLY"
    assert result.responsibilities_score >= 80


def test_years_mismatch_alone_does_not_auto_reject():
    result = qualify_job(
        responsibilities=["Provide application support and troubleshoot incidents"],
        required_skills=["SQL"],
        preferred_skills=["PostgreSQL"],
        evidence=[Evidence("Application support and SQL queries", employer="FactSet")],
        years_required=4,
        years_candidate=2.5,
    )
    assert result.recommendation != "SKIP"


def test_ai_project_evidence_supports_ai_automation_requirement():
    result = assess_requirement(
        "AI automation and prompt engineering",
        [Evidence("Career OS v2 AI-agent workflow automation, prompting and JD-analysis project", kind="project")],
    )
    assert result.status == "TRANSFERABLE"


def test_location_or_education_blocker_overrides_score():
    result = qualify_job(
        responsibilities=["Application support"],
        required_skills=["SQL"],
        preferred_skills=[],
        evidence=[Evidence("Application support and SQL", employer="FactSet")],
        location_eligible=False,
    )
    assert result.recommendation == "SKIP"
    assert "Location is not eligible" in result.blockers

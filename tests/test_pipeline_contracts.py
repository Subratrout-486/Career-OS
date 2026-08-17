from career_os.independent_ats import audit_independent_ats
from career_os.models import (
    IndependentATSAudit,
    Job,
    JDAnalysis,
    PipelineResult,
    TailoredResume,
)


def _job() -> Job:
    return Job(
        title="Business Analyst",
        company="Test Company",
        location="Hyderabad",
        description="Excel, SQL, reporting and stakeholder management.",
    )


def _resume() -> TailoredResume:
    return TailoredResume(
        title="Business Analyst",
        summary="Analyst experienced in reporting and stakeholder support.",
        skills=["Excel", "SQL", "Reporting"],
        experience=[],
        education=["B.Com"],
    )


def test_independent_ats_returns_canonical_pipeline_model() -> None:
    jd = JDAnalysis(
        technical_skills=["Excel", "SQL"],
        raw_keywords=["reporting"],
    )
    audit = audit_independent_ats(jd=jd, resume=_resume(), threshold=60)

    assert isinstance(audit, IndependentATSAudit)
    result = PipelineResult(job=_job(), independent_ats=audit)
    assert result.independent_ats is audit


def test_provider_exhaustion_is_a_valid_structured_pipeline_result() -> None:
    result = PipelineResult(
        job=_job(),
        review_status="AI_PROVIDER_UNAVAILABLE",
        errors=["AI_PROVIDER_UNAVAILABLE: all configured providers failed"],
    )

    payload = result.model_dump()
    assert payload["review_status"] == "AI_PROVIDER_UNAVAILABLE"
    assert payload["errors"]
    assert payload["job"]["title"] == "Business Analyst"

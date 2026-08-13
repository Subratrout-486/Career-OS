from typing import Any, Literal
from pydantic import BaseModel, Field, model_validator


class JobVerificationModel(BaseModel):
    active: bool = True
    status: Literal["ACTIVE", "INACTIVE", "UNKNOWN"] = "UNKNOWN"
    http_status: int | None = None
    title_ok: bool = False
    company_ok: bool = False
    location_ok: bool = False
    description_ok: bool = False
    application_url: str | None = None
    experience_requirement: str | None = None
    education_requirement: str | None = None
    responsibilities_found: bool = False
    notes: list[str] = Field(default_factory=list)


class Job(BaseModel):
    title: str
    company: str
    location: str | None = None
    url: str | None = None
    source: str | None = None
    description: str
    captured_at: str | None = None


class JDAnalysis(BaseModel):
    mandatory: list[str] = Field(default_factory=list)
    preferred: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    technical_skills: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    domain_knowledge: list[str] = Field(default_factory=list)
    soft_skills: list[str] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    experience_requirement: str | None = None
    location_work_model: str | None = None
    screening_requirements: list[str] = Field(default_factory=list)
    raw_keywords: list[str] = Field(default_factory=list)

    def all_requirements(self) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for group in (
            self.mandatory, self.technical_skills, self.tools,
            self.responsibilities, self.domain_knowledge, self.preferred,
            self.education, self.screening_requirements,
        ):
            for item in group:
                key = item.strip().lower()
                if key and key not in seen:
                    seen.add(key)
                    out.append(item.strip())
        return out


class RequirementMatch(BaseModel):
    requirement: str
    status: Literal["MATCHED", "PARTIAL", "MISSING", "UNCONFIRMED"] = "MATCHED"
    employer: str | None = None
    role: str | None = None
    claim: str | None = None
    confirmation_status: str | None = None
    professional_status: str | None = None
    safe_wording: str | None = None
    match_reason: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_string(cls, value):
        # AI providers can occasionally return a concise string despite the
        # requested structured schema. Preserve it as a matched requirement
        # instead of failing the entire application pipeline.
        if isinstance(value, str):
            return {"requirement": value, "status": "MATCHED", "match_reason": value}
        return value


class FitReport(BaseModel):
    fit_score: int = Field(ge=0, le=100)
    recommendation: Literal["APPLY", "APPLY-STRETCH", "REVIEW", "SKIP"]
    band: Literal["A", "B", "C", "D"] | None = None
    must_have_matches: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    rationale: str = ""
    requirement_matches: list[RequirementMatch] = Field(default_factory=list)
    confirmation_requests: list[str] = Field(default_factory=list)


class TailoredResume(BaseModel):
    title: str
    summary: str
    skills: list[str] = Field(default_factory=list)
    experience: list[dict[str, Any]] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    changes: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    evidence_trace: list[str] = Field(default_factory=list)


class ATSAudit(BaseModel):
    score: int = Field(ge=0, le=100)
    method: str = "relevant_jd_keyword_coverage"
    matched: list[str] = Field(default_factory=list)
    partial: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    unsupported_do_not_add: list[str] = Field(default_factory=list)
    notes: str = ""


class PipelineResult(BaseModel):
    job: Job
    job_verification: JobVerificationModel | None = None
    jd_analysis: JDAnalysis | None = None
    fit: FitReport
    resume: TailoredResume | None = None
    ats: ATSAudit | None = None
    challenger_notes: str | None = None
    resume_files: dict[str, str] = Field(default_factory=dict)
    resume_library_page_id: str | None = None
    review_page_id: str | None = None
    application_page_id: str | None = None
    review_status: Literal[
        "READY_FOR_REVIEW", "SKIPPED", "ERROR", "EVIDENCE_VAULT_UNAVAILABLE",
        "RESUME_GENERATION_FAILED", "NOTION_WRITE_FAILED", "CHALLENGER_FAILED",
        "ATS_AUDIT_FAILED", "INACTIVE_JOB",
    ] = "READY_FOR_REVIEW"
    errors: list[str] = Field(default_factory=list)
    evidence_count: int = 0
    usable_evidence_count: int = 0

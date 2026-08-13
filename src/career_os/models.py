from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Job(BaseModel):
    title: str
    company: str
    location: str = ""
    url: str = ""
    source: str = ""
    description: str = ""
    captured_at: str | None = None


class JobVerification(BaseModel):
    active: bool = True
    status: str = "ACTIVE"
    http_status: int | None = None
    title_ok: bool = True
    company_ok: bool = True
    location_ok: bool = True
    description_ok: bool = True
    application_url: str | None = None
    experience_requirement: str | None = None
    education_requirement: str | None = None
    responsibilities_found: bool = False
    notes: list[str] = Field(default_factory=list)


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


class RequirementMatch(BaseModel):
    requirement: str
    status: str
    employer: str | None = None
    role: str | None = None
    claim: str | None = None
    confirmation_status: str | None = None
    professional_status: str | None = None
    safe_wording: str | None = None
    match_reason: str | None = None


class FitReport(BaseModel):
    fit_score: int = 0
    recommendation: str = "REVIEW"
    band: str = "C"
    must_have_matches: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    rationale: str = ""
    requirement_matches: list[RequirementMatch] = Field(default_factory=list)
    confirmation_requests: list[str] = Field(default_factory=list)


class ExperienceEntry(BaseModel):
    title: str
    company: str
    dates: str = ""
    bullets: list[str] = Field(default_factory=list)


class TailoredResume(BaseModel):
    title: str = ""
    summary: str = ""
    skills: list[str] = Field(default_factory=list)
    experience: list[ExperienceEntry] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    changes: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    evidence_trace: list[str] = Field(default_factory=list)


class ATSAudit(BaseModel):
    score: int = 0
    method: str = "relevant_jd_keyword_coverage"
    matched: list[str] = Field(default_factory=list)
    partial: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    unsupported_do_not_add: list[str] = Field(default_factory=list)
    notes: str = ""


class PipelineResult(BaseModel):
    job: Job
    job_verification: JobVerification | None = None
    jd_analysis: JDAnalysis | None = None
    fit: FitReport | None = None
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
        "ATS_AUDIT_FAILED", "INACTIVE_JOB", "AI_CORRECTION_NOT_AVAILABLE",
    ] = "READY_FOR_REVIEW"
    errors: list[str] = Field(default_factory=list)
    evidence_count: int = 0
    usable_evidence_count: int = 0

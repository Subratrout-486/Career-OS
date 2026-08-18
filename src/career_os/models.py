from typing import Any, Literal
import json
import re
from pydantic import BaseModel, Field, field_validator, model_validator


class JobVerificationModel(BaseModel):
    active: bool = True
    status: Literal["ACTIVE", "INACTIVE", "UNKNOWN"] = "UNKNOWN"
    http_status: int | None = None
    title_ok: bool = False
    company_ok: bool = False
    location_ok: bool = False
    description_ok: bool = False
    application_url: str | None = None
    resolved_url: str | None = None
    redirect_chain: list[str] = Field(default_factory=list)
    verification_source: str = "none"
    application_channel: str | None = None
    browser_listing_evidence: bool = False
    experience_requirement: str | None = None
    education_requirement: str | None = None
    responsibilities_found: bool = False
    ghost_job_risk: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class Job(BaseModel):
    title: str
    company: str
    location: str | None = None
    url: str | None = None
    source: str | None = None
    description: str
    captured_at: str | None = None
    source_job_id: str | None = None
    source_url: str | None = None
    discovery_channel: str | None = None
    published_at: str | None = None
    application_method: str | None = None
    source_capture_evidence: str | None = None
    salary_observations: list[dict[str, Any]] = Field(default_factory=list)
    company_normalized: str | None = None
    official_job_url: str | None = None
    job_id: str | None = None
    country: str | None = None
    state: str | None = None
    city: str | None = None
    employment_type: str | None = None
    work_mode: str | None = None
    department: str | None = None
    category: str | None = None
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    last_checked_at: str | None = None
    application_status: str | None = None
    job_status: str | None = None
    source_hash: str | None = None
    content_hash: str | None = None
    dedupe_key: str | None = None
    parser_version: str | None = None
    extraction_timestamp: str | None = None
    apply_url: str | None = None
    jd_status: Literal["complete", "partial", "unavailable", "blocked", "failed"] = "unavailable"
    jd_error: str | None = None
    jd_text: str | None = None
    extracted_skills: list[str] = Field(default_factory=list)
    match_score: int | None = None
    match_explanation: str | None = None
    recommended_resume: str | None = None
    ingestion_status: str = "DISCOVERED"
    ingestion_error: str | None = None
    ready_state: Literal["NEW", "JD_PENDING", "JD_AVAILABLE", "MATCHED", "RESUME_READY", "READY_TO_APPLY", "APPLIED", "REJECTED", "CLOSED", "ERROR"] = "NEW"
    updated_at: str | None = None


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
        """Flatten structured JD fields into a de-duplicated requirement list."""
        seen: set[str] = set()
        out: list[str] = []
        for group in (
            self.mandatory,
            self.preferred,
            self.responsibilities,
            self.technical_skills,
            self.tools,
            self.domain_knowledge,
            self.soft_skills,
            self.education,
            self.screening_requirements,
            self.raw_keywords,
        ):
            for item in group:
                key = item.strip().lower()
                if item and key not in seen:
                    seen.add(key)
                    out.append(item)
        if self.experience_requirement:
            key = self.experience_requirement.strip().lower()
            if key not in seen:
                out.append(self.experience_requirement)
        return out


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

    @model_validator(mode="before")
    @classmethod
    def normalize_structured_lists(cls, values: Any) -> Any:
        """Accept conservative structured provider output without losing blockers."""
        if not isinstance(values, dict):
            return values
        values = dict(values)

        def as_text(item: Any) -> str:
            if isinstance(item, str):
                return item
            if isinstance(item, dict):
                parts = []
                for key in ("requirement", "question", "reason", "details", "evidence"):
                    value = item.get(key)
                    if value is not None and str(value).strip():
                        parts.append(str(value).strip())
                if parts:
                    return ": ".join(parts[:2])
                return json.dumps(item, sort_keys=True, default=str)
            return str(item)

        for field in (
            "must_have_matches",
            "gaps",
            "blockers",
            "evidence",
            "keywords",
            "risks",
            "confirmation_requests",
        ):
            if isinstance(values.get(field), list):
                values[field] = [as_text(item) for item in values[field]]

        matches = values.get("requirement_matches")
        if isinstance(matches, list):
            normalized_matches = []
            for item in matches:
                if isinstance(item, dict):
                    item = dict(item)
                    for key in (
                        "requirement", "status", "employer", "role", "claim",
                        "confirmation_status", "professional_status", "safe_wording", "match_reason",
                    ):
                        value = item.get(key)
                        if isinstance(value, list):
                            item[key] = "; ".join(str(part).strip() for part in value if str(part).strip())
                    if not item.get("requirement"):
                        item["requirement"] = ""
                        item["status"] = "UNCONFIRMED"
                    else:
                        item.setdefault("status", "UNCONFIRMED")
                elif isinstance(item, str):
                    item = {"requirement": "", "status": "UNCONFIRMED", "match_reason": item}
                normalized_matches.append(item)
            values["requirement_matches"] = normalized_matches
        return values


class ExperienceEntry(BaseModel):
    title: str
    company: str
    dates: str = ""
    bullets: list[str] = Field(default_factory=list)

    @field_validator("dates", mode="before")
    @classmethod
    def normalize_dates(cls, value: Any) -> str:
        text = str(value or "")
        text = re.sub(r"[\x00-\x1f\x7f]+\s*(?:1\s*)?(?=[A-Z][a-z]{2}\s+\d{4})", " - ", text)
        text = re.sub(r"[\u2010-\u2015\u2212]", "-", text)
        return re.sub(r"\s+", " ", text).strip()


class TailoredResume(BaseModel):
    title: str = ""
    summary: str = ""
    skills: list[str] = Field(default_factory=list)
    experience: list[ExperienceEntry] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    changes: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    evidence_trace: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_education(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        values = dict(values)
        def normalize_list(name: str, *, structured_keys: tuple[str, ...] = ()) -> None:
            items = values.get(name)
            if not isinstance(items, list):
                return
            normalized: list[Any] = []
            for item in items:
                if isinstance(item, dict):
                    parts: list[str] = []
                    for key in structured_keys:
                        value = item.get(key)
                        if value is not None and str(value).strip():
                            parts.append(str(value).strip())
                    normalized.append(" — ".join(parts) if parts else str(item))
                else:
                    normalized.append(item)
            values[name] = normalized
        normalize_list("education", structured_keys=("degree", "institution", "dates"))
        normalize_list("unsupported_claims", structured_keys=("item", "reason", "details", "claim"))
        normalize_list("evidence_trace", structured_keys=("claim", "employer", "source", "evidence"))
        return values


class ATSAudit(BaseModel):
    score: int = 0
    passed: bool = False
    pass_threshold: int = 60
    method: str = "relevant_jd_keyword_coverage"
    matched: list[str] = Field(default_factory=list)
    partial: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    unsupported_do_not_add: list[str] = Field(default_factory=list)
    notes: str = ""


class IndependentATSAudit(BaseModel):
    """Second ATS signal produced by a separate deterministic scoring model."""
    score: int = 0
    passed: bool = False
    threshold: int = 60
    keyword_coverage: int = 0
    section_score: int = 0
    parseability_score: int = 0
    matched_keywords: list[str] = Field(default_factory=list)
    missing_keywords: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    method: str = "independent_weighted_ats_v1"


class RecruiterReview(BaseModel):
    """Independent reviewer outcome; NOT_RUN is never a pass."""
    status: Literal["PASS", "REVISE", "BLOCKED", "NOT_RUN"] = "NOT_RUN"
    recommendation: Literal["APPLY", "REVIEW", "SKIP"] = "REVIEW"
    provider: str = ""
    notes: str = ""
    warnings: list[str] = Field(default_factory=list)


class ResumeDesignQA(BaseModel):
    """Deterministic checks for the current candidate-facing resume artifacts."""
    passed: bool = False
    issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    method: str = "deterministic_pdf_docx_design_contract_v1"


class SalaryIntelligence(BaseModel):
    market_low_lpa: float | None = None
    market_high_lpa: float | None = None
    recommended_ask_lpa: float | None = None
    stretch_target_lpa: float | None = None
    minimum_discussion_lpa: float | None = None
    confidence: str = "Low"
    researched_at: str | None = None
    method: str = ""
    sources: list[dict[str, Any]] = Field(default_factory=list)
    notes: str = ""


class ApplicationQuestion(BaseModel):
    question: str
    question_type: str = "Other"
    required: bool = False
    ai_draft: str = ""
    user_answer: str = ""
    status: str = "NEEDS_REVIEW"
    evidence: str = ""
    application_id: str = ""


class PipelineResult(BaseModel):
    job: Job
    job_verification: JobVerificationModel | None = None
    jd_analysis: JDAnalysis | None = None
    fit: FitReport | None = None
    resume: TailoredResume | None = None
    ats: ATSAudit | None = None
    independent_ats: IndependentATSAudit | None = None
    recruiter_review: RecruiterReview | None = None
    gemini_diagnostic: dict[str, Any] = Field(default_factory=dict)
    primary_recommendation_provider: str = ""
    primary_recommendation: Literal["APPLY", "REVIEW", "SKIP", "NOT_RUN"] = "NOT_RUN"
    design_qa: ResumeDesignQA | None = None
    salary: SalaryIntelligence | None = None
    application_questions: list[ApplicationQuestion] = Field(default_factory=list)
    challenger_notes: str | None = None
    resume_files: dict[str, str] = Field(default_factory=dict)
    resume_library_page_id: str | None = None
    review_page_id: str | None = None
    application_page_id: str | None = None
    application_channel: str | None = None
    application_url: str | None = None
    final_application_url: str | None = None
    application_destination_verified: bool = False
    truth_guard_passed: bool = False
    application_mode: Literal["AUTO_APPLY", "REVIEW_REQUIRED", "DO_NOT_APPLY"] = "REVIEW_REQUIRED"
    application_mode_reason: str = ""
    application_mode_blockers: list[str] = Field(default_factory=list)
    review_status: Literal[
        "READY_FOR_REVIEW", "SKIPPED", "ERROR", "EVIDENCE_VAULT_UNAVAILABLE",
        "RESUME_GENERATION_FAILED", "NOTION_WRITE_FAILED", "CHALLENGER_FAILED",
        "ATS_AUDIT_FAILED", "INACTIVE_JOB", "AI_CORRECTION_NOT_AVAILABLE",
        "AI_PROVIDER_UNAVAILABLE", "DESIGN_QA_FAILED", "RECRUITER_REVIEW_UNAVAILABLE",
        "MANIFEST_GENERATION_FAILED",
    ] = "READY_FOR_REVIEW"
    errors: list[str] = Field(default_factory=list)
    evidence_count: int = 0
    usable_evidence_count: int = 0

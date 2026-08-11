from typing import Literal
from pydantic import BaseModel, Field


class Job(BaseModel):
    title: str
    company: str
    location: str | None = None
    url: str | None = None
    source: str | None = None
    description: str


class FitReport(BaseModel):
    fit_score: int = Field(ge=0, le=100)
    recommendation: Literal["APPLY", "REVIEW", "SKIP"]
    must_have_matches: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    rationale: str


class TailoredResume(BaseModel):
    title: str
    summary: str
    skills: list[str] = Field(default_factory=list)
    experience: list[dict] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    changes: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)


class PipelineResult(BaseModel):
    job: Job
    fit: FitReport
    resume: TailoredResume | None = None
    challenger_notes: str | None = None
    review_status: Literal["READY_FOR_REVIEW", "SKIPPED", "ERROR"]

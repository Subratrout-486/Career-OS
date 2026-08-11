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
    must_have_matches: list[str] = []
    gaps: list[str] = []
    blockers: list[str] = []
    evidence: list[str] = []
    keywords: list[str] = []
    risks: list[str] = []
    rationale: str

class TailoredResume(BaseModel):
    title: str
    summary: str
    skills: list[str]
    experience: list[dict]
    education: list[str]
    changes: list[str]
    unsupported_claims: list[str] = []

class PipelineResult(BaseModel):
    job: Job
    fit: FitReport
    resume: TailoredResume | None = None
    challenger_notes: str | None = None
    review_status: Literal["READY_FOR_REVIEW", "SKIPPED", "ERROR"]

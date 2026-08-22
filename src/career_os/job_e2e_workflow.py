"""Deterministic job-processing workflow for the internal Career OS runtime.

This module defines the orchestration contract only. Specialist executors are
resolved through the existing Agent Hub; no external orchestration service is
required. The workflow is intentionally submission-safe: browser preparation
may occur only after all deterministic gates pass, and submission is always an
explicit approval action.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class JobStage(StrEnum):
    DISCOVER = "discover"
    VERIFY = "verify"
    ANALYZE_JD = "analyze_jd"
    RETRIEVE_EVIDENCE = "retrieve_evidence"
    SCORE_FIT = "score_fit"
    TAILOR_RESUME = "tailor_resume"
    VALIDATE_RESUME = "validate_resume"
    AUDIT_ATS = "audit_ats"
    INDEPENDENT_REVIEW = "independent_review"
    PREPARE_APPLICATION = "prepare_application"
    REVIEW_REQUIRED = "review_required"
    READY_TO_APPLY = "ready_to_apply"


@dataclass(frozen=True)
class StageSpec:
    stage: JobStage
    command: str
    requires: tuple[JobStage, ...] = ()
    approval_required: bool = False


WORKFLOW: tuple[StageSpec, ...] = (
    StageSpec(JobStage.DISCOVER, "find_jobs"),
    StageSpec(JobStage.VERIFY, "verify_job", (JobStage.DISCOVER,)),
    StageSpec(JobStage.ANALYZE_JD, "analyze_jd", (JobStage.VERIFY,)),
    StageSpec(JobStage.RETRIEVE_EVIDENCE, "retrieve_evidence", (JobStage.ANALYZE_JD,)),
    StageSpec(JobStage.SCORE_FIT, "score_fit", (JobStage.RETRIEVE_EVIDENCE,)),
    StageSpec(JobStage.TAILOR_RESUME, "tailor_resume", (JobStage.SCORE_FIT,)),
    StageSpec(JobStage.VALIDATE_RESUME, "validate_resume", (JobStage.TAILOR_RESUME,)),
    StageSpec(JobStage.AUDIT_ATS, "audit_ats", (JobStage.VALIDATE_RESUME,)),
    StageSpec(JobStage.INDEPENDENT_REVIEW, "review_package", (JobStage.AUDIT_ATS,)),
    StageSpec(JobStage.PREPARE_APPLICATION, "prepare_application", (JobStage.INDEPENDENT_REVIEW,)),
    StageSpec(JobStage.REVIEW_REQUIRED, "prepare_application", (JobStage.PREPARE_APPLICATION,), True),
)


class JobWorkflowError(RuntimeError):
    pass


def validate_stage_transition(completed: set[JobStage], target: JobStage) -> None:
    """Fail closed if a workflow tries to skip a prerequisite."""
    spec = next((item for item in WORKFLOW if item.stage == target), None)
    if spec is None:
        raise JobWorkflowError(f"Unknown workflow stage: {target}")
    missing = [stage.value for stage in spec.requires if stage not in completed]
    if missing:
        raise JobWorkflowError(f"Cannot enter {target.value}; missing prerequisites: {missing}")


def workflow_plan() -> list[dict[str, Any]]:
    return [
        {
            "stage": item.stage.value,
            "command": item.command,
            "requires": [stage.value for stage in item.requires],
            "approval_required": item.approval_required,
        }
        for item in WORKFLOW
    ]

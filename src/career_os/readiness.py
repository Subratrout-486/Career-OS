"""Deterministic application-readiness state for Career OS jobs."""
from __future__ import annotations

from typing import Any

READY_STATES = {
    "NEW", "JD_PENDING", "JD_AVAILABLE", "MATCHED", "RESUME_READY",
    "READY_TO_APPLY", "APPLIED", "REJECTED", "CLOSED", "ERROR",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def evaluate_readiness(job: dict[str, Any], result: dict[str, Any] | None = None) -> tuple[str, list[str]]:
    """Return the highest valid state and explicit blockers, never infer missing evidence."""
    result = result or {}
    jd_status = _text(job.get("jd_status")).lower()
    jd_text = _text(job.get("jd_text") or job.get("description"))
    fit = result.get("fit") or {}
    resume = result.get("resume") or {}
    errors = list(result.get("errors") or []) + ([_text(job.get("ingestion_error"))] if _text(job.get("ingestion_error")) else [])
    blockers: list[str] = []
    if not _text(job.get("company")):
        blockers.append("company is missing")
    if not _text(job.get("title")):
        blockers.append("title is missing")
    if not _text(job.get("source_url") or job.get("apply_url") or job.get("url")):
        blockers.append("source/apply URL is missing")
    if jd_status in {"blocked", "failed", "unavailable"} or not jd_text:
        blockers.append(f"usable JD is unavailable (status={jd_status or 'unknown'})")
    elif jd_status not in {"complete", "partial"}:
        blockers.append("JD status is not usable")
    score = fit.get("fit_score", job.get("match_score"))
    if score is None:
        blockers.append("candidate-job matching has not completed")
    if not resume:
        blockers.append("recommended resume is missing")
    if errors:
        blockers.append("critical ingestion or pipeline errors remain")
    if blockers:
        if not jd_text or jd_status in {"blocked", "failed", "unavailable"}:
            return "JD_PENDING", blockers
        if score is None:
            return "JD_AVAILABLE", blockers
        if not resume:
            return "MATCHED", blockers
        return "RESUME_READY", blockers
    return "READY_TO_APPLY", []


def apply_readiness_to_job(job: dict[str, Any], result: dict[str, Any] | None = None) -> dict[str, Any]:
    state, blockers = evaluate_readiness(job, result)
    updated = dict(job)
    updated["ready_state"] = state
    updated["readiness_blockers"] = blockers
    updated["match_score"] = (result or {}).get("fit", {}).get("fit_score", updated.get("match_score"))
    updated["match_explanation"] = (result or {}).get("fit", {}).get("rationale", updated.get("match_explanation"))
    resume = (result or {}).get("resume") or {}
    updated["recommended_resume"] = updated.get("recommended_resume") or resume.get("title")
    return updated

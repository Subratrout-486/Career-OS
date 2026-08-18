"""Deterministic application-readiness state for Career OS jobs."""
from __future__ import annotations
from typing import Any

READY_STATES = {
    "NEW", "JD_PENDING", "JD_AVAILABLE", "MATCHED", "RESUME_READY",
    "READY_TO_APPLY", "APPLIED", "REJECTED", "CLOSED", "ERROR",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _nested(result: dict[str, Any], key: str) -> dict[str, Any]:
    value = result.get(key) or {}
    return value if isinstance(value, dict) else {}


def evaluate_readiness(job: dict[str, Any], result: dict[str, Any] | None = None) -> tuple[str, list[str]]:
    """Return the highest valid state and explicit blockers.

    READY_TO_APPLY is deliberately conservative. A source URL is discovery
    provenance only; it can never substitute for a verified application URL.
    """
    result = result or {}
    jd_status = _text(job.get("jd_status")).lower()
    jd_text = _text(job.get("jd_text") or job.get("description"))
    fit = _nested(result, "fit")
    resume = _nested(result, "resume")
    verification = _nested(result, "job_verification")
    ats = _nested(result, "ats")
    independent_ats = _nested(result, "independent_ats")
    recruiter_review = _nested(result, "recruiter_review")
    errors = list(result.get("errors") or []) + ([_text(job.get("ingestion_error"))] if _text(job.get("ingestion_error")) else [])
    blockers: list[str] = []

    if not _text(job.get("company")):
        blockers.append("company is missing")
    if not _text(job.get("title")):
        blockers.append("title is missing")
    if not _text(job.get("source_url") or job.get("url")):
        blockers.append("source URL is missing")

    application_url = _text(result.get("application_url") or verification.get("application_url") or job.get("apply_url"))
    application_url_verified = bool(
        result.get("application_destination_verified")
        or result.get("application_url_verified")
        or verification.get("application_url_verified")
    )
    if not application_url or not application_url_verified:
        blockers.append("verified application URL is missing")

    if jd_status in {"blocked", "failed", "unavailable"} or not jd_text:
        blockers.append(f"usable JD is unavailable (status={jd_status or 'unknown'})")
    elif jd_status not in {"complete", "partial"}:
        blockers.append("JD status is not usable")

    score = fit.get("fit_score", job.get("match_score"))
    if score is None or not _text(fit.get("rationale")):
        blockers.append("successful fit analysis is missing")
    if not _text(resume.get("title") or job.get("recommended_resume")):
        blockers.append("recommended resume is missing")
    if result.get("truth_guard_passed") is not True:
        blockers.append("Truth Guard pass is missing")
    if ats.get("passed") is not True:
        blockers.append("required ATS validation has not passed")
    if independent_ats.get("passed") is not True:
        blockers.append("independent ATS validation has not passed")
    if recruiter_review and recruiter_review.get("status") not in {"PASS", "NOT_REQUIRED"}:
        blockers.append("independent review has not passed")
    if not result.get("evidence_count") or not result.get("usable_evidence_count"):
        blockers.append("required evidence/provenance is missing")
    if errors:
        blockers.append("critical ingestion or pipeline errors remain")

    if blockers:
        if not jd_text or jd_status in {"blocked", "failed", "unavailable"}:
            return "JD_PENDING", blockers
        if score is None:
            return "JD_AVAILABLE", blockers
        if not _text(resume.get("title") or job.get("recommended_resume")):
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

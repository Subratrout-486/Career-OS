"""Fail-closed ghost-job risk assessment for Career OS postings.

A reachable URL alone is not enough to support autonomous submission.  This
module converts the existing, deterministic posting-verification facts into a
small audit trail.  It intentionally returns ``REVIEW`` whenever a signal is
missing, unverifiable, stale, or inconsistent.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GhostJobRiskAssessment:
    level: str
    acceptable: bool
    reasons: tuple[str, ...]
    method: str = "deterministic_employer_posting_risk_v1"

    def as_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "acceptable": self.acceptable,
            "reasons": list(self.reasons),
            "method": self.method,
        }


def assess_ghost_job_risk(
    verification: dict[str, Any],
    *,
    source: str | None = None,
) -> GhostJobRiskAssessment:
    """Assess whether the current posting evidence is sufficient for AUTO_APPLY.

    The result is deliberately not a probability.  ``ACCEPTABLE`` means every
    deterministic freshness/identity signal below was supplied; it does *not*
    claim that an employer will respond.  Anything else remains ``REVIEW``.
    """
    reasons: list[str] = []
    if verification.get("status") != "ACTIVE" or verification.get("active") is not True:
        reasons.append("posting is not explicitly ACTIVE")
    http_status = verification.get("http_status")
    browser_verified = (
        verification.get("verification_source") == "authenticated_browser"
        and verification.get("browser_listing_evidence") is True
    )
    if not browser_verified and (not isinstance(http_status, int) or not 200 <= http_status < 400):
        reasons.append("employer posting did not return a successful HTTP response")
    for field, label in (
        ("title_ok", "title"),
        ("company_ok", "company"),
        ("location_ok", "location"),
        ("description_ok", "description"),
        ("responsibilities_found", "responsibilities"),
    ):
        if verification.get(field) is not True:
            reasons.append(f"posting {label} evidence is incomplete")
    if not str(verification.get("application_url") or "").strip():
        reasons.append("application URL is missing")
    source_value = str(source or "").strip().lower()
    channel_value = str(verification.get("application_channel") or "").strip().lower()
    browser_destination_ok = browser_verified and (
        "employer" in channel_value
        or "career site" in channel_value
        or "ats" in channel_value
        or "easy apply" in channel_value
    )
    if source_value and "employer" not in source_value and "ats" not in source_value and not browser_destination_ok:
        reasons.append("posting source is not identified as an employer/ATS source")

    if reasons:
        return GhostJobRiskAssessment("REVIEW", False, tuple(dict.fromkeys(reasons)))
    return GhostJobRiskAssessment(
        "ACCEPTABLE",
        True,
        ("active employer/ATS posting verified with complete identity and role evidence",),
    )

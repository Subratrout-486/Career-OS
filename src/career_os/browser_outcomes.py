"""Conservative reconciliation of Career OS browser-executor outcomes.

A browser task is not an application.  This module accepts only a structured
executor outcome and permits an ``Applied`` state only when the executor records
an actual employer, ATS, or LinkedIn confirmation along with proof that the
exact tailored resume was attached.  Any other result stays in review.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BrowserOutcomeDecision:
    """The single safe status transition for one browser execution outcome."""

    application_status: str
    next_action: str
    evidence: str
    blockers: tuple[str, ...]


_ALLOWED_CONFIRMATION_SOURCES = {"employer", "ats", "linkedin"}


def decide_browser_outcome(outcome: dict[str, Any]) -> BrowserOutcomeDecision:
    """Convert a structured browser result to a fail-closed Notion transition.

    Only ``status=SUBMITTED``, ``submitted=true``, evidence from an independent
    employer/ATS/LinkedIn confirmation surface, exact resume attachment/hash
    proof, and no blockers can yield ``Applied``.  A Manus task completing, a
    page navigation, or an upload without confirmation is deliberately
    insufficient.
    """
    status = str(outcome.get("status") or "ERROR").strip().upper()
    submitted = outcome.get("submitted") is True
    evidence = str(outcome.get("confirmation_evidence") or "").strip()
    confirmation_url = str(outcome.get("confirmation_url") or "").strip()
    source = str(outcome.get("confirmation_source") or "").strip().lower()
    attachment_verified = outcome.get("resume_attachment_verified") is True
    hash_verified = outcome.get("resume_sha256_verified") is True
    raw_blockers = outcome.get("blockers") or []
    blockers = [str(item).strip() for item in raw_blockers if str(item).strip()]

    if (
        status == "SUBMITTED"
        and submitted
        and source in _ALLOWED_CONFIRMATION_SOURCES
        and evidence
        and confirmation_url
        and attachment_verified
        and hash_verified
        and not blockers
    ):
        return BrowserOutcomeDecision(
            application_status="Applied",
            next_action="Submission confirmed by an employer, ATS, or LinkedIn confirmation surface. No further submission action is required.",
            evidence=evidence,
            blockers=(),
        )

    reasons: list[str] = []
    if status != "SUBMITTED":
        reasons.append(f"browser outcome status={status}")
    if not submitted:
        reasons.append("browser executor did not confirm submission")
    if source not in _ALLOWED_CONFIRMATION_SOURCES:
        reasons.append("independent employer/ATS/LinkedIn confirmation source is missing")
    if not evidence:
        reasons.append("employer/ATS/LinkedIn confirmation evidence is missing")
    if not confirmation_url:
        reasons.append("employer/ATS/LinkedIn confirmation URL is missing")
    if not attachment_verified:
        reasons.append("exact tailored-resume attachment was not verified")
    if not hash_verified:
        reasons.append("exact tailored-resume SHA-256 was not verified")
    reasons.extend(blockers)
    deduped = tuple(dict.fromkeys(reasons))
    return BrowserOutcomeDecision(
        application_status="Review",
        next_action="Browser execution requires review; do not mark Applied or resubmit automatically.",
        evidence=evidence,
        blockers=deduped,
    )

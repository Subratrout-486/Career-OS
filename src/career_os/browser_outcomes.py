"""Conservative reconciliation of Career OS browser-executor outcomes.

A browser task is not an application.  This module accepts only a structured
executor outcome and permits an ``Applied`` state only when the executor states
that it submitted the form and records specific employer/ATS confirmation
evidence.  Any other result stays in a review state with a visible next action.
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


def decide_browser_outcome(outcome: dict[str, Any]) -> BrowserOutcomeDecision:
    """Convert a structured browser result to a fail-closed Notion transition.

    Only ``status=SUBMITTED``, ``submitted=true``, no blockers, and a non-empty
    confirmation string can yield ``Applied``.  A resume upload, task creation,
    or a merely successful browser navigation is deliberately insufficient.
    """
    status = str(outcome.get("status") or "ERROR").strip().upper()
    submitted = outcome.get("submitted") is True
    evidence = str(outcome.get("confirmation_evidence") or "").strip()
    raw_blockers = outcome.get("blockers") or []
    blockers = tuple(str(item).strip() for item in raw_blockers if str(item).strip())

    if status == "SUBMITTED" and submitted and evidence and not blockers:
        return BrowserOutcomeDecision(
            application_status="Applied",
            next_action="Submission verified by the browser executor. No further submission action is required.",
            evidence=evidence,
            blockers=(),
        )

    reasons: list[str] = []
    if status != "SUBMITTED":
        reasons.append(f"browser outcome status={status}")
    if not submitted:
        reasons.append("browser executor did not confirm submission")
    if not evidence:
        reasons.append("employer/ATS confirmation evidence is missing")
    reasons.extend(blockers)
    deduped = tuple(dict.fromkeys(reasons))
    return BrowserOutcomeDecision(
        application_status="Review",
        next_action="Browser execution requires review; do not mark Applied or resubmit automatically.",
        evidence=evidence,
        blockers=deduped,
    )

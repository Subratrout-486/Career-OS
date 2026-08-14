"""Conservative structured interpretation of an independent recruiter review."""
from __future__ import annotations

import re

from .models import RecruiterReview


def classify_recruiter_review(notes: str | None, provider: str | None) -> RecruiterReview:
    """Classify explicit reviewer output without inferring approval.

    The reviewer prompt requires a ``VERDICT`` section. Only an unambiguous
    ``VERDICT: PASS`` is considered a pass. Missing, unavailable, or malformed
    output is a visible non-passing state that keeps browser execution gated.
    """
    text = (notes or "").strip()
    provider_name = (provider or "").strip()
    if not text or text.startswith("INDEPENDENT CHALLENGER NOT RUN"):
        return RecruiterReview(
            status="NOT_RUN",
            recommendation="REVIEW",
            provider=provider_name,
            notes=text,
            warnings=["Independent recruiter review was unavailable and is not approval."],
        )

    match = re.search(r"(?im)^\s*VERDICT\s*:\s*([^\n]+)", text)
    verdict = (match.group(1) if match else "").upper()
    if re.search(r"\bPASS\b", verdict) and not re.search(r"\b(REVISE|BLOCK|FAIL|REJECT)\b", verdict):
        status = "PASS"
    elif re.search(r"\b(BLOCK|REJECT|FAIL)\b", verdict):
        status = "BLOCKED"
    else:
        status = "REVISE"

    recommendation = "APPLY" if status == "PASS" and provider_name.lower().startswith("gemini") else ("SKIP" if status == "BLOCKED" else "REVIEW")
    warnings: list[str] = []
    if not match:
        warnings.append("Reviewer output omitted an explicit VERDICT; treated as REVISE.")
    if not provider_name.lower().startswith("gemini"):
        warnings.append("Independent reviewer provenance is not Gemini; treated as non-applying review.")
    return RecruiterReview(status=status, recommendation=recommendation, provider=provider_name, notes=text, warnings=warnings)

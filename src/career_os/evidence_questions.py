"""Generate structured user-confirmation questions for JD gaps.

This module deliberately treats a missing resume mention as UNKNOWN, not NO.
Only explicit user confirmation can promote a requirement into professional evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Status = Literal["CANONICAL_RESUME", "CONFIRMED_EVIDENCE", "UNCONFIRMED", "REJECTED", "SELF_DIRECTED", "KNOWLEDGE_ONLY", "INFERRED"]


@dataclass(frozen=True)
class ConfirmationQuestion:
    requirement: str
    employer_hint: str | None
    question: str
    fields: tuple[str, ...]


def classify_requirement(*, in_canonical_resume: bool, evidence_status: str | None) -> Status:
    """Classify a JD requirement without inferring professional use."""
    if in_canonical_resume:
        return "CANONICAL_RESUME"
    if evidence_status == "CONFIRMED":
        return "CONFIRMED_EVIDENCE"
    if evidence_status == "REJECTED":
        return "REJECTED"
    if evidence_status == "SELF_DIRECTED":
        return "SELF_DIRECTED"
    if evidence_status == "KNOWLEDGE_ONLY":
        return "KNOWLEDGE_ONLY"
    if evidence_status == "INFERRED":
        return "INFERRED"
    return "UNCONFIRMED"


def build_confirmation_question(requirement: str, *, employer_hint: str | None = None) -> ConfirmationQuestion:
    """Build the standard evidence-intake question for a missing JD requirement."""
    employer = employer_hint or "any employer"
    question = (
        f"The JD requires **{requirement}**, but it is not in the canonical resume or confirmed evidence. "
        f"Did you use/do **{requirement}** professionally at {employer}? "
        "If yes, tell me the employer/role, period, how you used it, the business/technical context, "
        "what you personally did, and any wording that is safe to put on your resume."
    )
    return ConfirmationQuestion(
        requirement=requirement,
        employer_hint=employer_hint,
        question=question,
        fields=("professional_use", "employer", "role", "employment_period", "how_used", "context", "personal_actions", "safe_wording", "unsafe_wording"),
    )


def should_ask(*, status: Status) -> bool:
    """Return True only for unknown evidence."""
    return status == "UNCONFIRMED"

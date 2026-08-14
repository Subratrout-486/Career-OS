"""Approval-gated recruiter/referral outreach primitives."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class OutreachStatus(StrEnum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    SENT = "SENT"
    REPLIED = "REPLIED"
    FOLLOW_UP_DUE = "FOLLOW_UP_DUE"
    CLOSED = "CLOSED"


@dataclass(frozen=True)
class RecruiterContact:
    name: str
    company: str
    email: str | None = None
    linkedin_url: str | None = None
    source: str = "user_or_approved_source"


@dataclass(frozen=True)
class OutreachDraft:
    recruiter: RecruiterContact
    job_title: str
    job_url: str
    resume_artifact_id: str
    subject: str
    body: str
    status: OutreachStatus = OutreachStatus.DRAFT


def draft_referral_email(
    recruiter: RecruiterContact,
    job_title: str,
    job_url: str,
    resume_artifact_id: str,
    candidate_name: str,
    fit_reason: str,
) -> OutreachDraft:
    """Create a concise, truthful referral request; sending is never automatic here."""
    first_name = recruiter.name.strip().split()[0] if recruiter.name.strip() else "there"
    subject = f"Referral request — {job_title}"
    body = (
        f"Hi {first_name},\n\n"
        f"I’m {candidate_name}, and I’m interested in the {job_title} opportunity. "
        f"{fit_reason.strip()}\n\n"
        f"If you think my background could be a fit, I’d really appreciate a referral "
        f"or guidance on the appropriate application path. My resume is prepared for "
        f"this role.\n\n"
        f"Job: {job_url}\n\n"
        "Thank you for your time,\n"
        f"{candidate_name}"
    )
    return OutreachDraft(recruiter, job_title, job_url, resume_artifact_id, subject, body)


def approve_outreach(draft: OutreachDraft) -> OutreachDraft:
    """Explicit human approval transition. No transport/network side effects."""
    if draft.status is not OutreachStatus.DRAFT:
        raise ValueError("Only DRAFT outreach can be approved")
    return OutreachDraft(**{**draft.__dict__, "status": OutreachStatus.APPROVED})

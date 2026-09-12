"""Email-to-job intake normalization.

Adapters may pass sanitized email metadata/body here. This module does not
send mail, read a mailbox, or bypass authentication; a connector supplies the
message content and the existing Career OS pipeline decides what happens next.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from email.utils import parseaddr

from .job_intelligence import JobRecord


_URL_RE = re.compile(r"https?://[^\s<>\"]+", re.I)
_REQ_RE = re.compile(r"(?:req(?:uisition)?|job\s*id)\s*[:#-]?\s*([A-Za-z0-9_-]{3,})", re.I)


@dataclass(frozen=True)
class EmailJobMessage:
    message_id: str
    sender: str
    subject: str
    body: str
    received_at: str | None = None


def extract_job_urls(text: str) -> tuple[str, ...]:
    urls = []
    for match in _URL_RE.findall(text):
        url = match.rstrip(".,);]>")
        if url not in urls:
            urls.append(url)
    return tuple(urls)


def extract_requisition_id(text: str) -> str | None:
    match = _REQ_RE.search(text)
    return match.group(1) if match else None


def message_to_job(message: EmailJobMessage, company: str | None = None) -> JobRecord | None:
    """Convert a job-alert email to an intake record when a URL exists."""
    urls = extract_job_urls(f"{message.subject}\n{message.body}")
    if not urls:
        return None
    sender_name, sender_email = parseaddr(message.sender)
    subject = message.subject.strip() or "Job opportunity"
    inferred_company = company or sender_name or sender_email.split("@")[-1].split(".")[0]
    return JobRecord(
        company=inferred_company,
        title=subject,
        location="Unknown",
        url=urls[0],
        source="email",
        requisition_id=extract_requisition_id(message.body),
        description=message.body,
        posted_at=message.received_at,
        metadata={"message_id": message.message_id, "sender": sender_email},
    )

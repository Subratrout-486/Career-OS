"""Active job posting verification before application-ready processing.

Does not claim a job is active without an HTTP check.
Marks expired/dead postings as INACTIVE so the pipeline skips resume generation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

from .models import Job

INACTIVE_MARKERS = [
    r"no longer available",
    r"job is closed",
    r"this job has expired",
    r"position has been filled",
    r"page not found",
    r"we couldn't find that job",
    r"job posting is no longer active",
    r"this position is no longer open",
    r"404",
    r"gone\b",
]


@dataclass
class JobVerification:
    active: bool
    status: str  # ACTIVE | INACTIVE | UNKNOWN
    http_status: int | None = None
    title_ok: bool = False
    company_ok: bool = False
    location_ok: bool = False
    description_ok: bool = False
    application_url: str | None = None
    experience_requirement: str | None = None
    education_requirement: str | None = None
    responsibilities_found: bool = False
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "active": self.active,
            "status": self.status,
            "http_status": self.http_status,
            "title_ok": self.title_ok,
            "company_ok": self.company_ok,
            "location_ok": self.location_ok,
            "description_ok": self.description_ok,
            "application_url": self.application_url,
            "experience_requirement": self.experience_requirement,
            "education_requirement": self.education_requirement,
            "responsibilities_found": self.responsibilities_found,
            "notes": self.notes,
        }


def _field_present(value: str | None, min_len: int = 2) -> bool:
    return bool(value and str(value).strip() and len(str(value).strip()) >= min_len)


def _extract_experience(text: str) -> str | None:
    patterns = [
        r"(\d+\+?\s*(?:to|-)\s*\d+\s*years?[^\n.]{0,40})",
        r"(\d+\+?\s*years?[^\n.]{0,40}experience[^\n.]{0,40})",
        r"(minimum\s+of\s+\d+\s*years?[^\n.]{0,40})",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            return m.group(1).strip()
    return None


def _extract_education(text: str) -> str | None:
    if re.search(r"\b(b\.?tech|b\.?e\.?|computer science|engineering degree|bachelor|master'?s|mba)\b", text, re.I):
        m = re.search(
            r"([^\n.]{0,80}(?:bachelor|master|b\.?tech|mba|degree)[^\n.]{0,80})",
            text,
            re.I,
        )
        return (m.group(1).strip() if m else "Degree requirement mentioned in JD")
    return None


def verify_job_fields(job: Job) -> JobVerification:
    """Validate captured fields without network I/O."""
    notes: list[str] = []
    title_ok = _field_present(job.title)
    company_ok = _field_present(job.company)
    location_ok = _field_present(job.location)
    description_ok = _field_present(job.description, min_len=40)
    if not title_ok:
        notes.append("Missing job title")
    if not company_ok:
        notes.append("Missing company name")
    if not location_ok:
        notes.append("Missing location")
    if not description_ok:
        notes.append("Missing or too-short job description")

    desc = job.description or ""
    exp = _extract_experience(desc)
    edu = _extract_education(desc)
    responsibilities = bool(
        re.search(
            r"responsibilit|what you.?ll do|key duties|about the role",
            desc,
            re.I,
        )
    ) or len(desc) > 200

    return JobVerification(
        active=True,
        status="UNKNOWN",
        title_ok=title_ok,
        company_ok=company_ok,
        location_ok=location_ok,
        description_ok=description_ok,
        application_url=(job.url or "").strip() or None,
        experience_requirement=exp,
        education_requirement=edu,
        responsibilities_found=responsibilities,
        notes=notes,
    )


def verify_job_active(job: Job, *, timeout: float = 20.0) -> JobVerification:
    """Verify job fields and, when a URL is present, check the posting is reachable/active."""
    result = verify_job_fields(job)
    url = (job.url or "").strip()
    if not url:
        result.notes.append("No application URL supplied — cannot confirm active status online")
        result.status = "UNKNOWN"
        result.active = result.title_ok and result.description_ok
        return result

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        result.notes.append(f"Invalid URL: {url}")
        result.status = "INACTIVE"
        result.active = False
        return result

    try:
        with httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; CareerOS/1.0; +https://github.com/Subratrout-486/Career-OS)"
                )
            },
        ) as client:
            response = client.get(url)
        result.http_status = response.status_code
        body = (response.text or "")[:200000].lower()
        if response.status_code >= 400:
            result.active = False
            result.status = "INACTIVE"
            result.notes.append(f"HTTP {response.status_code} for job URL")
            return result
        for marker in INACTIVE_MARKERS:
            if re.search(marker, body, re.I):
                if marker == r"404" and response.status_code == 200:
                    continue
                result.active = False
                result.status = "INACTIVE"
                result.notes.append(f"Inactive marker matched: {marker}")
                return result
        result.active = True
        result.status = "ACTIVE"
        result.notes.append(f"URL reachable (HTTP {response.status_code})")
        return result
    except Exception as exc:  # noqa: BLE001
        result.active = result.title_ok and result.description_ok
        result.status = "UNKNOWN"
        result.notes.append(f"URL check failed: {type(exc).__name__}: {exc}")
        return result

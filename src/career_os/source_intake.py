"""Authorized job-source intake for Career OS.

Jobright and Simplify provide user-facing browser-extension workflows.  This
module deliberately does not scrape authenticated accounts or invent a public
API.  It normalizes user-authorized exports or browser captures into the same
job contract as public employer ATS records, preserving source provenance and
centralizing deduplication before any application workflow begins.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


SUPPORTED_SOURCES = {"jobright", "simplify", "employer_ats"}
_SOURCE_LABELS = {
    "jobright": "Jobright — authorized browser capture",
    "simplify": "Simplify — authorized browser capture",
    "employer_ats": "Employer ATS — public feed",
}
_TRACKING_QUERY_KEYS = {
    "ref", "referrer", "source", "src", "utm_source", "utm_medium", "utm_campaign",
    "utm_term", "utm_content", "trk", "trackingid", "gh_src", "gh_jid",
}


class SourceIntakeError(ValueError):
    """Raised when an import is unsupported, incomplete, or unsafe to normalize."""


def source_capability(source: str) -> dict[str, Any]:
    """Describe the supported Career OS connection method for a job source."""
    key = str(source or "").strip().lower()
    if key not in SUPPORTED_SOURCES:
        raise SourceIntakeError(f"Unsupported job source: {source}")
    if key in {"jobright", "simplify"}:
        return {
            "source": key,
            "public_api_supported": False,
            "supported_intake": ("authorized_json_export", "authorized_browser_capture"),
            "account_access_required": True,
            "application_execution": "supervised browser extension only",
            "status": "ACCESS_REQUIRED",
        }
    return {
        "source": key,
        "public_api_supported": True,
        "supported_intake": ("public_ats_feed", "authorized_json_export"),
        "account_access_required": False,
        "application_execution": "direct employer application page",
        "status": "SUPPORTED",
    }


def _clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def canonicalize_url(value: object) -> str:
    """Drop common tracking parameters but preserve the applicant destination."""
    raw = _clean_text(value)
    if not raw:
        return ""
    parsed = urlsplit(raw)
    query = urlencode([(key, item) for key, item in parse_qsl(parsed.query, keep_blank_values=True) if key.lower() not in _TRACKING_QUERY_KEYS])
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), query, ""))


def job_fingerprint(job: Mapping[str, Any]) -> str:
    """Create a stable cross-source duplicate key from application identity."""
    url = canonicalize_url(job.get("url") or job.get("application_url"))
    identity = "|".join(
        _clean_text(part).casefold()
        for part in (job.get("company"), job.get("title"), job.get("location"), url)
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _first(payload: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if _clean_text(value):
            return _clean_text(value)
    return ""


def normalize_source_job(
    payload: Mapping[str, Any], *, source: str, intake_method: str, captured_at: str | None = None
) -> dict[str, Any]:
    """Normalize one authorized record without adding claims or application data."""
    capability = source_capability(source)
    method = str(intake_method or "").strip().lower()
    if method not in capability["supported_intake"]:
        raise SourceIntakeError(
            f"{source} does not support intake method {intake_method!r}; supported methods are {', '.join(capability['supported_intake'])}"
        )
    title = _first(payload, "title", "job_title", "role")
    company = _first(payload, "company", "company_name", "employer")
    url = canonicalize_url(_first(payload, "url", "application_url", "apply_url", "job_url"))
    description = _first(payload, "description", "job_description", "content")
    if not title or not company or not url or not description:
        raise SourceIntakeError("A source record requires title, company, application URL, and job description")
    now = captured_at or datetime.now(timezone.utc).isoformat()
    source_job_id = _first(payload, "source_job_id", "job_id", "id", "external_id")
    capture_evidence = _first(payload, "source_capture_evidence", "capture_url", "export_reference")
    normalized = {
        "title": title,
        "company": company,
        "location": _first(payload, "location", "location_name") or "Not specified",
        "url": url,
        "source": _SOURCE_LABELS[str(source).lower()],
        "description": description,
        "captured_at": now,
        "source_job_id": source_job_id or job_fingerprint({"company": company, "title": title, "url": url}),
        "source_url": canonicalize_url(_first(payload, "source_url", "listing_url")) or url,
        "discovery_channel": method,
        "published_at": _first(payload, "published_at", "posted_at", "date_posted"),
        "application_method": _first(payload, "application_method", "apply_method") or "external employer application",
        "source_capture_evidence": capture_evidence,
    }
    normalized["dedupe_key"] = job_fingerprint(normalized)
    return normalized


def deduplicate_source_jobs(jobs: Iterable[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep the first canonical job and return later source duplicates separately."""
    accepted: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in jobs:
        job = dict(item)
        key = str(job.get("dedupe_key") or job_fingerprint(job))
        job["dedupe_key"] = key
        if key in seen:
            duplicates.append(job)
            continue
        seen.add(key)
        accepted.append(job)
    return accepted, duplicates

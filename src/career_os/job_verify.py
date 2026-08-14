"""Active job posting verification before application-ready processing.

Does not claim a job is active without an HTTP check.
Marks expired/dead postings as INACTIVE so the pipeline skips resume generation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from .ghost_job_risk import assess_ghost_job_risk
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
    resolved_url: str | None = None
    redirect_chain: list[str] = field(default_factory=list)
    verification_source: str = "none"  # http | authenticated_browser | none
    application_channel: str | None = None
    browser_listing_evidence: bool = False
    experience_requirement: str | None = None
    education_requirement: str | None = None
    responsibilities_found: bool = False
    ghost_job_risk: dict[str, Any] = field(default_factory=dict)
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
            "resolved_url": self.resolved_url,
            "redirect_chain": self.redirect_chain,
            "verification_source": self.verification_source,
            "application_channel": self.application_channel,
            "browser_listing_evidence": self.browser_listing_evidence,
            "experience_requirement": self.experience_requirement,
            "education_requirement": self.education_requirement,
            "responsibilities_found": self.responsibilities_found,
            "ghost_job_risk": self.ghost_job_risk,
            "notes": self.notes,
        }


def _field_present(value: str | None, min_len: int = 2) -> bool:
    return bool(value and str(value).strip() and len(str(value).strip()) >= min_len)


def _canonical_url(value: str | None) -> str:
    return (str(value or "").strip().split("#", 1)[0].rstrip("/")).lower()


def _linkedin_job_id(value: str | None) -> str | None:
    match = re.search(r"/jobs/view/(\d+)", str(value or ""), re.I)
    return match.group(1) if match else None


def _identity_matches(expected: str | None, observed: str | None) -> bool:
    expected_text = re.sub(r"[^a-z0-9]+", " ", str(expected or "").lower()).strip()
    observed_text = re.sub(r"[^a-z0-9]+", " ", str(observed or "").lower()).strip()
    if not expected_text or not observed_text:
        return False
    if expected_text in observed_text or observed_text in expected_text:
        return True
    expected_tokens = {token for token in expected_text.split() if len(token) > 2}
    observed_tokens = {token for token in observed_text.split() if len(token) > 2}
    return len(expected_tokens & observed_tokens) >= max(1, min(2, len(expected_tokens)))


def _browser_active_evidence(job: Job, evidence: dict[str, Any] | None) -> tuple[bool, dict[str, Any]]:
    """Validate authenticated current-page evidence without trusting a boolean alone."""
    evidence = evidence or {}
    notes: list[str] = []
    page_url = str(evidence.get("page_url") or evidence.get("url") or "").strip()
    page_text = str(
        evidence.get("listing_text")
        or evidence.get("page_text")
        or evidence.get("description")
        or ""
    )
    channel = str(
        evidence.get("application_channel")
        or evidence.get("application_type")
        or ""
    ).strip() or None
    destination = str(
        evidence.get("apply_destination_url")
        or evidence.get("company_application_url")
        or evidence.get("apply_url")
        or evidence.get("application_url")
        or ""
    ).strip()
    apply_label = str(evidence.get("apply_label") or evidence.get("application_method") or "").lower()
    easy_apply = "easy apply" in f"{channel} {apply_label}".lower()

    if evidence.get("page_loaded") is not True or evidence.get("inaccessible") or evidence.get("login_required"):
        notes.append("authenticated browser page was not loaded and accessible")
    if evidence.get("closed_signal") or evidence.get("expired_signal") or evidence.get("removed_signal"):
        notes.append("browser evidence contains an explicit closed, expired, or removed signal")
    if evidence.get("suspicious_redirect"):
        notes.append("browser evidence contains a suspicious redirect")
    if isinstance(evidence.get("http_status"), int) and evidence["http_status"] >= 400:
        notes.append(f"browser page returned HTTP {evidence['http_status']}")
    if evidence.get("current_listing_evidence") is not True:
        notes.append("current listing evidence was not explicitly verified")
    if not _canonical_url(page_url):
        notes.append("browser evidence has no page URL")
    if not _identity_matches(job.title, evidence.get("page_title") or evidence.get("title")):
        notes.append("browser page title does not match the captured job title")
    if not _identity_matches(job.company, evidence.get("page_company") or evidence.get("company")):
        notes.append("browser page company does not match the captured employer")
    expected_id = job.source_job_id or _linkedin_job_id(job.url)
    observed_id = str(evidence.get("source_job_id") or evidence.get("job_id") or _linkedin_job_id(page_url) or "")
    if expected_id and observed_id != str(expected_id):
        notes.append("browser page job ID does not match the captured job ID")
    elif not expected_id and _canonical_url(page_url) != _canonical_url(job.url):
        notes.append("browser page URL does not match the captured job URL")
    if any(re.search(marker, page_text, re.I) for marker in INACTIVE_MARKERS):
        notes.append("browser listing text contains an explicit inactive marker")
    if not apply_label and evidence.get("apply_available") is not True:
        notes.append("a live Apply destination was not observed")
    if not destination and easy_apply:
        destination = page_url
    destination_parts = urlparse(destination)
    if destination_parts.path.rstrip("/").lower() == "/safety/go" and destination_parts.query:
        wrapped_target = parse_qs(destination_parts.query).get("url", [""])[0]
        if wrapped_target:
            destination = unquote(wrapped_target)
    if not _canonical_url(destination):
        notes.append("the observed Apply destination is missing or invalid")
    else:
        parsed_destination = urlparse(destination)
        if parsed_destination.scheme not in {"http", "https"} or not parsed_destination.netloc:
            notes.append("the observed Apply destination is not a valid HTTP URL")

    valid = not notes
    return valid, {
        "page_url": page_url,
        "application_url": destination or None,
        "application_channel": channel or ("LinkedIn Easy Apply" if easy_apply else None),
        "notes": notes,
    }


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


def verify_job_active(
    job: Job,
    *,
    timeout: float = 20.0,
    browser_evidence: dict[str, Any] | None = None,
) -> JobVerification:
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
        result.resolved_url = str(response.url)
        result.redirect_chain = [str(item.url) for item in response.history] + [str(response.url)]
        body = (response.text or "")[:200000].lower()
        browser_checked = isinstance(browser_evidence, dict)
        browser_valid, browser_result = _browser_active_evidence(job, browser_evidence) if browser_checked else (False, {"notes": []})
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
        if browser_checked and not browser_valid:
            explicit_inactive = bool(
                browser_evidence.get("closed_signal")
                or browser_evidence.get("expired_signal")
                or browser_evidence.get("removed_signal")
                or browser_evidence.get("inaccessible")
                or (isinstance(browser_evidence.get("http_status"), int) and browser_evidence["http_status"] >= 400)
            )
            result.active = False
            result.status = "INACTIVE" if explicit_inactive else "UNKNOWN"
            result.notes.append("Current authenticated browser evidence did not verify the same active listing")
            result.notes.extend(f"Browser evidence: {note}" for note in browser_result["notes"])
            result.ghost_job_risk = assess_ghost_job_risk(result.as_dict(), source=job.source).as_dict()
            return result
        result.active = True
        result.status = "ACTIVE"
        result.verification_source = "authenticated_browser" if browser_checked else "http"
        if browser_valid:
            result.resolved_url = browser_result["page_url"]
            result.application_url = browser_result["application_url"]
            result.application_channel = browser_result["application_channel"]
            result.browser_listing_evidence = True
            result.notes.append("Current authenticated browser listing evidence matched the reachable job URL")
        result.notes.append(f"URL reachable (HTTP {response.status_code})")
        result.ghost_job_risk = assess_ghost_job_risk(result.as_dict(), source=job.source).as_dict()
        return result
    except Exception as exc:  # noqa: BLE001
        browser_valid, browser_result = _browser_active_evidence(job, browser_evidence)
        if browser_valid:
            result.active = True
            result.status = "ACTIVE"
            result.verification_source = "authenticated_browser"
            result.resolved_url = browser_result["page_url"]
            result.application_url = browser_result["application_url"]
            result.application_channel = browser_result["application_channel"]
            result.browser_listing_evidence = True
            result.notes.append(
                "HTTP verification was unavailable; active status established from matching authenticated browser listing evidence"
            )
            result.ghost_job_risk = assess_ghost_job_risk(result.as_dict(), source=job.source).as_dict()
            return result
        explicit_inactive = bool(
            browser_evidence
            and (
                browser_evidence.get("closed_signal")
                or browser_evidence.get("expired_signal")
                or browser_evidence.get("removed_signal")
                or browser_evidence.get("inaccessible")
                or (isinstance(browser_evidence.get("http_status"), int) and browser_evidence["http_status"] >= 400)
            )
        )
        result.active = False if browser_evidence else (result.title_ok and result.description_ok)
        result.status = "INACTIVE" if explicit_inactive else "UNKNOWN"
        result.notes.append(f"URL check failed: {type(exc).__name__}: {exc}")
        if browser_result["notes"]:
            result.notes.extend(f"Browser evidence: {note}" for note in browser_result["notes"])
        result.ghost_job_risk = assess_ghost_job_risk(result.as_dict(), source=job.source).as_dict()
        return result

"""Safe job-intelligence primitives for Career OS.

This module intentionally does not scrape LinkedIn or submit applications. It
normalizes jobs from approved feeds/email/browser adapters and produces a
stable candidate-job record that can enter the existing application pipeline.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_TRACKING_KEYS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "trk", "trackingId", "refId", "gh_src", "source", "ref",
}
_WORK_MODEL_TERMS = {
    "remote": ("remote", "work from home", "wfh", "fully remote", "100% remote"),
    "hybrid": ("hybrid", "flexible hybrid"),
    "onsite": ("on-site", "onsite", "in office", "office-based"),
}


def normalize_job_url(url: str) -> str:
    """Remove common tracking parameters while preserving meaningful query data."""
    parts = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in _TRACKING_KEYS]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), urlencode(query), ""))


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9+#./$%-]", " ", value.lower())).strip()


def detect_work_model(text: str, explicit: str | None = None) -> str:
    """Classify work model conservatively; UNKNOWN is preferred to guessing."""
    if explicit:
        value = normalize_text(explicit)
        if "remote" in value or "wfh" in value:
            return "REMOTE"
        if "hybrid" in value:
            return "HYBRID"
        if "onsite" in value or "on-site" in value:
            return "ONSITE"
    haystack = normalize_text(text)
    for model, terms in _WORK_MODEL_TERMS.items():
        if any(term in haystack for term in terms):
            return model.upper()
    return "UNKNOWN"


def parse_salary_range(text: str) -> tuple[float | None, float | None, str | None]:
    """Extract an explicitly stated annual salary range without inventing currency."""
    haystack = text.replace(",", "")
    pattern = re.compile(
        r"(?:\$|USD\s*)?(\d+(?:\.\d+)?)\s*(k|K)?\s*(?:-|to|–|—)\s*"
        r"(?:\$|USD\s*)?(\d+(?:\.\d+)?)\s*(k|K)?"
        r"(?:\s*(?:/\s*year|per\s+year|yearly|annual|yr|p\.a\.))?",
        re.I,
    )
    match = pattern.search(haystack)
    if not match:
        return None, None, None
    low = float(match.group(1)) * (1000 if match.group(2) else 1)
    high = float(match.group(3)) * (1000 if match.group(4) else 1)
    currency = "USD" if "$" in match.group(0) or "USD" in match.group(0).upper() else None
    return low, high, currency


def freshness_hours(posted_at: str | None, now: datetime | None = None) -> float | None:
    """Return posting age in hours. Invalid/missing timestamps remain unknown."""
    if not posted_at:
        return None
    try:
        value = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        reference = now or datetime.now(timezone.utc)
        return max(0.0, (reference - value.astimezone(timezone.utc)).total_seconds() / 3600)
    except ValueError:
        return None


@dataclass(frozen=True)
class JobRecord:
    company: str
    title: str
    location: str
    url: str
    source: str
    requisition_id: str | None = None
    description: str = ""
    posted_at: str | None = None
    active: bool = True
    metadata: dict[str, str] = field(default_factory=dict)
    work_model: str = "UNKNOWN"
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None

    def __post_init__(self) -> None:
        if self.work_model == "UNKNOWN":
            object.__setattr__(self, "work_model", detect_work_model(f"{self.title} {self.description}"))
        if self.salary_min is None and self.salary_max is None:
            low, high, currency = parse_salary_range(f"{self.title} {self.description}")
            object.__setattr__(self, "salary_min", low)
            object.__setattr__(self, "salary_max", high)
            object.__setattr__(self, "salary_currency", currency)

    @property
    def canonical_url(self) -> str:
        return normalize_job_url(self.url)

    @property
    def identity(self) -> str:
        """Prefer requisition identity; fall back to stable URL identity."""
        if self.requisition_id:
            raw = f"{normalize_text(self.company)}|req:{normalize_text(self.requisition_id)}"
        else:
            raw = self.canonical_url
        return hashlib.sha256(raw.encode()).hexdigest()


@dataclass(frozen=True)
class JobMatch:
    job: JobRecord
    score: int
    matched_terms: tuple[str, ...]
    blockers: tuple[str, ...] = ()
    priority: str = "NORMAL"
    freshness_hours: float | None = None
    reasons: tuple[str, ...] = ()


def rank_jobs(
    jobs: Iterable[JobRecord],
    target_terms: Iterable[str],
    excluded_terms: Iterable[str] = (),
    *,
    preferred_work_models: Iterable[str] = ("REMOTE", "HYBRID"),
    minimum_salary: float | None = None,
    now: datetime | None = None,
) -> list[JobMatch]:
    """Rank jobs using transparent evidence; freshness/remote/pay add priority only."""
    terms = tuple(sorted({normalize_text(t) for t in target_terms if t.strip()}))
    excluded = tuple(sorted({normalize_text(t) for t in excluded_terms if t.strip()}))
    preferred_models = {m.strip().upper() for m in preferred_work_models if m.strip()}
    ranked: list[JobMatch] = []
    for job in jobs:
        haystack = normalize_text(f"{job.title} {job.description}")
        matched = tuple(t for t in terms if t in haystack)
        blockers = tuple(t for t in excluded if t in haystack)
        score = min(100, len(matched) * 12 + (20 if normalize_text(job.title) in haystack else 0))
        reasons: list[str] = []
        if job.work_model in preferred_models:
            score = min(100, score + 10)
            reasons.append(job.work_model.lower())
        age = freshness_hours(job.posted_at, now)
        if age is not None:
            if age <= 24:
                score = min(100, score + 8)
                reasons.append("posted_within_24h")
            elif age <= 72:
                score = min(100, score + 4)
        if minimum_salary is not None and job.salary_max is not None:
            if job.salary_max >= minimum_salary:
                score = min(100, score + 8)
                reasons.append("salary_target_met")
            else:
                blockers = tuple(sorted(set(blockers + ("below_salary_target",))))
                score = max(0, score - 12)
        if job.salary_max is not None:
            reasons.append("salary_disclosed")
        if blockers:
            score = max(0, score - 25 * len(blockers))
        if not job.active:
            score = 0
            blockers = tuple(sorted(set(blockers + ("inactive_job",))))
        priority = "HIGH" if score >= 80 and not blockers else "NORMAL"
        if score < 60 or blockers:
            priority = "LOW" if score < 60 else "NORMAL"
        ranked.append(JobMatch(job=job, score=score, matched_terms=matched, blockers=blockers,
                               priority=priority, freshness_hours=age, reasons=tuple(reasons)))
    return sorted(ranked, key=lambda item: (-item.score, item.job.company.lower(), item.job.title.lower()))


def select_job_updates(matches: Iterable[JobMatch], *, minimum_priority: str = "HIGH") -> list[JobMatch]:
    """Select fresh/high-priority opportunities for a dashboard or notification adapter."""
    order = {"LOW": 0, "NORMAL": 1, "HIGH": 2}
    threshold = order.get(minimum_priority.upper(), 2)
    return [m for m in matches if order.get(m.priority, 0) >= threshold and not m.blockers]

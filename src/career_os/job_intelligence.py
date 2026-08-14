"""Safe job-intelligence primitives for Career OS.

This module intentionally does not scrape LinkedIn or submit applications. It
normalizes jobs from approved feeds/email/browser adapters and produces a
stable candidate-job record that can enter the existing application pipeline.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_TRACKING_KEYS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "trk", "trackingId", "refId"}


def normalize_job_url(url: str) -> str:
    """Remove common tracking parameters while preserving meaningful query data."""
    parts = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in _TRACKING_KEYS]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), urlencode(query), ""))


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9+#./ -]", " ", value.lower())).strip()


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


def rank_jobs(jobs: Iterable[JobRecord], target_terms: Iterable[str], excluded_terms: Iterable[str] = ()) -> list[JobMatch]:
    """Rank jobs using transparent lexical evidence; no skills are invented."""
    terms = tuple(sorted({normalize_text(t) for t in target_terms if t.strip()}))
    excluded = tuple(sorted({normalize_text(t) for t in excluded_terms if t.strip()}))
    ranked: list[JobMatch] = []
    for job in jobs:
        haystack = normalize_text(f"{job.title} {job.description}")
        matched = tuple(t for t in terms if t in haystack)
        blockers = tuple(t for t in excluded if t in haystack)
        score = min(100, len(matched) * 12 + (20 if normalize_text(job.title) in haystack else 0))
        if blockers:
            score = max(0, score - 25 * len(blockers))
        if not job.active:
            score = 0
            blockers = tuple(sorted(set(blockers + ("inactive_job",))))
        ranked.append(JobMatch(job=job, score=score, matched_terms=matched, blockers=blockers))
    return sorted(ranked, key=lambda item: (-item.score, item.job.company.lower(), item.job.title.lower()))

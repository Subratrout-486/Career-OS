"""Durable local store for jobs already surfaced by Career OS."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from .job_sources import JobCandidate


class SeenJobStore:
    """Atomically persists stable job fingerprints across discovery runs."""

    def __init__(self, path: str | Path = "jobs/job_search/seen_jobs.json") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seen: dict[str, dict[str, object]] = {}
        self._load()

    @staticmethod
    def fingerprint(job: JobCandidate) -> str:
        canonical = "|".join((job.company.strip().lower(), job.title.strip().lower(), job.url.rstrip("/").lower()))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def new_only(self, jobs: Iterable[JobCandidate]) -> list[JobCandidate]:
        result: list[JobCandidate] = []
        now = time.time()
        for job in jobs:
            key = self.fingerprint(job)
            record = self._seen.get(key)
            if record is not None:
                record["last_seen_at"] = now
                continue
            self._seen[key] = {"first_seen_at": now, "last_seen_at": now, "job": asdict(job)}
            result.append(job)
        self._persist()
        return result

    def mark_seen(self, jobs: Iterable[JobCandidate]) -> None:
        now = time.time()
        for job in jobs:
            key = self.fingerprint(job)
            self._seen.setdefault(key, {"first_seen_at": now, "last_seen_at": now, "job": asdict(job)})
            self._seen[key]["last_seen_at"] = now
        self._persist()

    def count(self) -> int:
        return len(self._seen)

    def _load(self) -> None:
        if not self.path.exists():
            return
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self._seen = dict(raw.get("jobs", {}))

    def _persist(self) -> None:
        payload = {"jobs": self._seen}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        tmp.replace(self.path)

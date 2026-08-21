"""Configurable job-source registry with local durable seen-job state.

Inspired by workflow-as-configuration and durable local-state patterns used by
Dagu, while keeping Career OS source adapters independent and testable.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .job_sources import CompanyCareerSource, JobCandidate, deduplicate_candidates


@dataclass(frozen=True)
class JobSourceConfig:
    id: str
    company: str
    url: str
    enabled: bool = True
    source_type: str = "company_careers"


@dataclass(frozen=True)
class SeenJob:
    fingerprint: str
    title: str
    company: str
    url: str
    first_seen_at: str
    last_seen_at: str


def job_fingerprint(candidate: JobCandidate) -> str:
    canonical = "|".join((candidate.company.strip().lower(), candidate.title.strip().lower(), candidate.url.rstrip("/").lower()))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class SeenJobStore:
    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _write(self, payload: dict[str, dict]) -> None:
        fd, temp_name = tempfile.mkstemp(prefix=self.path.name + ".", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def classify(self, candidates: Iterable[JobCandidate]) -> tuple[list[JobCandidate], list[JobCandidate]]:
        state = self._read()
        new: list[JobCandidate] = []
        known: list[JobCandidate] = []
        now = datetime.now(timezone.utc).isoformat()
        changed = False
        for candidate in deduplicate_candidates(candidates):
            fp = job_fingerprint(candidate)
            previous = state.get(fp)
            if previous is None:
                state[fp] = asdict(SeenJob(fp, candidate.title, candidate.company, candidate.url, now, now))
                new.append(candidate)
                changed = True
            else:
                previous["last_seen_at"] = now
                known.append(candidate)
                changed = True
        if changed:
            self._write(state)
        return new, known

    def count(self) -> int:
        return len(self._read())


class JobSourceRegistry:
    def __init__(self, sources: Iterable[JobSourceConfig], *, state_path: str = "state/seen_jobs.json", source_adapter: CompanyCareerSource | None = None) -> None:
        self.sources = [source for source in sources if source.enabled]
        self.store = SeenJobStore(state_path)
        self.source_adapter = source_adapter or CompanyCareerSource()

    async def discover_new(self) -> dict[str, list[JobCandidate]]:
        result: dict[str, list[JobCandidate]] = {}
        for source in self.sources:
            if source.source_type != "company_careers":
                raise ValueError(f"unsupported job source type: {source.source_type}")
            candidates = await self.source_adapter.discover(url=source.url, company=source.company)
            new, _known = self.store.classify(candidates)
            result[source.id] = new
        return result

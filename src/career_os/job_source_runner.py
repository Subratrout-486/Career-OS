"""Durable multi-source discovery coordinator.

Runs configured public sources independently, records health in the source
catalog, filters jobs already surfaced in previous runs, and aggregates only
successful results. Transport failures in one source must not abort the
complete discovery cycle.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from .job_source_catalog import JobSourceCatalog, SourceRecord
from .job_sources import CompanyCareerSource, JobCandidate, deduplicate_candidates
from .seen_jobs import SeenJobStore


@dataclass(frozen=True)
class SourceRunResult:
    source_id: str
    status: str
    jobs: tuple[JobCandidate, ...] = ()
    error: str | None = None


class JobSourceRunner:
    def __init__(
        self,
        *,
        catalog: JobSourceCatalog,
        adapter: CompanyCareerSource | None = None,
        seen_store: SeenJobStore | None = None,
    ) -> None:
        self.catalog = catalog
        self.adapter = adapter or CompanyCareerSource()
        self.seen_store = seen_store or SeenJobStore()

    async def run_once(self) -> dict[str, Any]:
        sources = self.catalog.enabled_sources()
        results = list(await asyncio.gather(*(self._run_source(source) for source in sources))) if sources else []
        candidates = deduplicate_candidates(
            candidate for result in results if result.status == "SUCCESS" for candidate in result.jobs
        )
        new_jobs = self.seen_store.new_only(candidates)
        successful = [result for result in results if result.status == "SUCCESS"]
        failed = [result for result in results if result.status == "FAILED"]
        return {
            "sources": [r.source_id for r in results],
            "successful_sources": [r.source_id for r in successful],
            "failed_sources": [{"source_id": r.source_id, "error": r.error} for r in failed],
            "jobs": new_jobs,
            "all_discovered_jobs": candidates,
            "job_count": len(new_jobs),
            "seen_job_count": self.seen_store.count(),
        }

    async def _run_source(self, source: SourceRecord) -> SourceRunResult:
        try:
            jobs = await asyncio.wait_for(
                self.adapter.discover(url=source.url, company=source.company),
                timeout=float(getattr(source, "timeout_sec", 20)),
            )
            self.catalog.record_success(source.id, discovered_count=len(jobs))
            return SourceRunResult(source.id, "SUCCESS", tuple(jobs))
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            self.catalog.record_failure(source.id, error)
            return SourceRunResult(source.id, "FAILED", error=error)

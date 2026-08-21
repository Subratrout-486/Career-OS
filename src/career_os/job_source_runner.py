"""Durable multi-source discovery coordinator.

Runs configured public sources independently, records health in the source
catalog, and aggregates only successful results. Transport failures in one
source must not abort the complete discovery cycle.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from .job_source_catalog import JobSourceCatalog
from .job_sources import CompanyCareerSource, JobCandidate, deduplicate_candidates


@dataclass(frozen=True)
class SourceRunResult:
    source_id: str
    status: str
    jobs: tuple[JobCandidate, ...] = ()
    error: str | None = None


class JobSourceRunner:
    def __init__(self, *, catalog: JobSourceCatalog, adapter: CompanyCareerSource | None = None) -> None:
        self.catalog = catalog
        self.adapter = adapter or CompanyCareerSource()

    async def run_once(self) -> dict[str, Any]:
        sources = self.catalog.enabled_sources()
        results: list[SourceRunResult] = []
        tasks = [self._run_source(source) for source in sources]
        if tasks:
            results = list(await asyncio.gather(*tasks))

        candidates = deduplicate_candidates(
            candidate for result in results if result.status == "SUCCESS" for candidate in result.jobs
        )
        successful = [result for result in results if result.status == "SUCCESS"]
        failed = [result for result in results if result.status == "FAILED"]
        return {
            "sources": [r.source_id for r in results],
            "successful_sources": [r.source_id for r in successful],
            "failed_sources": [{"source_id": r.source_id, "error": r.error} for r in failed],
            "jobs": candidates,
            "job_count": len(candidates),
        }

    async def _run_source(self, source: dict[str, Any]) -> SourceRunResult:
        source_id = str(source["id"])
        try:
            jobs = await asyncio.wait_for(
                self.adapter.discover(url=str(source["url"]), company=str(source["company"])),
                timeout=float(source.get("timeout_sec", 20)),
            )
            self.catalog.record_success(source_id, len(jobs))
            return SourceRunResult(source_id, "SUCCESS", tuple(jobs))
        except Exception as exc:
            self.catalog.record_failure(source_id, f"{type(exc).__name__}: {exc}")
            return SourceRunResult(source_id, "FAILED", error=f"{type(exc).__name__}: {exc}")

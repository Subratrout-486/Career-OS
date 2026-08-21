#!/usr/bin/env python3
"""Discover one real public job and process it end-to-end with a direct AI provider.

This is the Conductor- and Notion-independent E2E path. It keeps Career OS
orchestration, truth controls, resume/ATS stages, and audit trails intact while
using the canonical profile as the evidence boundary for this smoke/E2E run.
The live Notion evidence vault remains a production enrichment layer and is not
allowed to block this independent real-job processing path.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from career_os.direct_provider_runtime import DirectProviderRuntime
from career_os.models import Job
from career_os.orchestrator import CareerOS
from career_os.pipeline_adapter import ControlledCareerPipeline
from direct_career_watcher import run as discover_public_jobs

PREFERRED = (
    "product support",
    "application support",
    "technical support",
    "support analyst",
    "support engineer",
    "operations analyst",
    "research analyst",
    "business analyst",
)


def choose_job(jobs: list[dict]) -> dict:
    if not jobs:
        raise RuntimeError("NO_REAL_DISCOVERED_JOB")

    def score(job: dict) -> tuple[int, int, str]:
        title = str(job.get("title", "")).lower()
        description = str(job.get("description", "")).lower()
        preference = next(
            (i for i, term in enumerate(PREFERRED) if term in title),
            len(PREFERRED),
        )
        technical = sum(
            term in description
            for term in (
                "support",
                "sql",
                "incident",
                "troubleshooting",
                "application",
                "analyst",
            )
        )
        return (preference, -technical, str(job.get("published_at") or ""))

    return sorted(jobs, key=score)[0]


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="config/master_profile.md")
    parser.add_argument("--result-output", default="real-job-direct-e2e-result.json")
    parser.add_argument("--control-plane-output", default="real-job-direct-e2e-control-plane.json")
    parser.add_argument("--discovery-output", default="real-job-direct-discovery.json")
    args = parser.parse_args()

    jobs, digest = discover_public_jobs()
    selected = choose_job(jobs)
    Path(args.discovery_output).write_text(
        json.dumps({"digest": digest, "selected_job": selected}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    job = Job.model_validate(selected)
    profile = Path(args.profile).read_text(encoding="utf-8")
    runtime = DirectProviderRuntime()

    # Critical boundary: inject an explicit empty vault so this direct E2E
    # never attempts the unavailable external Notion credential/data source.
    # The canonical profile remains the only evidence source for this run;
    # truth_guard still blocks unsupported resume claims.
    pipeline = CareerOS(runtime=runtime, vault=[], write_to_notion=False)
    controlled = ControlledCareerPipeline(pipeline=pipeline)
    result = await controlled.process(profile, job)

    payload = result.model_dump(mode="json")
    payload["provider_used"] = runtime.last_provider_used
    payload["provider_policy"] = "STRICT_DIRECT_NO_CONDUCTOR_NO_FALLBACK"
    payload["evidence_mode"] = "CANONICAL_PROFILE_ONLY_EXTERNAL_NOTION_DISABLED_FOR_E2E"
    payload["e2e_policy"] = "REAL_DISCOVERY_FULL_PROCESSING_NO_APPLICATION_SUBMISSION"
    Path(args.result_output).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    Path(args.control_plane_output).write_text(
        json.dumps(controlled.store.snapshot(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    stages = {
        "job_verification": result.job_verification,
        "jd_analysis": result.jd_analysis,
        "fit": result.fit,
        "resume": result.resume,
        "ats": result.ats,
        "independent_ats": result.independent_ats,
        "recruiter_review": result.recruiter_review,
        "design_qa": result.design_qa,
    }
    missing = [name for name, value in stages.items() if value is None]
    if missing:
        raise SystemExit(
            "CAREER_OS_DIRECT_E2E_INCOMPLETE: "
            f"missing={','.join(missing)} review_status={result.review_status}"
        )
    if result.job_verification.status != "ACTIVE":
        raise SystemExit(
            f"CAREER_OS_DIRECT_E2E_FAILED: job verification={result.job_verification.status}"
        )
    if not runtime.last_provider_used:
        raise SystemExit("CAREER_OS_DIRECT_E2E_FAILED: direct provider usage not recorded")

    print("CAREER_OS_REAL_JOB_DIRECT_E2E_PASSED")
    print(f"JOB={job.company} — {job.title}")
    print(f"URL={job.url}")
    print(f"PROVIDER={runtime.last_provider_used}")
    print("EVIDENCE_MODE=CANONICAL_PROFILE_ONLY_EXTERNAL_NOTION_DISABLED_FOR_E2E")
    print(f"FIT_SCORE={result.fit.fit_score if result.fit else None}")
    print(f"REVIEW_STATUS={result.review_status}")
    print(f"APPLICATION_MODE={result.application_mode}")
    print("APPLICATION_SUBMITTED=FALSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

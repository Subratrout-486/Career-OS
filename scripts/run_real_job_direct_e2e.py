#!/usr/bin/env python3
"""Discover real public jobs and prove one can traverse the full Career OS E2E path.

This path is deliberately independent of Conductor and live Notion. It uses the
canonical profile as the evidence boundary and a single configured direct AI
provider. Discovery candidates that legitimately short-circuit (for example a
SKIP fit decision or an inactive posting) are recorded and the runner continues
until it finds an ACTIVE job that actually traverses resume/ATS/reviewer/design
stages. A genuine runtime/provider exception still fails the workflow.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import traceback
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


def score_job(job: dict) -> tuple[int, int, str]:
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


def candidate_jobs(jobs: list[dict], limit: int) -> list[dict]:
    if not jobs:
        raise RuntimeError("NO_REAL_DISCOVERED_JOB")
    return sorted(jobs, key=score_job)[:limit]


def write_json(path: str, payload: object) -> None:
    Path(path).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


async def process_one(profile: str, selected: dict, runtime: DirectProviderRuntime) -> tuple[object, object]:
    job = Job.model_validate(selected)
    # Explicit empty vault: this E2E must never reach the unavailable external
    # Notion evidence source. The canonical profile remains the truth boundary.
    pipeline = CareerOS(runtime=runtime, vault=[], write_to_notion=False)
    controlled = ControlledCareerPipeline(pipeline=pipeline)
    result = await controlled.process(profile, job)
    return job, result


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="config/master_profile.md")
    parser.add_argument("--result-output", default="real-job-e2e-result.json")
    parser.add_argument("--control-plane-output", default="real-job-e2e-control-plane.json")
    parser.add_argument("--discovery-output", default="real-job-discovery.json")
    parser.add_argument("--max-candidates", type=int, default=8)
    args = parser.parse_args()

    jobs, digest = discover_public_jobs()
    candidates = candidate_jobs(jobs, max(1, args.max_candidates))
    write_json(args.discovery_output, {"digest": digest, "candidates": candidates})

    profile = Path(args.profile).read_text(encoding="utf-8")
    runtime = DirectProviderRuntime()
    attempts: list[dict] = []
    successful_job = None
    successful_result = None
    successful_store = None

    for index, selected in enumerate(candidates, start=1):
        label = f"{selected.get('company')} — {selected.get('title')}"
        print(f"E2E_CANDIDATE_{index}={label}", flush=True)
        try:
            job, result = await process_one(profile, selected, runtime)
        except Exception as exc:
            traceback.print_exc()
            write_json("real-job-direct-e2e-error.json", {
                "candidate": selected,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            })
            raise

        payload = result.model_dump(mode="json")
        payload["provider_used"] = runtime.last_provider_used
        payload["provider_policy"] = "STRICT_DIRECT_NO_CONDUCTOR_NO_FALLBACK"
        payload["evidence_mode"] = "CANONICAL_PROFILE_ONLY_EXTERNAL_NOTION_DISABLED_FOR_E2E"
        payload["e2e_policy"] = "REAL_DISCOVERY_FULL_PROCESSING_NO_APPLICATION_SUBMISSION"
        attempts.append({
            "candidate": label,
            "job_verification": getattr(result.job_verification, "status", None),
            "review_status": result.review_status,
            "fit_score": result.fit.fit_score if result.fit else None,
            "recommendation": result.fit.recommendation if result.fit else None,
            "full_stage_traversal": all(result.__dict__.get(name) is not None for name in (
                "job_verification", "jd_analysis", "fit", "resume", "ats",
                "independent_ats", "recruiter_review", "design_qa"
            )),
        })

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

        # A legitimate SKIP/inactive result is not a code failure. It simply
        # cannot exercise the downstream stages, so try the next discovered job.
        if missing and result.review_status in {"SKIPPED", "INACTIVE_JOB"}:
            print(
                f"E2E_CANDIDATE_SKIPPED={label} review_status={result.review_status} "
                f"missing={','.join(missing)}",
                flush=True,
            )
            continue

        if missing:
            write_json(args.result_output, payload)
            write_json(args.control_plane_output, controlled.store.snapshot())
            raise SystemExit(
                "CAREER_OS_DIRECT_E2E_INCOMPLETE: "
                f"candidate={label} missing={','.join(missing)} review_status={result.review_status} "
                f"errors={result.errors}"
            )

        if result.job_verification.status != "ACTIVE":
            continue
        if not runtime.last_provider_used:
            raise SystemExit("CAREER_OS_DIRECT_E2E_FAILED: direct provider usage not recorded")

        successful_job = job
        successful_result = result
        successful_store = controlled.store.snapshot()
        break

    write_json("real-job-e2e-attempts.json", {"attempts": attempts})

    if successful_job is None or successful_result is None:
        raise SystemExit(
            "CAREER_OS_REAL_JOB_DIRECT_E2E_NO_FULL_TRAVERSAL: "
            f"tried={len(attempts)} candidates; attempts={json.dumps(attempts, ensure_ascii=False)}"
        )

    payload = successful_result.model_dump(mode="json")
    payload["provider_used"] = runtime.last_provider_used
    payload["provider_policy"] = "STRICT_DIRECT_NO_CONDUCTOR_NO_FALLBACK"
    payload["evidence_mode"] = "CANONICAL_PROFILE_ONLY_EXTERNAL_NOTION_DISABLED_FOR_E2E"
    payload["e2e_policy"] = "REAL_DISCOVERY_FULL_PROCESSING_NO_APPLICATION_SUBMISSION"
    payload["candidate_attempts"] = attempts
    write_json(args.result_output, payload)
    write_json(args.control_plane_output, successful_store)

    print("CAREER_OS_REAL_JOB_DIRECT_E2E_PASSED")
    print(f"JOB={successful_job.company} — {successful_job.title}")
    print(f"URL={successful_job.url}")
    print(f"PROVIDER={runtime.last_provider_used}")
    print("EVIDENCE_MODE=CANONICAL_PROFILE_ONLY_EXTERNAL_NOTION_DISABLED_FOR_E2E")
    print(f"FIT_SCORE={successful_result.fit.fit_score if successful_result.fit else None}")
    print(f"REVIEW_STATUS={successful_result.review_status}")
    print(f"APPLICATION_MODE={successful_result.application_mode}")
    print("APPLICATION_SUBMITTED=FALSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

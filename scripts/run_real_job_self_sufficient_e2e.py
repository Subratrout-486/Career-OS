#!/usr/bin/env python3
"""Self-sufficient real-job E2E runner.

Uses the specialist provider pool directly; Conductor and live Notion are not
required for this verification path. A real application is never submitted.
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

PREFERRED = ("product support", "application support", "technical support", "support analyst", "support engineer", "operations analyst", "research analyst", "business analyst")


def score_job(job: dict) -> tuple[int, int, str]:
    title = str(job.get("title", "")).lower()
    description = str(job.get("description", "")).lower()
    preference = next((i for i, term in enumerate(PREFERRED) if term in title), len(PREFERRED))
    technical = sum(term in description for term in ("support", "sql", "incident", "troubleshooting", "application", "analyst"))
    return preference, -technical, str(job.get("published_at") or "")


def write_json(path: str, payload: object) -> None:
    Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="config/master_profile.md")
    parser.add_argument("--result-output", default="real-job-e2e-result.json")
    parser.add_argument("--control-plane-output", default="real-job-e2e-control-plane.json")
    parser.add_argument("--discovery-output", default="real-job-discovery.json")
    parser.add_argument("--max-candidates", type=int, default=8)
    args = parser.parse_args()

    jobs, digest = discover_public_jobs()
    if not jobs:
        raise RuntimeError("NO_REAL_DISCOVERED_JOB")
    candidates = sorted(jobs, key=score_job)[: max(1, args.max_candidates)]
    write_json(args.discovery_output, {"digest": digest, "candidates": candidates})

    profile = Path(args.profile).read_text(encoding="utf-8")
    runtime = DirectProviderRuntime()
    attempts: list[dict] = []

    for index, selected in enumerate(candidates, start=1):
        label = f"{selected.get('company')} — {selected.get('title')}"
        print(f"E2E_CANDIDATE_{index}={label}", flush=True)
        job = Job.model_validate(selected)
        pipeline = CareerOS(runtime=runtime, vault=[], write_to_notion=False)
        controlled = ControlledCareerPipeline(pipeline=pipeline)
        try:
            result = await controlled.process(profile, job)
        except Exception as exc:
            traceback.print_exc()
            write_json("real-job-direct-e2e-error.json", {
                "candidate": selected,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "agent_runtime": runtime.diagnostics(),
            })
            raise

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
        attempt = {
            "candidate": label,
            "job_verification": getattr(result.job_verification, "status", None),
            "review_status": result.review_status,
            "fit_score": result.fit.fit_score if result.fit else None,
            "recommendation": result.fit.recommendation if result.fit else None,
            "provider_used": runtime.last_provider_used,
            "provider_attempts": list(runtime.provider_attempts),
            "full_stage_traversal": not bool(missing),
            "missing": missing,
        }
        attempts.append(attempt)

        payload = result.model_dump(mode="json")
        payload.update({
            "provider_used": runtime.last_provider_used,
            "provider_policy": "SELF_SUFFICIENT_DEPARTMENT_AGENT_POOL_NO_CONDUCTOR",
            "agent_runtime": runtime.diagnostics(),
            "evidence_mode": "CANONICAL_PROFILE_ONLY_EXTERNAL_NOTION_DISABLED_FOR_E2E",
            "e2e_policy": "REAL_DISCOVERY_FULL_PROCESSING_NO_APPLICATION_SUBMISSION",
            "candidate_attempts": attempts,
        })

        if missing and result.review_status in {"SKIPPED", "INACTIVE_JOB"}:
            print(f"E2E_CANDIDATE_SKIPPED={label} review_status={result.review_status} missing={','.join(missing)}", flush=True)
            continue
        if missing:
            write_json(args.result_output, payload)
            write_json(args.control_plane_output, controlled.store.snapshot())
            raise SystemExit("CAREER_OS_SELF_SUFFICIENT_E2E_INCOMPLETE: " f"candidate={label} missing={','.join(missing)} review_status={result.review_status} errors={result.errors}")
        if result.job_verification.status != "ACTIVE":
            continue
        if not runtime.last_provider_used:
            raise SystemExit("CAREER_OS_SELF_SUFFICIENT_E2E_FAILED: no provider recorded")

        write_json(args.result_output, payload)
        write_json(args.control_plane_output, controlled.store.snapshot())
        write_json("real-job-e2e-attempts.json", {"attempts": attempts})
        print("CAREER_OS_REAL_JOB_SELF_SUFFICIENT_E2E_PASSED")
        print(f"JOB={job.company} — {job.title}")
        print(f"URL={job.url}")
        print(f"PROVIDER={runtime.last_provider_used}")
        print(f"PROVIDER_ATTEMPTS={','.join(runtime.provider_attempts)}")
        print(f"FIT_SCORE={result.fit.fit_score if result.fit else None}")
        print(f"REVIEW_STATUS={result.review_status}")
        print(f"APPLICATION_MODE={result.application_mode}")
        print("APPLICATION_SUBMITTED=FALSE")
        return 0

    write_json("real-job-e2e-attempts.json", {"attempts": attempts})
    raise SystemExit("CAREER_OS_REAL_JOB_SELF_SUFFICIENT_E2E_NO_FULL_TRAVERSAL: " f"tried={len(attempts)} candidates")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

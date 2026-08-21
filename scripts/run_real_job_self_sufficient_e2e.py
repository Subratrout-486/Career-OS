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
from career_os.models import Job, RecruiterReview
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


def local_recruiter_challenge(result) -> RecruiterReview:
    """Fail-closed deterministic challenger when no independent model is reachable.

    This is intentionally a safety fallback, not an AI substitute. It checks
    the artifacts already produced by Career OS and keeps the application in
    REVIEW_REQUIRED. A later run with a verified independent model replaces
    this fallback with the real red-team reviewer.
    """
    issues: list[str] = []
    if not result.truth_guard_passed:
        issues.append("truth guard did not pass")
    if not result.resume:
        issues.append("tailored resume is missing")
    if not result.ats or not result.ats.passed:
        issues.append("primary ATS audit did not pass")
    if not result.independent_ats or not result.independent_ats.passed:
        issues.append("independent ATS audit did not pass")
    if not result.design_qa or not result.design_qa.passed:
        issues.append("resume design QA did not pass")

    if issues:
        verdict = "REVISE"
        status = "REVISE"
        warnings = [
            "Deterministic challenger fallback used because no verified independent AI provider was reachable.",
            *issues,
        ]
    else:
        verdict = "PASS"
        status = "PASS"
        warnings = [
            "Deterministic challenger fallback used because no verified independent AI provider was reachable.",
            "PASS here means deterministic safety checks passed; it is not AI recruiter approval.",
        ]

    notes = (
        f"VERDICT: {verdict}\n"
        "ISSUES: " + ("; ".join(issues) if issues else "none") + "\n"
        "REQUIRED_FIXES: " + ("; ".join(issues) if issues else "none")
    )
    return RecruiterReview(
        status=status,
        recommendation="REVIEW",
        provider="local:deterministic-challenger",
        notes=notes,
        warnings=warnings,
    )


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

        # A provider outage must not silently masquerade as a completed
        # recruiter-review stage. If the independent AI reviewer is unavailable,
        # run the bounded deterministic safety reviewer instead. It never grants
        # AUTO_APPLY and is explicitly labelled as a local fallback.
        if result.recruiter_review is None or result.recruiter_review.status == "NOT_RUN":
            result.recruiter_review = local_recruiter_challenge(result)
            result.challenger_notes = result.recruiter_review.notes
            result.challenger_diagnostic = {
                **(result.challenger_diagnostic or {}),
                "fallback": "local:deterministic-challenger",
                "ai_reviewer_available": False,
            }
            result.errors.append(
                "WARNING: independent AI recruiter unavailable; deterministic challenger fallback used."
            )
            result.application_mode = "REVIEW_REQUIRED"
            result.application_mode_reason = (
                "Independent AI recruiter was unavailable; deterministic safety review completed, but human review is required."
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
        attempt = {
            "candidate": label,
            "job_verification": getattr(result.job_verification, "status", None),
            "review_status": result.review_status,
            "fit_score": result.fit.fit_score if result.fit else None,
            "recommendation": result.fit.recommendation if result.fit else None,
            "provider_used": runtime.last_provider_used,
            "provider_attempts": list(runtime.provider_attempts),
            "recruiter_review_status": result.recruiter_review.status if result.recruiter_review else None,
            "recruiter_review_provider": result.recruiter_review.provider if result.recruiter_review else None,
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
        print(f"RECRUITER_REVIEW={result.recruiter_review.status if result.recruiter_review else 'MISSING'}")
        print(f"RECRUITER_REVIEW_PROVIDER={result.recruiter_review.provider if result.recruiter_review else 'missing'}")
        print(f"APPLICATION_MODE={result.application_mode}")
        print("APPLICATION_SUBMITTED=FALSE")
        return 0

    write_json("real-job-e2e-attempts.json", {"attempts": attempts})
    raise SystemExit("CAREER_OS_REAL_JOB_SELF_SUFFICIENT_E2E_NO_FULL_TRAVERSAL: " f"tried={len(attempts)} candidates")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

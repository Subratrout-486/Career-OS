#!/usr/bin/env python3
"""Run one discovered public job through Career OS's internal runtime only.

This intentionally bypasses Conductor/AgentFlow and never submits an application.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from career_os.job_e2e_runner import JobE2EInput, JobE2ERunner
from direct_career_watcher import run as discover_public_jobs

PREFERRED = (
    "product support", "application support", "technical support",
    "support analyst", "support engineer", "operations analyst",
    "research analyst", "business analyst",
)


def choose_job(jobs: list[dict]) -> dict:
    if not jobs:
        raise RuntimeError("NO_REAL_DISCOVERED_JOB")
    def score(job: dict) -> tuple[int, int, str]:
        title = str(job.get("title", "")).lower()
        desc = str(job.get("description", "")).lower()
        preference = next((i for i, term in enumerate(PREFERRED) if term in title), len(PREFERRED))
        technical = sum(term in desc for term in ("support", "sql", "incident", "troubleshooting", "application", "analyst"))
        return (preference, -technical, str(job.get("published_at") or ""))
    return sorted(jobs, key=score)[0]


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="config/master_profile.md")
    parser.add_argument("--result-output", default="real-job-internal-e2e-result.json")
    parser.add_argument("--control-plane-output", default="real-job-internal-e2e-control-plane.json")
    args = parser.parse_args()

    jobs, digest = discover_public_jobs()
    selected = choose_job(jobs)
    profile = Path(args.profile).read_text(encoding="utf-8")

    # The internal runner owns the durable control plane and specialist execution.
    # No Conductor runtime is constructed here.
    from career_os.control_plane import ControlPlaneStore
    from career_os.agent_runtime import MultiAgentRuntime

    store = ControlPlaneStore()
    runtime = MultiAgentRuntime(store, provider_runtime=None)
    runner = JobE2ERunner(runtime)
    result = await runner.run(JobE2EInput(
        job=selected,
        profile={"text": profile},
        metadata={"discovery_digest": digest, "mode": "internal-runtime-no-submit"},
    ))

    payload = {
        "run_id": result.run_id,
        "parent_task_id": result.parent_task_id,
        "state": result.state,
        "stages": list(result.stages),
        "audit_event_ids": list(result.audit_event_ids),
        "artifacts": result.artifacts,
        "job": selected,
        "submission": {"enabled": False, "performed": False},
        "e2e_policy": "REAL_DISCOVERY_FULL_PROCESSING_INTERNAL_RUNTIME_NO_APPLICATION_SUBMISSION",
    }
    Path(args.result_output).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    Path(args.control_plane_output).write_text(json.dumps(store.snapshot(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if result.state not in {"READY_TO_APPLY", "REVIEW_REQUIRED", "BLOCKED"}:
        raise SystemExit(f"CAREER_OS_INTERNAL_E2E_FAILED: state={result.state}")
    print("CAREER_OS_INTERNAL_REAL_JOB_E2E_PASSED")
    print(f"JOB={selected.get('company')} — {selected.get('title')}")
    print(f"STATE={result.state}")
    print(f"STAGES={len(result.stages)}")
    print("APPLICATION_SUBMITTED=FALSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

#!/usr/bin/env python3
"""Verify the no-paid-provider Career OS handoff boundary.

This test intentionally performs no LLM inference. It proves that a real job
can be converted into a durable Conductor handoff without requiring an API key.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from career_os.control_plane import AuditEvent, ControlPlaneStore, TaskRecord, TaskStatus
from career_os.models import Job


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-json", required=True)
    parser.add_argument("--profile", default="config/master_profile.md")
    parser.add_argument("--result-output", default="conductor-handoff.json")
    parser.add_argument("--control-plane", default="conductor-handoff-control-plane.json")
    args = parser.parse_args()

    job = Job.model_validate(json.loads(Path(args.job_json).read_text(encoding="utf-8")))
    profile_path = Path(args.profile)
    if not profile_path.exists():
        raise SystemExit(f"PROFILE_NOT_FOUND: {profile_path}")

    store = ControlPlaneStore(args.control_plane)
    task = store.create_task(
        TaskRecord(
            objective=f"Process one job through Career OS: {job.company} — {job.title}",
            department="career-pipeline",
            agent_id="conductor",
            status=TaskStatus.WAITING,
            payload={
                "runtime": "conductor-boundary-v1",
                "job": job.model_dump(mode="json"),
                "profile_path": str(profile_path),
                "source_of_truth": "Career Profile / Master Resume + Career Evidence Vault",
                "handoff_status": "READY_FOR_CONDUCTOR",
            },
        )
    )
    handoff = {
        "status": "READY_FOR_CONDUCTOR",
        "task_id": task.id,
        "job": job.model_dump(mode="json"),
        "profile_path": str(profile_path),
        "source_of_truth": "Career Profile / Master Resume + Career Evidence Vault",
        "next_stages": [
            "JD_ANALYSIS",
            "EVIDENCE_RETRIEVAL",
            "FIT",
            "RESUME",
            "TRUTH_GUARD",
            "ATS",
            "INDEPENDENT_REVIEW",
            "NOTION_SYNC",
        ],
        "ai_runtime": "Conductor/AgentFlow",
        "conductor_base_url_configured": bool(os.getenv("CONDUCTOR_BASE_URL")),
        "paid_provider_fallback": False,
    }
    task.payload["handoff"] = handoff
    store.update_task(task)
    store.add_audit(
        AuditEvent(
            event_type="CONDUCTOR_HANDOFF_READY",
            actor_type="harness",
            actor_id="career-os-boundary-smoke",
            source="conductor-boundary",
            task_id=task.id,
            decision="WAITING_FOR_CONDUCTOR",
            output={"status": "READY_FOR_CONDUCTOR"},
        )
    )

    Path(args.result_output).write_text(
        json.dumps(handoff, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(handoff, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

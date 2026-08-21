#!/usr/bin/env python3
"""Create durable provider-neutral Career OS handoff evidence.

No model call occurs here. This proves the durable task boundary can be
created independently of Conductor or any paid provider.
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
    parser.add_argument("--result-output", default="provider-boundary-handoff.json")
    parser.add_argument("--control-plane", default="provider-boundary-control-plane.json")
    args = parser.parse_args()

    job = Job.model_validate(json.loads(Path(args.job_json).read_text(encoding="utf-8")))
    profile_path = Path(args.profile)
    if not profile_path.exists():
        raise SystemExit(f"PROFILE_NOT_FOUND: {profile_path}")

    provider = os.getenv("AI_PROVIDER", "auto").strip().lower()
    task = ControlPlaneStore(args.control_plane).create_task(
        TaskRecord(
            objective=f"Process one job through Career OS: {job.company} — {job.title}",
            department="career-pipeline",
            agent_id="ai-provider",
            status=TaskStatus.WAITING,
            payload={
                "runtime": "career-os-provider-boundary-v1",
                "job": job.model_dump(mode="json"),
                "profile_path": str(profile_path),
                "source_of_truth": "Career Profile / Master Resume + Career Evidence Vault",
                "handoff_status": "READY_FOR_AI_PROVIDER",
                "ai_provider": provider,
            },
        )
    )

    handoff = {
        "status": "READY_FOR_AI_PROVIDER",
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
        "ai_runtime": "Direct provider boundary",
        "ai_provider": provider,
        "paid_provider_fallback": False,
    }
    task.payload["handoff"] = handoff
    store = ControlPlaneStore(args.control_plane)
    store.update_task(task)
    store.add_audit(
        AuditEvent(
            event_type="AI_PROVIDER_HANDOFF_READY",
            actor_type="harness",
            actor_id="career-os-provider-boundary",
            source="provider-boundary",
            task_id=task.id,
            decision="WAITING_FOR_AI_PROVIDER",
            output={"status": "READY_FOR_AI_PROVIDER", "provider": provider},
        )
    )

    Path(args.result_output).write_text(
        json.dumps(handoff, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(handoff, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

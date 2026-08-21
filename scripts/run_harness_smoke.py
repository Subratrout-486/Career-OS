#!/usr/bin/env python3
"""Run one complete Career OS pipeline execution through the durable harness."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from career_os.control_plane import ControlPlaneStore
from career_os.evidence_vault_snapshot import VAULT_SNAPSHOT
from career_os.models import Job
from career_os.orchestrator import CareerOS
from career_os.pipeline_harness import PipelineHarness


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-json", required=True)
    parser.add_argument("--profile", default="config/master_profile.md")
    parser.add_argument("--result-output", default="harness-smoke-result.json")
    parser.add_argument("--control-plane", default="harness-smoke-control-plane.json")
    args = parser.parse_args()

    job = Job.model_validate(json.loads(Path(args.job_json).read_text(encoding="utf-8")))
    profile = Path(args.profile).read_text(encoding="utf-8")
    browser_context = {
        "page_loaded": True,
        "current_listing_evidence": True,
        "page_url": job.url,
        "page_title": job.title,
        "page_company": job.company,
        "application_channel": "Employer ATS",
        "apply_label": "Apply",
        "apply_available": True,
        "application_url": job.url,
        "apply_destination_url": job.url,
        "http_status": 200,
    }

    async def run() -> dict:
        store = ControlPlaneStore(args.control_plane)
        harness = PipelineHarness(store)
        task, result = await harness.run(
            objective=f"Process one job end-to-end: {job.company} — {job.title}",
            context={"job_id": job.job_id, "company": job.company, "title": job.title},
            operation=lambda: CareerOS(vault=VAULT_SNAPSHOT, write_to_notion=False).process(
                profile,
                job,
                browser_context=browser_context,
            ),
        )
        payload = result.model_dump()
        payload["harness"] = {
            "task_id": task.id,
            "status": task.status.value,
            "recovery_pending": harness.recover(),
        }
        return payload

    result = asyncio.run(run())
    Path(args.result_output).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "harness_task_id": result["harness"]["task_id"],
        "harness_status": result["harness"]["status"],
        "review_status": result.get("review_status"),
        "application_mode": result.get("application_mode"),
        "errors": result.get("errors", []),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

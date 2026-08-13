from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from career_os.models import Job
from career_os.orchestrator import CareerOS, load_profile
from career_os.evidence_vault_snapshot import VAULT_SNAPSHOT


async def main() -> None:
    root = Path(__file__).resolve().parents[1]
    item = json.loads((root / "pilot" / "one_job.json").read_text(encoding="utf-8"))[0]
    profile = load_profile(str(root / "config" / "master_profile.md"))
    job = Job.model_validate(item)
    timeout_seconds = float(os.getenv("ONE_JOB_TIMEOUT_SECONDS", "240"))
    runtime = CareerOS(vault=VAULT_SNAPSHOT, write_to_notion=False)
    print(f"processing {job.company} — {job.title}", flush=True)
    try:
        result = await asyncio.wait_for(runtime.process(profile, job), timeout=timeout_seconds)
        output = result.model_dump(mode="json")
    except asyncio.TimeoutError:
        output = {
            "job": job.model_dump(mode="json"),
            "application_mode": "REVIEW_REQUIRED",
            "application_mode_reason": "One-job validation timed out before a complete result was produced.",
            "application_mode_blockers": [f"timeout after {timeout_seconds:g} seconds"],
            "review_status": "PILOT_TIMEOUT",
            "errors": [f"PILOT_TIMEOUT: processing exceeded {timeout_seconds:g} seconds"],
        }
    (root / "pilot" / "one_job_result.json").write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())

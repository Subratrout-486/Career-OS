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
    jobs = json.loads((root / "pilot" / "pilot_jobs.json").read_text(encoding="utf-8"))
    profile = load_profile(str(root / "config" / "master_profile.md"))
    runtime = CareerOS(vault=VAULT_SNAPSHOT, write_to_notion=False)
    outputs = []
    timeout_seconds = float(os.getenv("PILOT_TIMEOUT_SECONDS", "180"))
    for index, item in enumerate(jobs, start=1):
        job = Job.model_validate(item)
        print(f"[{index}/{len(jobs)}] processing {job.company} — {job.title}", flush=True)
        try:
            result = await asyncio.wait_for(
                runtime.process(profile, job), timeout=timeout_seconds
            )
            serialized = result.model_dump(mode="json")
        except asyncio.TimeoutError:
            serialized = {
                "job": job.model_dump(mode="json"),
                "application_mode": "REVIEW_REQUIRED",
                "application_mode_reason": "Pilot processing timed out before a complete Career OS result was produced.",
                "application_mode_blockers": [
                    f"pilot timeout after {timeout_seconds:g} seconds"
                ],
                "review_status": "PILOT_TIMEOUT",
                "errors": [
                    f"PILOT_TIMEOUT: processing exceeded {timeout_seconds:g} seconds"
                ],
            }
        outputs.append(serialized)
        print(
            f"[{index}/{len(jobs)}] finished mode={serialized.get('application_mode')} status={serialized.get('review_status')}",
            flush=True,
        )
    (root / "pilot" / "pilot_results.json").write_text(
        json.dumps(outputs, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    summary = {
        "discovered": len(outputs),
        "active": sum(1 for x in outputs if x.get("job_verification", {}).get("active")),
        "apply": sum(1 for x in outputs if x.get("fit", {}).get("recommendation") == "APPLY"),
        "auto_apply": sum(1 for x in outputs if x.get("application_mode") == "AUTO_APPLY"),
        "review_required": sum(1 for x in outputs if x.get("application_mode") == "REVIEW_REQUIRED"),
        "do_not_apply": sum(1 for x in outputs if x.get("application_mode") == "DO_NOT_APPLY"),
        "actually_submitted": 0,
        "records_created_or_updated": 0,
        "jobs": [
            {
                "company": x["job"]["company"],
                "title": x["job"]["title"],
                "url": x["job"].get("url"),
                "active_status": x.get("job_verification", {}).get("status"),
                "fit_score": x.get("fit", {}).get("fit_score"),
                "recommendation": x.get("fit", {}).get("recommendation"),
                "application_mode": x.get("application_mode"),
                "application_mode_reason": x.get("application_mode_reason"),
                "blockers": x.get("application_mode_blockers", []),
                "review_status": x.get("review_status"),
                "resume_files": x.get("resume_files", []),
                "errors": x.get("errors", []),
            }
            for x in outputs
        ],
    }
    (root / "pilot" / "pilot_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())

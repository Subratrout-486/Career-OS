#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from career_os.conductor_runtime import ConductorRuntime
from career_os.models import Job
from career_os.orchestrator import CareerOS
from career_os.pipeline_adapter import ControlledCareerPipeline


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-json", required=True)
    parser.add_argument("--profile", default="config/master_profile.md")
    parser.add_argument("--result-output", default="conductor-e2e-result.json")
    args = parser.parse_args()

    job = Job.model_validate(json.loads(Path(args.job_json).read_text(encoding="utf-8")))
    profile = Path(args.profile).read_text(encoding="utf-8")
    runtime = ConductorRuntime()
    health = await runtime.health()
    if health.get("ok") is not True and health.get("configured") is not True:
        raise SystemExit(f"CONDUCTOR_NOT_READY: {health}")

    pipeline = CareerOS(runtime=runtime, write_to_notion=False)
    controlled = ControlledCareerPipeline(pipeline=pipeline)
    result = await controlled.process(profile, job)
    payload = result.model_dump(mode="json")
    payload["conductor_health"] = health
    payload["provider_used"] = runtime.last_provider_used
    Path(args.result_output).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if result.review_status in {"AI_PROVIDER_UNAVAILABLE", "EVIDENCE_VAULT_UNAVAILABLE"}:
        raise SystemExit(f"CAREER_OS_E2E_BLOCKED: {result.review_status}")
    if result.fit is None:
        raise SystemExit("CAREER_OS_E2E_FAILED: fit stage did not produce a result")
    if not runtime.last_provider_used:
        raise SystemExit("CAREER_OS_E2E_FAILED: Conductor provider usage was not recorded")

    print("CAREER_OS_E2E_PASSED")
    print(f"REVIEW_STATUS={result.review_status}")
    print(f"PROVIDER={runtime.last_provider_used}")
    print(f"FIT_SCORE={result.fit.fit_score}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

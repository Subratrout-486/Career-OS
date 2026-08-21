#!/usr/bin/env python3
"""Run the Career OS pipeline through one explicitly selected AI provider.

This is the direct replacement for the old Conductor E2E path. It never uses
Conductor and never permits provider fallback in primary fit/resume generation.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from career_os.direct_provider_runtime import DirectProviderRuntime
from career_os.models import Job
from career_os.orchestrator import CareerOS


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-json", required=True)
    parser.add_argument("--profile", default="config/master_profile.md")
    parser.add_argument("--result-output", default="direct-provider-e2e-result.json")
    parser.add_argument("--offline-vault", action="store_true")
    args = parser.parse_args()

    job = Job.model_validate(json.loads(Path(args.job_json).read_text(encoding="utf-8")))
    profile = Path(args.profile).read_text(encoding="utf-8")
    runtime = DirectProviderRuntime()

    vault = None
    if args.offline_vault:
        from career_os.evidence_vault_snapshot import VAULT_SNAPSHOT
        vault = VAULT_SNAPSHOT

    pipeline = CareerOS(
        vault=vault,
        runtime=runtime,
        write_to_notion=False,
    )
    result = await pipeline.process(profile, job)
    payload = result.model_dump(mode="json")
    payload["provider_used"] = runtime.last_provider_used
    payload["provider_policy"] = "STRICT_DIRECT_NO_FALLBACK"
    Path(args.result_output).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    if result.review_status in {"AI_PROVIDER_UNAVAILABLE", "EVIDENCE_VAULT_UNAVAILABLE"}:
        raise SystemExit(f"CAREER_OS_E2E_BLOCKED: {result.review_status}")
    if result.fit is None:
        raise SystemExit("CAREER_OS_E2E_FAILED: fit stage did not produce a result")
    if not runtime.last_provider_used:
        raise SystemExit("CAREER_OS_E2E_FAILED: direct provider usage was not recorded")

    print("CAREER_OS_DIRECT_PROVIDER_E2E_PASSED")
    print(f"PROVIDER={runtime.last_provider_used}")
    print(f"FIT_SCORE={result.fit.fit_score}")
    print(f"REVIEW_STATUS={result.review_status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

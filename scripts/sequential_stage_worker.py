#!/usr/bin/env python3
"""Run an isolated Career OS department without invoking downstream stages."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from career_os.agents import AgentRuntime
from career_os.evidence_loader import VaultLoadError, load_evidence_vault
from career_os.jd_analyzer import analyze_jd, requirements_for_retrieval
from career_os.models import FitReport, Job
from career_os.orchestrator import collect_relevant_evidence, load_profile
from career_os.pipeline_state import Stage, PipelineStatus, begin_attempt, complete, fail

MAX_JOBS = 5
STAGE_MAX_JOBS = {Stage.MATCHING: 1}
ROOT = Path("jobs")


def records_for(status: PipelineStatus) -> list[Path]:
    found: list[Path] = []
    for path in sorted(ROOT.rglob("*.json")):
        if any(part.endswith("_runtime") for part in path.parts):
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(record, dict) and str(record.get("status") or record.get("pipeline_status") or "") == status.value:
            found.append(path)
    return found[:MAX_JOBS]


def _job_from_record(record: dict[str, Any]) -> Job:
    """Convert the durable job record to the production Job model."""
    payload = dict(record)
    payload["description"] = str(
        payload.get("jd_text") or payload.get("description") or ""
    )
    return Job.model_validate(payload)


async def process_matching(
    record: dict[str, Any],
    *,
    profile_path: str = "config/master_profile.md",
    runtime: AgentRuntime | None = None,
    vault: list[Any] | None = None,
) -> dict[str, Any]:
    """Run the existing production matching implementation and stop at Stage 3.

    The preparation below intentionally mirrors ``CareerOS.process`` through its
    real ``AgentRuntime.fit`` call. No resume, Notion, readiness, browser, or
    application code is called from this boundary.
    """
    stage = Stage.MATCHING
    updated = begin_attempt(record, stage)
    try:
        job = _job_from_record(updated)
        jd_analysis = analyze_jd(job)
        if vault is None:
            vault = load_evidence_vault(use_cache=True).items
        requirements = requirements_for_retrieval(jd_analysis)
        fit_evidence_pack = collect_relevant_evidence(
            requirements, vault, include_all_usable=False
        )
        profile = load_profile(profile_path)
        active_runtime = runtime or AgentRuntime()
        fit = await active_runtime.fit(
            profile, job, fit_evidence_pack, jd_analysis
        )
        if not isinstance(fit, FitReport):
            fit = FitReport.model_validate(fit)
        updated["fit_report"] = fit.model_dump(mode="json")
        updated["match_score"] = fit.fit_score
        updated["match_explanation"] = fit.rationale
        updated["matching_recommendation"] = fit.recommendation
        updated["matching_band"] = fit.band
        updated["matching_provider"] = active_runtime.last_provider_used
        updated["matching_evidence_count"] = len(fit_evidence_pack)
        updated["matching_jd_analysis"] = jd_analysis.model_dump(mode="json")
        return complete(updated, stage)
    except VaultLoadError as exc:
        return fail(updated, stage, exc, "MATCH_EVIDENCE_UNAVAILABLE")
    except Exception as exc:  # noqa: BLE001 — retain durable retry state
        return fail(updated, stage, exc, "MATCHING_FAILED")


def process(record: dict[str, Any], stage: Stage) -> dict[str, Any]:
    """Compatibility path for non-Stage-3 tests; Stage 3 is async and real."""
    if stage is Stage.MATCHING:
        return asyncio.run(process_matching(record))
    updated = begin_attempt(record, stage)
    if stage is Stage.RESUME_RECOMMENDATION:
        ready = bool(str(updated.get("recommended_resume") or updated.get("resume_path") or "").strip())
        return complete(updated, stage) if ready else fail(updated, stage, "recommended resume is not present", "RESUME_NOT_AVAILABLE")
    if stage is Stage.NOTION_SYNC:
        ready = bool(updated.get("notion_synced") or updated.get("notion_page_id") or updated.get("notion_job_page_id"))
        return complete(updated, stage) if ready else fail(updated, stage, "Notion record is not present", "NOTION_NOT_SYNCED")
    if stage is Stage.READY_TO_APPLY_VALIDATION:
        conditions = {
            "usable_jd": str(updated.get("jd_status") or "").lower() == "complete" and bool(str(updated.get("jd_text") or updated.get("description") or "").strip()),
            "successful_match": str(updated.get("status")) == PipelineStatus.NOTION_READY.value and (updated.get("match_score") is not None or bool(updated.get("match_explanation"))),
            "recommended_resume": bool(str(updated.get("recommended_resume") or updated.get("resume_path") or "").strip()),
            "valid_application_url": bool(str(updated.get("apply_url") or updated.get("application_url") or updated.get("url") or "").strip()),
            "truth_guard": bool(updated.get("truth_guard_satisfied")),
            "evidence_provenance": bool(updated.get("evidence_satisfied") or updated.get("provenance_satisfied") or updated.get("evidence_provenance_satisfied")),
        }
        if all(conditions.values()):
            return complete(updated, stage)
        missing = ",".join(key for key, value in conditions.items() if not value)
        return fail(updated, stage, f"readiness prerequisites missing: {missing}", "READINESS_PREREQUISITES_MISSING")
    raise ValueError(f"unsupported stage: {stage.value}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stage",
        choices=[stage.value for stage in Stage if stage not in {Stage.DISCOVERY_INTAKE, Stage.JD_ENRICHMENT, Stage.AUTO_APPLY}],
        required=True,
    )
    parser.add_argument("--max-jobs", type=int, default=MAX_JOBS)
    parser.add_argument("--profile", default="config/master_profile.md")
    args = parser.parse_args()
    stage = Stage(args.stage)
    contract_input = {
        Stage.MATCHING: PipelineStatus.JD_READY,
        Stage.RESUME_RECOMMENDATION: PipelineStatus.MATCHED,
        Stage.NOTION_SYNC: PipelineStatus.RESUME_READY,
        Stage.READY_TO_APPLY_VALIDATION: PipelineStatus.NOTION_READY,
    }[stage]
    limit = min(args.max_jobs, STAGE_MAX_JOBS.get(stage, MAX_JOBS), MAX_JOBS)
    paths = records_for(contract_input)[: max(0, limit)]
    report: dict[str, Any] = {
        "stage": stage.value,
        "input_status": contract_input.value,
        "max_jobs": limit,
        "processed": 0,
        "success": 0,
        "pending": 0,
        "records": [],
    }
    for path in paths:
        original = json.loads(path.read_text(encoding="utf-8"))
        if stage is Stage.MATCHING:
            updated = asyncio.run(process_matching(original, profile_path=args.profile))
        else:
            updated = process(original, stage)
        path.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        success = updated["status"] == {
            Stage.MATCHING: PipelineStatus.MATCHED,
            Stage.RESUME_RECOMMENDATION: PipelineStatus.RESUME_READY,
            Stage.NOTION_SYNC: PipelineStatus.NOTION_READY,
            Stage.READY_TO_APPLY_VALIDATION: PipelineStatus.READY_TO_APPLY,
        }[stage].value
        report["processed"] += 1
        report["success" if success else "pending"] += 1
        item = {
            "path": str(path),
            "job_id": updated.get("job_id"),
            "input_state": original.get("status"),
            "output_state": updated.get("status"),
            "error_code": updated.get("error_code"),
        }
        if stage is Stage.MATCHING:
            item.update({
                "match_score": updated.get("match_score"),
                "matching_recommendation": updated.get("matching_recommendation"),
                "matching_band": updated.get("matching_band"),
                "matching_provider": updated.get("matching_provider"),
            })
        report["records"].append(item)
    runtime = ROOT / "sequential_runtime"
    runtime.mkdir(exist_ok=True)
    (runtime / f"{stage.value.lower()}.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

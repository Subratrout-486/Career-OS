#!/usr/bin/env python3
"""Dispatch pre-gated Career OS browser tasks through the Manus API.

The script deliberately consumes an explicit manifest created by the trusted
Career OS pipeline. It does not infer a resume file from job title text, scrape
unverified jobs, or convert review-required items into applications. A durable
state store prevents a rerun from creating a second task for the same exact
application URL and tailored-resume fingerprint.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from career_os.browser_execution_manifest import ManifestGenerationError, validate_browser_execution_record
from career_os.browser_execution_state import BrowserExecutionStateStore, ExecutionStateError
from career_os.manus_browser_runner import ManusApiError, ManusBrowserRunner


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_truthy(record: dict[str, Any], key: str) -> None:
    if record.get(key) is not True:
        raise ManusApiError(f"{key}=true is required for browser dispatch")


def validate_record(record: dict[str, Any]) -> tuple[dict[str, str], Path, str]:
    """Validate every deterministic prerequisite before any API request."""
    if str(record.get("application_mode") or "") != "AUTO_APPLY":
        raise ManusApiError("application_mode=AUTO_APPLY is required for browser dispatch")
    if str(record.get("review_status") or "") != "READY_FOR_REVIEW":
        raise ManusApiError("review_status=READY_FOR_REVIEW is required for browser dispatch")
    for key in (
        "job_active", "ghost_job_risk_acceptable", "manus_recommendation_apply", "truth_guard_passed",
        "ats_passed", "recruiter_review_passed", "gemini_adversarial_passed", "gemini_adversarial_apply",
        "design_qa_passed", "complete_form_verified", "required_answers_verified", "resume_attachment_verified",
        "resume_sha256_verified",
    ):
        _require_truthy(record, key)
    if not str(record.get("gemini_adversarial_provider") or "").lower().startswith("gemini"):
        raise ManusApiError("gemini_adversarial_provider must identify the mandatory Gemini reviewer")
    if record.get("human_controlled_blockers"):
        raise ManusApiError("human_controlled_blockers must be empty before browser dispatch")

    application = {
        "company": str(record.get("company") or "").strip(),
        "title": str(record.get("title") or "").strip(),
        "job_url": str(record.get("job_url") or "").strip(),
        "application_id": str(record.get("application_id") or "").strip(),
    }
    missing = [name for name, value in application.items() if not value]
    if missing:
        raise ManusApiError("manifest missing required application fields: " + ", ".join(missing))

    resume_path = Path(str(record.get("resume_path") or ""))
    if not resume_path.is_file() or resume_path.suffix.lower() not in {".pdf", ".docx"}:
        raise ManusApiError("resume_path must point to the exact existing PDF or DOCX artifact")
    manifest_hash = str(record.get("resume_sha256") or "").lower()
    computed_hash = _sha256(resume_path)
    if manifest_hash != computed_hash:
        raise ManusApiError("resume_sha256 does not match the exact resume artifact")
    return application, resume_path, computed_hash


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path, help="Verified browser-execution manifest JSON.")
    parser.add_argument("--results", type=Path, default=Path("browser_execution_results.json"), help="JSON outcome path for the workflow artifact.")
    parser.add_argument("--state", type=Path, default=Path("browser_execution_state.json"), help="Durable task-state JSON preserved between reruns.")
    args = parser.parse_args()

    if os.getenv("CAREER_OS_EXECUTION_ENABLED", "false").casefold() != "true":
        raise SystemExit("CAREER_OS_EXECUTION_ENABLED=true is required; no task was created.")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    records = manifest.get("applications")
    if not isinstance(records, list) or not records:
        raise SystemExit("Manifest must contain a non-empty applications list; no task was created.")

    runner = ManusBrowserRunner()
    state = BrowserExecutionStateStore(args.state)
    results: list[dict[str, Any]] = []
    for record in records:
        try:
            validate_browser_execution_record(record)
            application, resume_path, resume_hash = validate_record(record)
            reserved, existing = state.reserve(record, stage="execution")
            if not reserved:
                prior = (existing.get("execution") or {}) if isinstance(existing, dict) else {}
                results.append({
                    "application_id": application["application_id"], "job_url": application["job_url"],
                    "resume_sha256": resume_hash, "status": "DUPLICATE_SKIPPED",
                    "task_id": prior.get("task_id"), "task_url": prior.get("task_url"),
                    "reason": "A task already exists for this application and exact tailored-resume fingerprint.",
                })
                continue
            try:
                created = runner.create_execution_task(application, resume_path, resume_sha256=resume_hash)
            except Exception as exc:
                state.release(record, stage="execution", reason=str(exc))
                raise
            state.record_task(record, stage="execution", task_id=str(created.get("task_id") or ""), task_url=str(created.get("task_url") or ""))
            results.append({
                "application_id": application["application_id"], "job_url": application["job_url"],
                "resume_sha256": resume_hash, "status": "TASK_CREATED",
                "task_id": created.get("task_id"), "task_url": created.get("task_url"),
            })
        except (ManusApiError, ManifestGenerationError, ExecutionStateError, ValueError, TypeError) as exc:
            results.append({
                "application_id": str(record.get("application_id") or ""),
                "job_url": str(record.get("job_url") or ""),
                "status": "BLOCKED", "reason": str(exc),
            })

    args.results.write_text(json.dumps({"results": results, "state_path": str(args.state)}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"results": results, "state_path": str(args.state)}, indent=2))
    return 0 if all(item["status"] in {"TASK_CREATED", "DUPLICATE_SKIPPED"} for item in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())

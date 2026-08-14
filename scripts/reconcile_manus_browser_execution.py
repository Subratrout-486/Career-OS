#!/usr/bin/env python3
"""Poll Manus execution tasks and reconcile verified browser submission outcomes.

A completed agent task is not evidence of an application. This command keeps
records in Review unless the structured result proves the manifest's exact
resume SHA-256 and captures a confirmation from an employer, ATS, or LinkedIn
surface. It never retries or creates a task.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any, Mapping

from career_os.applications import ApplicationsTracker
from career_os.browser_execution_state import BrowserExecutionStateStore, ExecutionStateError
from career_os.browser_outcomes import decide_browser_outcome
from career_os.manus_browser_runner import ManusApiError, ManusBrowserRunner


def _expected_hash(state_record: Mapping[str, Any]) -> str:
    fingerprint = str(state_record.get("fingerprint") or "")
    parts = fingerprint.rsplit("|", 1)
    if len(parts) != 2 or len(parts[1]) != 64:
        raise ExecutionStateError("EXECUTION_STATE_INVALID: execution record lacks an exact resume SHA-256 fingerprint")
    return parts[1]


def _normalise_outcome(application_id: str, expected_resume_hash: str, outcome: Mapping[str, Any]) -> dict[str, Any]:
    """Add hard blockers for any task result that diverges from its manifest."""
    prepared = dict(outcome)
    blockers = [str(item).strip() for item in prepared.get("blockers") or [] if str(item).strip()]
    if str(prepared.get("application_record_id") or "").strip() != application_id:
        blockers.append("structured browser outcome does not match the durable Application record ID")
    if prepared.get("resume_attachment_verified") is not True:
        blockers.append("exact tailored-resume attachment was not verified by the browser")
    if prepared.get("resume_sha256_verified") is not True:
        blockers.append("exact tailored-resume SHA-256 was not verified by the browser")
    if str(prepared.get("selected_resume_sha256") or "").lower() != expected_resume_hash:
        blockers.append("browser-selected resume SHA-256 does not match the dispatched tailored resume")
    if prepared.get("normal_upload_attempted") is not True:
        blockers.append("normal tailored-resume upload was not attempted")
    if prepared.get("normal_upload_succeeded") is not True:
        fallback_attempted = prepared.get("file_chooser_retry_attempted") is True or prepared.get("input_retry_attempted") is True
        fallback_succeeded = prepared.get("file_chooser_retry_succeeded") is True or prepared.get("input_retry_succeeded") is True
        if not fallback_attempted:
            blockers.append("force-resume-upload fallback was not attempted after normal upload failure")
        elif not fallback_succeeded:
            blockers.append("force-resume-upload fallback did not confirm a successful exact tailored-resume upload")
    prepared["application_id"] = application_id
    prepared["application_record_id"] = application_id
    prepared["blockers"] = list(dict.fromkeys(blockers))
    decision = decide_browser_outcome(prepared)
    # State must never call a blocked claimed-submission confirmation. Preserve
    # evidence for human review but make its state non-submission explicit.
    if decision.application_status != "Applied" and str(prepared.get("status") or "").upper() == "SUBMITTED":
        prepared["status"] = "REVIEW_REQUIRED"
    return prepared


async def reconcile_state(state: BrowserExecutionStateStore) -> list[dict[str, Any]]:
    runner = ManusBrowserRunner()
    tracker = ApplicationsTracker()
    entries = state.load().get("applications", {})
    results: list[dict[str, Any]] = []
    for application_id, current in entries.items():
        if not isinstance(current, Mapping):
            continue
        execution = current.get("execution")
        if not isinstance(execution, Mapping) or not str(execution.get("task_id") or "").strip():
            continue
        execution_status = str(execution.get("status") or "").upper()
        if execution_status in {"SUBMITTED_CONFIRMED", "RECONCILED_REVIEW", "BLOCKED"}:
            results.append({
                "application_id": str(application_id),
                "task_id": execution.get("task_id"),
                "status": "TERMINAL_SKIPPED",
                "state": execution_status,
            })
            continue
        task_id = str(execution["task_id"])
        try:
            snapshot = runner.inspect_task(task_id)
            outcome = runner.structured_value(snapshot)
            if outcome is None:
                state.record_snapshot(str(application_id), stage="execution", snapshot=snapshot)
                results.append({
                    "application_id": str(application_id), "task_id": task_id,
                    "status": "BROWSER_CONNECTION_REQUIRED" if snapshot.get("browser_connection_required") else "PENDING",
                    "agent_status": snapshot.get("agent_status"),
                    "browser_connection_required": snapshot.get("browser_connection_required"),
                    "browser_clients_available": snapshot.get("browser_clients_available"),
                    "errors": snapshot.get("errors"),
                })
                continue
            prepared = _normalise_outcome(str(application_id), _expected_hash(current), outcome)
            persisted = await tracker.record_browser_outcome(str(application_id), prepared)
            state.record_snapshot(str(application_id), stage="execution", snapshot=snapshot, outcome=prepared)
            results.append({
                "application_id": str(application_id), "task_id": task_id,
                "status": "RECORDED", "outcome": prepared,
                "application_status": persisted.get("application_status"),
                "evidence": persisted.get("evidence"), "blockers": persisted.get("blockers"),
            })
        except (ManusApiError, ExecutionStateError, ValueError, TypeError) as exc:
            results.append({"application_id": str(application_id), "task_id": task_id, "status": "ERROR", "reason": str(exc)})
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=Path("browser_execution_state.json"), help="Durable state JSON created by browser dispatch.")
    parser.add_argument("--results", type=Path, default=Path("browser_submission_reconciliation.json"))
    args = parser.parse_args()
    try:
        results = asyncio.run(reconcile_state(BrowserExecutionStateStore(args.state)))
    except (ExecutionStateError, ManusApiError, ValueError, TypeError) as exc:
        results = [{"status": "ERROR", "reason": str(exc)}]
    payload = {"results": results, "state_path": str(args.state)}
    args.results.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if all(item.get("status") in {"RECORDED", "PENDING", "BROWSER_CONNECTION_REQUIRED", "TERMINAL_SKIPPED"} for item in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())

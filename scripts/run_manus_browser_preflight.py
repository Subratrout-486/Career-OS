#!/usr/bin/env python3
"""Run the Career OS Manus browser-preflight lifecycle for one pipeline result.

``start`` creates an inspection-only browser task. ``poll`` consumes a completed
structured observation, preserves it in the durable state file, and creates a
verified browser-execution manifest only when the existing Career OS decision
returns AUTO_APPLY. It never submits an application itself.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from career_os.browser_execution_manifest import ManifestGenerationError, generate_browser_execution_manifest
from career_os.browser_execution_state import BrowserExecutionStateStore, ExecutionStateError
from career_os.browser_preflight import (
    BrowserPreflightError,
    build_preflight_request,
    evaluate_preflight_observation,
)
from career_os.manus_browser_runner import ManusApiError, ManusBrowserRunner


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _approved_questions(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, dict):
        value = value.get("questions") or value.get("results") or []
    if not isinstance(value, list):
        raise ValueError("Approved-questions JSON must be a list or an object with a questions list.")
    return [dict(item) for item in value if isinstance(item, dict)]


def _state_record(request: dict[str, Any]) -> dict[str, str]:
    identity = request["application"]
    return {
        "application_id": str(identity["application_id"]),
        "job_url": str(identity["job_url"]),
        "resume_sha256": str(request["resume_sha256"]),
    }


def start(result: dict[str, Any], *, approved_questions: list[dict[str, Any]], state: BrowserExecutionStateStore) -> dict[str, Any]:
    request = build_preflight_request(result, approved_questions=approved_questions)
    record = _state_record(request)
    reserved, existing = state.reserve(record, stage="preflight")
    if not reserved:
        prior = (existing.get("preflight") or {}) if isinstance(existing, dict) else {}
        return {
            "status": "DUPLICATE_SKIPPED",
            "application_id": record["application_id"],
            "task_id": prior.get("task_id"),
            "task_url": prior.get("task_url"),
            "reason": "A browser preflight already exists for this application and exact tailored-resume fingerprint.",
        }
    runner = ManusBrowserRunner()
    try:
        created = runner.create_preflight_task(
            request["application"],
            request["resume_path"],
            resume_sha256=request["resume_sha256"],
            approved_questions=request["approved_questions"],
        )
    except Exception as exc:
        state.release(record, stage="preflight", reason=str(exc))
        raise
    state.record_task(record, stage="preflight", task_id=str(created.get("task_id") or ""), task_url=str(created.get("task_url") or ""))
    return {
        "status": "TASK_CREATED",
        "application_id": record["application_id"],
        "task_id": created.get("task_id"),
        "task_url": created.get("task_url"),
        "resume_filename": request["resume_filename"],
        "resume_sha256": request["resume_sha256"],
    }


def poll(
    result: dict[str, Any], *, approved_questions: list[dict[str, Any]], state: BrowserExecutionStateStore, manifest_output: Path | None
) -> dict[str, Any]:
    request = build_preflight_request(result, approved_questions=approved_questions)
    record = _state_record(request)
    current = state.load().get("applications", {}).get(record["application_id"])
    preflight = (current or {}).get("preflight") if isinstance(current, dict) else None
    task_id = str((preflight or {}).get("task_id") or "").strip()
    if not task_id:
        raise ExecutionStateError("PREFLIGHT_POLL_BLOCKED: no preflight task exists for this application fingerprint")

    runner = ManusBrowserRunner()
    snapshot = runner.inspect_task(task_id)
    observation = runner.structured_value(snapshot)
    if observation is None:
        connection = {"status": "NOT_REQUIRED"}
        if snapshot.get("browser_connection_required") is True:
            # The client identifier exists only in the runner while confirming
            # this one supported Browser Operator action.  The durable state
            # receives only safe readiness/blocker facts below.
            connection = runner.confirm_authorized_browser(task_id, snapshot)
        public_snapshot = runner.public_browser_snapshot(snapshot)
        public_snapshot["browser_session_status"] = connection["status"]
        if connection.get("blocker"):
            public_snapshot["browser_session_blocker"] = connection["blocker"]
        state.record_snapshot(record["application_id"], stage="preflight", snapshot=public_snapshot)
        selected = connection["status"] == "AUTHORIZED_BROWSER_SELECTED"
        status = "PENDING" if selected or snapshot.get("browser_connection_required") is not True else "BROWSER_CONNECTION_REQUIRED"
        return {
            "status": status,
            "application_id": record["application_id"],
            "task_id": task_id,
            "browser_connection_required": snapshot.get("browser_connection_required"),
            "browser_session_status": connection["status"],
            "browser_session_blocker": connection.get("blocker"),
            "browser_clients_available": snapshot.get("browser_clients_available"),
            "agent_status": snapshot.get("agent_status"),
            "errors": public_snapshot.get("errors"),
        }

    evaluation = evaluate_preflight_observation(result, observation, approved_questions=approved_questions)
    output: dict[str, Any] = {
        "status": evaluation.status,
        "application_id": record["application_id"],
        "task_id": task_id,
        "browser_context": evaluation.browser_context,
        "application_mode": evaluation.decision.mode.value,
        "application_mode_reason": evaluation.decision.reason,
        "application_mode_blockers": list(evaluation.decision.blockers),
        "question_feedback": evaluation.required_question_payload,
    }
    state.record_snapshot(record["application_id"], stage="preflight", snapshot=snapshot, outcome=output)
    if evaluation.status != "AUTO_APPLY_READY":
        return output
    if manifest_output is None:
        raise BrowserPreflightError("PREFLIGHT_BLOCKED: --manifest-output is required for an AUTO_APPLY_READY preflight")
    manifest = generate_browser_execution_manifest(
        evaluation.prepared_result,
        browser_context=evaluation.browser_context,
        output_path=manifest_output,
    )
    output["manifest_path"] = manifest["manifest_path"]
    output["manifest_record_count"] = len(manifest.get("applications") or [])
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("start", "poll"))
    parser.add_argument("--pipeline-result", required=True, type=Path, help="Full Career OS pipeline result JSON with durable Notion IDs.")
    parser.add_argument("--approved-questions", type=Path, help="Optional user-approved Application Questions export JSON.")
    parser.add_argument("--state", type=Path, default=Path("browser_execution_state.json"), help="Durable state JSON preserved between workflow runs.")
    parser.add_argument("--manifest-output", type=Path, help="Output path for an AUTO_APPLY verified execution manifest (poll only).")
    parser.add_argument("--output", type=Path, default=Path("browser_preflight_result.json"))
    args = parser.parse_args()

    try:
        result = _load_object(args.pipeline_result)
        approved = _approved_questions(args.approved_questions)
        state = BrowserExecutionStateStore(args.state)
        if args.command == "start":
            output = start(result, approved_questions=approved, state=state)
        else:
            output = poll(result, approved_questions=approved, state=state, manifest_output=args.manifest_output)
    except (BrowserPreflightError, ExecutionStateError, ManusApiError, ManifestGenerationError, ValueError, TypeError) as exc:
        output = {"status": "BLOCKED", "reason": str(exc)}
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))
    return 0 if output.get("status") in {"TASK_CREATED", "DUPLICATE_SKIPPED", "PENDING", "BROWSER_CONNECTION_REQUIRED", "AUTO_APPLY_READY", "REVIEW_REQUIRED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())

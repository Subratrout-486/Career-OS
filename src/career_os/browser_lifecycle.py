"""Automatic, resumable Career OS Manus browser lifecycle coordination.

The coordinator consumes one self-contained workspace whose artifacts were
produced by a trusted Career OS intake workflow.  It never searches for a
resume, guesses an answer, or bypasses the existing preflight/manifest/
reconciliation checks.  A workspace is safe to carry across workflow runs
because every candidate result, its exact tailored-resume files, generated
manifest, and state file travel together.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping, Sequence

from career_os.applications import ApplicationsTracker
from career_os.browser_execution_state import BrowserExecutionStateStore, ExecutionStateError
from career_os.browser_preflight import BrowserPreflightError
from career_os.manus_browser_runner import ManusApiError

PreflightStart = Callable[..., dict[str, Any]]
PreflightPoll = Callable[..., dict[str, Any]]
DispatchRecords = Callable[..., list[dict[str, Any]]]
ReconcileState = Callable[[BrowserExecutionStateStore], Awaitable[list[dict[str, Any]]]]


class BrowserLifecycleError(ValueError):
    """Raised when a cross-run lifecycle workspace is malformed or unsafe."""


@dataclass(frozen=True)
class LifecycleWorkspace:
    root: Path

    @property
    def candidates_dir(self) -> Path:
        return self.root / "pipeline_results"

    @property
    def resumes_dir(self) -> Path:
        return self.root / "generated_resumes"

    @property
    def manifests_dir(self) -> Path:
        return self.root / "browser_execution_manifests"

    @property
    def state_path(self) -> Path:
        return self.root / "browser_execution_state.json"

    @property
    def summary_path(self) -> Path:
        return self.root / "browser_lifecycle_summary.json"

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifests_dir.mkdir(parents=True, exist_ok=True)


def _json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BrowserLifecycleError(f"LIFECYCLE_BLOCKED: cannot read candidate {path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise BrowserLifecycleError(f"LIFECYCLE_BLOCKED: candidate {path} must be a JSON object")
    return dict(value)


def _candidate_paths(workspace: LifecycleWorkspace) -> list[Path]:
    paths = sorted(path for path in workspace.candidates_dir.rglob("*.json") if path.is_file())
    if not paths:
        raise BrowserLifecycleError("LIFECYCLE_BLOCKED: no pipeline-result candidates were supplied")
    return paths


def _rebase_resume_paths(result: Mapping[str, Any], workspace: LifecycleWorkspace) -> dict[str, Any]:
    """Rebase only the result's declared current PDF/DOCX into its workspace.

    Source workflow runners may persist absolute temporary paths.  The artifact
    handoff is allowed to restore only an artifact with the same declared file
    name.  Ambiguity, missing files, and any unrecognised resume key are left to
    the normal ``select_current_resume`` gate, which fails closed.
    """

    prepared = dict(result)
    raw_resume_files = prepared.get("resume_files")
    if not isinstance(raw_resume_files, Mapping):
        return prepared
    resume_files = dict(raw_resume_files)
    for key in ("pdf", "docx"):
        raw_path = resume_files.get(key)
        if not raw_path:
            continue
        declared = Path(str(raw_path))
        if declared.is_file():
            continue
        matches = [path for path in workspace.resumes_dir.rglob(declared.name) if path.is_file()]
        if len(matches) == 1:
            resume_files[key] = str(matches[0].resolve())
        elif len(matches) == 0:
            continue
        else:
            raise BrowserLifecycleError(
                "LIFECYCLE_BLOCKED: more than one persisted resume matches the declared tailored-resume filename"
            )
    prepared["resume_files"] = resume_files
    return prepared


def _application_id(result: Mapping[str, Any]) -> str:
    value = str(result.get("application_page_id") or result.get("application_id") or "").strip()
    if not value:
        raise BrowserLifecycleError("LIFECYCLE_BLOCKED: candidate has no durable Application record ID")
    return value


def _manifest_path(workspace: LifecycleWorkspace, result: Mapping[str, Any]) -> Path:
    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in _application_id(result))
    return workspace.manifests_dir / f"{safe}.json"


def _continuation_required(state: Mapping[str, Any]) -> bool:
    """Return true only for an unfinished Manus task that may later progress."""

    applications = state.get("applications") if isinstance(state, Mapping) else {}
    if not isinstance(applications, Mapping):
        return False
    for current in applications.values():
        if not isinstance(current, Mapping):
            continue
        preflight = current.get("preflight")
        execution = current.get("execution")
        preflight_status = str(preflight.get("status") or "").upper() if isinstance(preflight, Mapping) else ""
        execution_status = str(execution.get("status") or "").upper() if isinstance(execution, Mapping) else ""
        if execution_status in {"TASK_CREATED", "RUNNING", "WAITING", "RECONCILIATION_PENDING"}:
            return True
        if preflight_status in {"TASK_CREATED", "RUNNING", "WAITING"}:
            return True
        if preflight_status == "READY_FOR_EXECUTION" and not execution_status:
            return True
    return False


def _as_results(value: object) -> list[dict[str, Any]]:
    return [dict(item) for item in value if isinstance(item, Mapping)] if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else []


def _ensure_application_record(result: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Repair a missing durable Applications record before browser preflight.

    Intake can successfully finish the expensive JD/resume pipeline while a
    transient Notion write fails. Previously that left the lifecycle artifact
    permanently unusable because the browser gate requires a real Application
    page ID. Recovery is intentionally narrow: reuse the canonical Applications
    record when possible, create one only when the result has an exact job URL,
    and remove only the transient tracking errors caused by the failed write.
    No browser task is created until the durable ID exists.
    """

    existing = str(result.get("application_page_id") or result.get("application_id") or "").strip()
    if existing:
        return result, existing

    job = result.get("job") or {}
    job_url = str(job.get("url") or result.get("application_url") or "").strip()
    if not job_url:
        raise BrowserLifecycleError(
            "LIFECYCLE_BLOCKED: candidate has no durable Application record ID and no exact job URL; "
            "application-record recovery is unsafe until a role-specific URL is available"
        )

    tracker = ApplicationsTracker()
    try:
        page_id = asyncio.run(tracker.create_review_record(result))
    except Exception as exc:
        raise BrowserLifecycleError(
            f"LIFECYCLE_BLOCKED: automatic Applications record recovery failed: {exc}"
        ) from exc
    if not page_id:
        raise BrowserLifecycleError(
            "LIFECYCLE_BLOCKED: Applications record recovery returned no page ID; "
            "verify NOTION_TOKEN and Applications database permissions"
        )

    repaired = dict(result)
    repaired["application_page_id"] = str(page_id)
    repaired["application_record_recovered"] = True
    # The pipeline may have marked itself NOTION_WRITE_FAILED/APPLICATIONS_TRACK_FAILED.
    # Those are exactly the transient failures repaired here; preserve all other
    # errors because they may still represent real application blockers.
    errors = repaired.get("errors")
    if isinstance(errors, list):
        repaired["errors"] = [
            item for item in errors
            if not str(item).startswith(("NOTION_WRITE_FAILED:", "APPLICATIONS_TRACK_FAILED:"))
        ]
    if repaired.get("review_status") == "NOTION_WRITE_FAILED":
        repaired["review_status"] = "READY_FOR_REVIEW"
    return repaired, str(page_id)


def run_automatic_lifecycle(
    workspace_root: str | Path,
    *,
    approved_questions: Sequence[Mapping[str, Any]] | None = None,
    preflight_start: PreflightStart,
    preflight_poll: PreflightPoll,
    dispatch_records: DispatchRecords,
    reconcile_state: ReconcileState,
) -> dict[str, Any]:
    """Advance all workspace candidates through preflight, dispatch, and poll.

    One call may create tasks, poll completed tasks, dispatch verified manifests,
    and reconcile confirmed submissions. It also repairs a missing Notion
    Applications page before preflight, so a transient downstream persistence
    failure cannot strand an otherwise valid lifecycle candidate.
    """

    workspace = LifecycleWorkspace(Path(workspace_root))
    workspace.ensure()
    state = BrowserExecutionStateStore(workspace.state_path)
    summary: dict[str, Any] = {
        "schema_version": "career_os_manus_browser_lifecycle/v1",
        "workspace": str(workspace.root),
        "candidates": [],
        "dispatch": [],
        "reconciliation": [],
        "continuation_required": False,
    }
    manifests: list[dict[str, Any]] = []

    for candidate_path in _candidate_paths(workspace):
        entry: dict[str, Any] = {"candidate_path": str(candidate_path)}
        try:
            result = _rebase_resume_paths(_json_object(candidate_path), workspace)
            result, application_id = _ensure_application_record(result)
            entry["application_id"] = application_id
            if result.get("application_record_recovered"):
                candidate_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
                entry["application_record_recovered"] = True

            manifest_path = _manifest_path(workspace, result)
            current = state.load().get("applications", {}).get(application_id, {})
            preflight = current.get("preflight", {}) if isinstance(current, Mapping) else {}
            execution = current.get("execution", {}) if isinstance(current, Mapping) else {}
            preflight_status = str(preflight.get("status") or "").upper() if isinstance(preflight, Mapping) else ""
            execution_status = str(execution.get("status") or "").upper() if isinstance(execution, Mapping) else ""

            if execution_status in {"TASK_CREATED", "RUNNING", "WAITING", "RECONCILIATION_PENDING", "SUBMITTED_CONFIRMED", "RECONCILED_REVIEW", "BLOCKED"}:
                entry["status"] = "EXECUTION_ALREADY_PERSISTED"
                entry["execution_state"] = execution_status
            elif preflight_status == "BLOCKED":
                entry["status"] = "PREFLIGHT_BLOCKED"
            elif preflight_status == "READY_FOR_EXECUTION" and manifest_path.is_file():
                manifest = _json_object(manifest_path)
                records = manifest.get("applications")
                if not isinstance(records, list):
                    raise BrowserLifecycleError("LIFECYCLE_BLOCKED: persisted manifest lacks applications")
                manifests.extend(dict(item) for item in records if isinstance(item, Mapping))
                entry["status"] = "PERSISTED_MANIFEST_READY"
                entry["manifest_path"] = str(manifest_path)
            else:
                start_result = preflight_start(result, approved_questions=list(approved_questions or ()), state=state)
                entry["preflight_start"] = start_result
                poll_result = preflight_poll(
                    result,
                    approved_questions=list(approved_questions or ()),
                    state=state,
                    manifest_output=manifest_path,
                )
                entry["preflight_poll"] = poll_result
                if poll_result.get("status") == "AUTO_APPLY_READY":
                    manifest = _json_object(manifest_path)
                    records = manifest.get("applications")
                    if not isinstance(records, list):
                        raise BrowserLifecycleError("LIFECYCLE_BLOCKED: generated manifest lacks applications")
                    manifests.extend(dict(item) for item in records if isinstance(item, Mapping))
                    entry["manifest_path"] = str(manifest_path)
        except (BrowserLifecycleError, BrowserPreflightError, ExecutionStateError, ManusApiError, ValueError, TypeError) as exc:
            entry["status"] = "BLOCKED"
            entry["reason"] = str(exc)
        summary["candidates"].append(entry)

    if manifests:
        summary["dispatch"] = dispatch_records(manifests, state=state)
    try:
        summary["reconciliation"] = asyncio.run(reconcile_state(state))
    except (ExecutionStateError, ManusApiError, ValueError, TypeError) as exc:
        summary["reconciliation"] = [{"status": "ERROR", "reason": str(exc)}]

    summary["continuation_required"] = _continuation_required(state.load())
    workspace.summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


__all__ = [
    "BrowserLifecycleError",
    "LifecycleWorkspace",
    "run_automatic_lifecycle",
]

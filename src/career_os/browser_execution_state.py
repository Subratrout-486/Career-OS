"""Durable, fail-closed state for Manus browser preflight and execution tasks."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

STATE_SCHEMA_VERSION = "career_os_manus_browser_execution_state/v1"
_ACTIVE_TASK_STATUSES = {"TASK_CREATED", "RUNNING", "WAITING", "RECONCILIATION_PENDING", "SUBMITTED_CONFIRMED", "RECONCILED_REVIEW", "READY_FOR_EXECUTION", "BLOCKED"}


class ExecutionStateError(ValueError):
    """Raised when a state file is malformed or conflicts with a new handoff."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BrowserExecutionStateStore:
    """Atomic local state store keyed by durable Application record ID.

    The store is deliberately supplied as an explicit workflow artifact or
    tracked operational file.  It never guesses a state location, and it refuses
    fingerprint drift rather than silently creating a second task for a changed
    resume or URL.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _blank(self) -> dict[str, Any]:
        return {"schema_version": STATE_SCHEMA_VERSION, "updated_at": _now(), "applications": {}}

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._blank()
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ExecutionStateError(f"EXECUTION_STATE_INVALID: cannot read {self.path}: {exc}") from exc
        if not isinstance(state, Mapping) or state.get("schema_version") != STATE_SCHEMA_VERSION:
            raise ExecutionStateError("EXECUTION_STATE_INVALID: unsupported state schema")
        if not isinstance(state.get("applications"), Mapping):
            raise ExecutionStateError("EXECUTION_STATE_INVALID: applications mapping is missing")
        return {"schema_version": STATE_SCHEMA_VERSION, "updated_at": state.get("updated_at"), "applications": dict(state["applications"])}

    def _write(self, state: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(state)
        payload["updated_at"] = _now()
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(temp, self.path)

    @staticmethod
    def fingerprint(record: Mapping[str, Any]) -> str:
        application_id = str(record.get("application_id") or "").strip()
        job_url = str(record.get("job_url") or "").strip()
        resume_sha256 = str(record.get("resume_sha256") or "").strip().lower()
        if not application_id or not job_url or len(resume_sha256) != 64:
            raise ExecutionStateError("EXECUTION_STATE_INVALID: application_id, job_url, and exact resume_sha256 are required")
        return f"{application_id}|{job_url}|{resume_sha256}"

    def reserve(self, record: Mapping[str, Any], *, stage: str) -> tuple[bool, dict[str, Any]]:
        """Reserve a stage once; return ``False`` when a task already exists."""
        if stage not in {"preflight", "execution"}:
            raise ExecutionStateError(f"EXECUTION_STATE_INVALID: unsupported stage {stage}")
        state = self.load()
        application_id = str(record.get("application_id") or "").strip()
        fingerprint = self.fingerprint(record)
        applications = state["applications"]
        existing = applications.get(application_id)
        if existing is not None:
            if not isinstance(existing, Mapping) or existing.get("fingerprint") != fingerprint:
                raise ExecutionStateError("EXECUTION_STATE_CONFLICT: application fingerprint changed; manual review is required before another task")
            stage_state = existing.get(stage) or {}
            # Automatic runs are allowed to *poll* unfinished work, never to
            # recreate a task after it is ready, blocked, or terminal. A
            # deliberate human-approved retry must use a new state workflow.
            if isinstance(stage_state, Mapping) and str(stage_state.get("status") or "") in _ACTIVE_TASK_STATUSES:
                return False, dict(existing)
        current = dict(existing) if isinstance(existing, Mapping) else {}
        current.setdefault("fingerprint", fingerprint)
        current.setdefault("application_id", application_id)
        current[stage] = {"status": "RESERVED", "reserved_at": _now()}
        applications[application_id] = current
        self._write(state)
        return True, current

    def record_task(self, record: Mapping[str, Any], *, stage: str, task_id: str, task_url: str | None = None) -> dict[str, Any]:
        if not str(task_id).strip():
            raise ExecutionStateError("EXECUTION_STATE_INVALID: task_id is required")
        state = self.load()
        application_id = str(record.get("application_id") or "").strip()
        fingerprint = self.fingerprint(record)
        current = state["applications"].get(application_id)
        if not isinstance(current, Mapping) or current.get("fingerprint") != fingerprint:
            raise ExecutionStateError("EXECUTION_STATE_CONFLICT: task was not reserved for this application fingerprint")
        updated = dict(current)
        updated[stage] = {
            "status": "TASK_CREATED",
            "task_id": str(task_id),
            "task_url": str(task_url or ""),
            "created_at": _now(),
        }
        state["applications"][application_id] = updated
        self._write(state)
        return updated

    def record_snapshot(self, application_id: str, *, stage: str, snapshot: Mapping[str, Any], outcome: Mapping[str, Any] | None = None) -> dict[str, Any]:
        state = self.load()
        current = state["applications"].get(str(application_id))
        if not isinstance(current, Mapping):
            raise ExecutionStateError("EXECUTION_STATE_INVALID: cannot reconcile an application that has no recorded task")
        stage_state = current.get(stage)
        if not isinstance(stage_state, Mapping):
            raise ExecutionStateError("EXECUTION_STATE_INVALID: cannot reconcile a stage that has no recorded task")
        updated = dict(current)
        agent_status = str(snapshot.get("agent_status") or "unknown").upper()
        if outcome is not None and stage == "preflight":
            outcome_status = str(outcome.get("status") or "").upper()
            terminal = "READY_FOR_EXECUTION" if outcome_status == "AUTO_APPLY_READY" else "BLOCKED"
        elif outcome is not None:
            # A completed Manus execution has one durable reconciliation pass.
            # Any non-submission result is persisted as Review, not repeatedly
            # polled or retried by a later automatic queue run.
            terminal = "SUBMITTED_CONFIRMED" if str(outcome.get("status") or "").upper() == "SUBMITTED" else "RECONCILED_REVIEW"
        elif agent_status == "ERROR":
            terminal = "ERROR"
        elif agent_status == "WAITING":
            terminal = "WAITING"
        elif agent_status == "STOPPED":
            terminal = "RECONCILIATION_PENDING"
        else:
            terminal = "RUNNING"
        updated[stage] = {
            **dict(stage_state),
            "status": terminal,
            "last_checked_at": _now(),
            "snapshot": dict(snapshot),
            "outcome": dict(outcome) if isinstance(outcome, Mapping) else None,
        }
        state["applications"][str(application_id)] = updated
        self._write(state)
        return updated

    def release(self, record: Mapping[str, Any], *, stage: str, reason: str) -> None:
        """Record a non-task failure so a later explicit retry remains auditable."""
        state = self.load()
        application_id = str(record.get("application_id") or "").strip()
        fingerprint = self.fingerprint(record)
        current = state["applications"].get(application_id)
        if not isinstance(current, Mapping) or current.get("fingerprint") != fingerprint:
            return
        updated = dict(current)
        updated[stage] = {"status": "BLOCKED", "reason": str(reason)[:1500], "updated_at": _now()}
        state["applications"][application_id] = updated
        self._write(state)

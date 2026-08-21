"""Local-first scheduler for AgentFlow workflows.

Inspired by Dagu scheduling semantics: timezone-aware cron, overlap policy,
catch-up, durable scheduler state, and single-process locking. It deliberately
owns dispatch only; WorkflowEngine remains responsible for durable execution.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

try:
    from croniter import croniter
except ImportError:  # pragma: no cover - optional dependency at import time
    croniter = None


@dataclass(frozen=True)
class ScheduleSpec:
    workflow_id: str
    cron: str
    timezone: str = "UTC"
    overlap_policy: str = "skip"  # skip | all | latest
    catchup_window_sec: int = 0


class SchedulerState:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.data = self._load()

    def _load(self) -> dict:
        if not self.path.exists():
            return {"schedules": {}, "runs": {}}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self) -> None:
        with self._lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
            tmp.replace(self.path)


class LocalWorkflowScheduler:
    """A small durable scheduler suitable for the local Conductor runtime."""

    def __init__(self, *, state_dir: str | Path = "jobs/workflow_runtime/scheduler", tick_sec: int = 30) -> None:
        self.state_dir = Path(state_dir)
        self.state = SchedulerState(self.state_dir / "scheduler.json")
        self.lock_path = self.state_dir / "scheduler.lock"
        self.tick_sec = max(1, tick_sec)
        self.schedules: dict[str, ScheduleSpec] = {}
        self.dispatch: Callable[[str, dict], object] | None = None
        self._stop = threading.Event()

    def register(self, spec: ScheduleSpec) -> None:
        if croniter is None:
            raise RuntimeError("croniter is required for scheduler execution")
        if spec.overlap_policy not in {"skip", "all", "latest"}:
            raise ValueError("overlap_policy must be skip, all, or latest")
        ZoneInfo(spec.timezone)
        croniter(spec.cron, datetime.now(timezone.utc))
        self.schedules[spec.workflow_id] = spec
        self.state.data["schedules"].setdefault(spec.workflow_id, {})
        self.state.save()

    def set_dispatcher(self, dispatch: Callable[[str, dict], object]) -> None:
        self.dispatch = dispatch

    def tick(self, now: datetime | None = None) -> list[str]:
        if self.dispatch is None:
            raise RuntimeError("scheduler dispatcher is not configured")
        now = now or datetime.now(timezone.utc)
        dispatched: list[str] = []
        for workflow_id, spec in self.schedules.items():
            tz = ZoneInfo(spec.timezone)
            local_now = now.astimezone(tz)
            state = self.state.data["schedules"].setdefault(workflow_id, {})
            last = state.get("last_scheduled_at")
            if last:
                cursor = datetime.fromisoformat(last)
            else:
                cursor = local_now - timedelta(seconds=1)
            due = self._due_times(spec, cursor, local_now)
            if not due:
                continue
            if spec.overlap_policy == "latest":
                due = [due[-1]]
            for scheduled_at in due:
                if spec.overlap_policy == "skip" and self._has_active(workflow_id):
                    state["last_scheduled_at"] = scheduled_at.isoformat()
                    continue
                run_id = f"{workflow_id}-{scheduled_at.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
                if run_id in self.state.data["runs"]:
                    continue
                payload = {"scheduled_at": scheduled_at.isoformat(), "run_id": run_id, "trigger": "schedule"}
                self.dispatch(workflow_id, payload)
                self.state.data["runs"][run_id] = {"workflow_id": workflow_id, "scheduled_at": scheduled_at.isoformat(), "status": "DISPATCHED"}
                state["last_scheduled_at"] = scheduled_at.isoformat()
                dispatched.append(run_id)
        self.state.save()
        return dispatched

    def run_forever(self) -> None:
        self._acquire_lock()
        try:
            while not self._stop.is_set():
                self.tick()
                self._stop.wait(self.tick_sec)
        finally:
            self._release_lock()

    def stop(self) -> None:
        self._stop.set()

    def _due_times(self, spec: ScheduleSpec, cursor: datetime, now: datetime) -> list[datetime]:
        local_cursor = cursor.astimezone(ZoneInfo(spec.timezone))
        itr = croniter(spec.cron, local_cursor)
        due: list[datetime] = []
        candidate = itr.get_next(datetime)
        earliest = now - timedelta(seconds=spec.catchup_window_sec) if spec.catchup_window_sec else now
        while candidate <= now:
            if candidate >= earliest:
                due.append(candidate)
            candidate = itr.get_next(datetime)
            if len(due) > 1000:
                break
        return due

    def _has_active(self, workflow_id: str) -> bool:
        return any(r.get("workflow_id") == workflow_id and r.get("status") in {"DISPATCHED", "RUNNING", "AWAITING_APPROVAL"} for r in self.state.data["runs"].values())

    def _acquire_lock(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        try:
            fd = self.lock_path.open("x", encoding="utf-8")
            fd.write(str(time.time()))
            fd.close()
        except FileExistsError:
            raise RuntimeError(f"Scheduler lock already held: {self.lock_path}")

    def _release_lock(self) -> None:
        self.lock_path.unlink(missing_ok=True)

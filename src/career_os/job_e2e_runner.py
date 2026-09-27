"""One-job end-to-end Career OS workflow on the existing internal runtime.

This runner deliberately does not depend on Conductor/AgentFlow. It composes the
already-registered Career OS specialists through ``MultiAgentRuntime`` and
persists a terminal audit trail through the runtime's ControlPlaneStore.

The first production-safe mode stops at READY_TO_APPLY or REVIEW_REQUIRED.
Application submission is never performed by this runner.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from .agent_runtime import MultiAgentRuntime
from .control_plane import AuditEvent, TaskRecord, TaskStatus


TERMINAL_STATES = {"READY_TO_APPLY", "REVIEW_REQUIRED", "BLOCKED", "FAILED"}


@dataclass(frozen=True)
class JobE2EInput:
    job: Mapping[str, Any]
    profile: Mapping[str, Any]
    evidence_pack: Mapping[str, Any] | None = None
    jd_analysis: Mapping[str, Any] | None = None
    resume_files: Mapping[str, Any] | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class JobE2EResult:
    run_id: str
    parent_task_id: str
    state: str
    stages: tuple[dict[str, Any], ...]
    audit_event_ids: tuple[str, ...]
    artifacts: Mapping[str, Any]


class JobE2ERunner:
    """Compose the real specialist runtime into one durable job-processing run."""

    def __init__(self, runtime: MultiAgentRuntime) -> None:
        self.runtime = runtime

    def _parent(self, run: JobE2EInput, run_id: str) -> TaskRecord:
        task = self.runtime.store.create_task(
            TaskRecord(
                objective=f"Process one job end-to-end: {run.job.get('title') or run.job.get('id') or run_id}",
                department="job-processing",
                agent_id="ceo",
                payload={
                    "runtime": "career-os-job-e2e-v1",
                    "run_id": run_id,
                    "job_id": run.job.get("id"),
                    "job_url": run.job.get("url"),
                    "mode": "no-submit",
                    "metadata": dict(run.metadata),
                },
            )
        )
        task.status = TaskStatus.RUNNING
        self.runtime.store.update_task(task)
        self.runtime.harness.start_session(task.id, objective=task.objective, input_data={"run_id": run_id, "job_id": run.job.get("id")})
        self.runtime.store.add_audit(
            AuditEvent(
                event_type="JOB_E2E_STARTED",
                actor_type="career-os",
                actor_id="job-e2e-runner",
                source="internal-runtime",
                task_id=task.id,
                output={"run_id": run_id, "job_id": run.job.get("id"), "mode": "no-submit"},
                decision="STARTED",
            )
        )
        return task

    def _audit(self, task_id: str, run_id: str, stage: str, status: str, output: Mapping[str, Any] | None = None) -> str:
        event = self.runtime.store.add_audit(
            AuditEvent(
                event_type="JOB_E2E_STAGE",
                actor_type="career-os",
                actor_id="job-e2e-runner",
                source="internal-runtime",
                task_id=task_id,
                output={
                    "run_id": run_id,
                    "stage": stage,
                    "status": status,
                    "output_keys": sorted((output or {}).keys()),
                },
                decision=status,
            )
        )
        return event.id

    @staticmethod
    def _dict(value: Any) -> dict[str, Any]:
        if hasattr(value, "model_dump"):
            value = value.model_dump(mode="json")
        if isinstance(value, Mapping):
            return dict(value)
        return {"result": value}

    async def run(self, run: JobE2EInput) -> JobE2EResult:
        run_id = f"job-e2e-{uuid4().hex[:12]}"
        parent = self._parent(run, run_id)
        stages: list[dict[str, Any]] = []
        audit_ids: list[str] = []
        artifacts: dict[str, Any] = {"job": dict(run.job), "run_id": run_id}

        # Stage 1: verification. If caller supplied a verified destination/JD,
        # preserve it. Otherwise fail closed rather than pretending discovery ran.
        job = dict(run.job)
        if not job.get("id") or not job.get("url") or not job.get("title"):
            return await self._terminal(parent, run_id, stages, audit_ids, artifacts, "BLOCKED", "job requires id, title and url")
        artifacts["job"] = job
        audit_ids.append(self._audit(parent.id, run_id, "VERIFY", "PASS", job))
        stages.append({"stage": "VERIFY", "status": "PASS"})

        context: dict[str, Any] = {
            "job": job,
            "profile": dict(run.profile),
            "evidence_pack": dict(run.evidence_pack or {}),
            "jd_analysis": dict(run.jd_analysis or {}),
        }

        # The provider-backed specialists are used when configured. The runtime
        # itself owns retries/checkpoints; this runner only passes explicit stage context.
        pipeline = (
            ("career-analyst", "Analyze JD/job fit and evidence"),
            ("resume-agent", "Create a job-specific truthful resume"),
            ("recruiter-challenger", "Independently challenge fit and resume claims"),
        )
        for agent_id, objective in pipeline:
            try:
                result = await self.runtime.execute_real_agent_async(
                    parent_task_id=parent.id,
                    agent_id=agent_id,
                    objective=objective,
                    context=context,
                )
            except Exception as exc:
                stages.append({"stage": agent_id, "status": "FAILED", "error": type(exc).__name__})
                audit_ids.append(self._audit(parent.id, run_id, agent_id, "FAILED", {"error": type(exc).__name__}))
                return await self._terminal(parent, run_id, stages, audit_ids, artifacts, "FAILED", type(exc).__name__)

            output = self._dict(result)
            key = {"career-analyst": "fit", "resume-agent": "resume", "recruiter-challenger": "challenge"}[agent_id]
            context[key] = output
            artifacts[key] = output
            audit_ids.append(self._audit(parent.id, run_id, agent_id, "PASS", output))
            stages.append({"stage": agent_id, "status": "PASS", "output_keys": sorted(output)})

        # Readiness is deliberately conservative. A real browser submission is
        # outside this first E2E and therefore cannot be inferred from agent output.
        challenge = context.get("challenge", {})
        blocked = bool(challenge.get("blocked") or challenge.get("critical_issue") or challenge.get("requires_review"))
        state = "REVIEW_REQUIRED" if blocked else "READY_TO_APPLY"
        artifacts["submission"] = {"enabled": False, "performed": False}
        audit_ids.append(self._audit(parent.id, run_id, "READINESS", state, {"submission_performed": False}))
        stages.append({"stage": "READINESS", "status": state})
        return await self._terminal(parent, run_id, stages, audit_ids, artifacts, state, None)

    async def _terminal(self, parent: TaskRecord, run_id: str, stages: list[dict[str, Any]], audit_ids: list[str], artifacts: dict[str, Any], state: str, error: str | None) -> JobE2EResult:
        parent = self.runtime.store.get_task(parent.id)
        parent.result = {"run_id": run_id, "state": state, "stages": stages, "artifacts": artifacts, "error": error}
        parent.status = TaskStatus.COMPLETED if state in {"READY_TO_APPLY", "REVIEW_REQUIRED", "BLOCKED"} else TaskStatus.FAILED
        parent.failure_reason = error
        self.runtime.store.update_task(parent)
        self.runtime.harness.end_session(parent.id, output={"run_id": run_id, "state": state, "stage_count": len(stages)})
        self.runtime.store.add_audit(
            AuditEvent(
                event_type="JOB_E2E_TERMINAL",
                actor_type="career-os",
                actor_id="job-e2e-runner",
                source="internal-runtime",
                task_id=parent.id,
                output={"run_id": run_id, "state": state, "error": error, "submission_performed": False},
                decision=state,
            )
        )
        return JobE2EResult(run_id, parent.id, state, tuple(stages), tuple(audit_ids), artifacts)


__all__ = ["JobE2EInput", "JobE2EResult", "JobE2ERunner", "TERMINAL_STATES"]

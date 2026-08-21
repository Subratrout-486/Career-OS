"""Durable Career OS agent runtime.

This is the execution layer that turns the DeepSeek-inspired harness primitives
into actual Career OS work. GitHub Actions remains a scheduler/trigger; this
runtime owns task lifecycle, bounded retry, checkpoints and Conductor-backed
specialist execution.
"""
from __future__ import annotations

import asyncio
from typing import Any

from .agent_harness import AgentHarness
from .control_plane import ControlPlaneStore, TaskRecord, TaskStatus
from .conductor_runtime import ConductorRuntime
from .jd_analyzer import analyze_jd
from .models import FitReport, Job, TailoredResume


class CareerOSAgentRuntime:
    """Durable specialist-agent runner over the Career OS control plane."""

    AGENT_DEPARTMENTS = {
        "career-analyst": "strategy",
        "resume-agent": "resume",
        "recruiter-challenger": "quality",
        "jd-analyzer": "jd-analysis",
        "evidence-agent": "career-profile",
    }

    def __init__(self, store: ControlPlaneStore | None = None, conductor: ConductorRuntime | None = None):
        self.store = store or ControlPlaneStore()
        self.harness = AgentHarness(self.store, actor_id="career-os-runtime")
        self.conductor = conductor or ConductorRuntime()

    @staticmethod
    def _jsonable(value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        if isinstance(value, dict):
            return {str(k): CareerOSAgentRuntime._jsonable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [CareerOSAgentRuntime._jsonable(v) for v in value]
        return value

    def create_root_task(self, objective: str, *, payload: dict[str, Any] | None = None) -> TaskRecord:
        task = self.store.create_task(TaskRecord(
            objective=objective,
            department="orchestrator",
            status=TaskStatus.RUNNING,
            payload=self._jsonable(payload or {}),
        ))
        self.harness.start_session(task.id, objective=objective, input_data=self._jsonable(payload or {}))
        return task

    async def execute_real_agent_async(
        self,
        *,
        parent_task_id: str,
        agent_id: str,
        objective: str,
        context: dict[str, Any],
    ) -> Any:
        """Execute one specialist as a durable child task.

        The child is persisted before provider execution. Provider failures are
        bounded by the child task's retry budget. A terminal failure remains
        visible in the control plane and is never silently replaced by another
        provider.
        """
        parent = self.store.get_task(parent_task_id)
        child = self.store.create_task(TaskRecord(
            objective=objective,
            department=self.AGENT_DEPARTMENTS.get(agent_id, "orchestrator"),
            agent_id=agent_id,
            parent_task_id=parent.id,
            status=TaskStatus.RUNNING,
            payload={"agent_id": agent_id, "context": self._jsonable(context)},
            max_retries=2,
        ))
        step = 1
        self.harness.start_session(child.id, objective=objective, input_data=self._jsonable(context))

        for attempt in range(child.max_retries + 1):
            child = self.store.get_task(child.id)
            child.retry_count = attempt
            child.status = TaskStatus.RUNNING
            self.store.update_task(child)
            self.harness.start_step(child.id, step_index=step, input_data={"attempt": attempt + 1, "agent_id": agent_id})
            try:
                result = await self._execute_agent(agent_id, context)
                child = self.store.get_task(child.id)
                child.status = TaskStatus.COMPLETED
                child.result = {"value": self._jsonable(result), "provider": self.conductor.last_provider_used}
                child.failure_reason = None
                self.store.update_task(child)
                self.harness.end_step(child.id, step_index=step, output=self._jsonable(result))
                self.harness.end_session(child.id, output=self._jsonable(result))
                return result
            except Exception as exc:
                child = self.store.get_task(child.id)
                child.failure_reason = f"{type(exc).__name__}: {exc}"
                if attempt < child.max_retries:
                    child.status = TaskStatus.RETRYING
                    self.store.update_task(child)
                    self.harness.end_step(child.id, step_index=step, output={"retry": True, "error": child.failure_reason})
                    await asyncio.sleep(min(2 ** attempt, 4))
                    step += 1
                    continue
                child.status = TaskStatus.FAILED
                self.store.update_task(child)
                self.harness.end_step(child.id, step_index=step, output={"failed": True, "error": child.failure_reason})
                raise

    async def _execute_agent(self, agent_id: str, context: dict[str, Any]) -> Any:
        if agent_id == "career-analyst":
            return await self.conductor.fit(
                str(context["profile"]),
                context["job"],
                context.get("evidence_pack"),
                context.get("jd_analysis"),
            )
        if agent_id == "resume-agent":
            fit = context["fit"]
            if not isinstance(fit, FitReport):
                fit = FitReport.model_validate(self._jsonable(fit))
            return await self.conductor.resume(
                str(context["profile"]),
                context["job"],
                fit,
                context.get("evidence_pack"),
                context.get("jd_analysis"),
            )
        if agent_id == "recruiter-challenger":
            fit = context["fit"]
            resume = context["resume"]
            if not isinstance(fit, FitReport):
                fit = FitReport.model_validate(self._jsonable(fit))
            if not isinstance(resume, TailoredResume):
                resume = TailoredResume.model_validate(self._jsonable(resume))
            return await self.conductor.challenge(
                str(context["profile"]), context["job"], fit, resume, context.get("evidence_pack")
            )
        if agent_id == "jd-analyzer":
            job = context["job"]
            if not isinstance(job, Job):
                job = Job.model_validate(self._jsonable(job))
            return analyze_jd(job)
        if agent_id == "evidence-agent":
            return context.get("evidence_pack") or []
        raise ValueError(f"Unknown Career OS agent: {agent_id}")

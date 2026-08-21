"""Durable harness boundary for the real Career OS pipeline.

This module deliberately keeps lifecycle state separate from the domain pipeline.
When an AI runtime is unavailable, the task is WAITING/READY_FOR_CONDUCTOR rather
than FAILED: deterministic work and the durable handoff survive the outage.
"""
from __future__ import annotations

import inspect
from typing import Any, Awaitable, Callable

from .agent_harness import AgentHarness, HarnessRecovery
from .control_plane import ControlPlaneStore, TaskRecord, TaskStatus


class PipelineHarness:
    """Run one Career OS pipeline execution as a durable harness task."""

    AI_HANDOFF_STATUSES = frozenset({
        "AI_PROVIDER_UNAVAILABLE",
        "CONDUCTOR_NOT_CONNECTED",
        "READY_FOR_CONDUCTOR",
    })

    def __init__(self, store: ControlPlaneStore | None = None) -> None:
        self.store = store or ControlPlaneStore()
        self.harness = AgentHarness(self.store, actor_id="career-os-pipeline-harness")
        self.recovery = HarnessRecovery(self.store)

    async def run(
        self,
        *,
        objective: str,
        context: dict[str, Any],
        operation: Callable[[], Awaitable[Any] | Any],
    ) -> tuple[TaskRecord, Any]:
        task = self.store.create_task(
            TaskRecord(
                objective=objective,
                department="career-pipeline",
                agent_id="career-os-pipeline",
                status=TaskStatus.RUNNING,
                payload={"runtime": "career-os-harness", "context": context},
            )
        )
        self.harness.start_session(task.id, objective=objective, input_data=context)
        self.harness.start_step(task.id, step_index=0, input_data=context)
        try:
            output = operation()
            if inspect.isawaitable(output):
                output = await output
            if hasattr(output, "model_dump"):
                summary = output.model_dump()
            elif isinstance(output, dict):
                summary = output
            else:
                summary = {"result": output}

            review_status = str(summary.get("review_status") or "") if isinstance(summary, dict) else ""
            if review_status in self.AI_HANDOFF_STATUSES:
                task.result = summary
                task.status = TaskStatus.WAITING
                task.failure_reason = review_status
                task.payload["handoff"] = {
                    "status": "READY_FOR_CONDUCTOR",
                    "reason": review_status,
                    "next_action": "Conductor must consume the durable handoff and resume the AI stages.",
                }
                self.store.update_task(task)
                self.harness._event(
                    "CONDUCTOR_HANDOFF_READY",
                    task_id=task.id,
                    output=task.payload["handoff"],
                    decision="WAITING_FOR_CONDUCTOR",
                )
                self.harness.end_step(task.id, step_index=0, output={"review_status": review_status})
                return task, output

            task.result = summary
            task.status = TaskStatus.COMPLETED
            self.store.update_task(task)
            self.harness.end_step(task.id, step_index=0, output={"review_status": summary.get("review_status")})
            self.harness.end_session(task.id, output={"review_status": summary.get("review_status")})
            return task, output
        except Exception as exc:
            task.retry_count += 1
            task.failure_reason = f"{type(exc).__name__}: {exc}"
            message = str(exc).lower()
            if "ai provider" in message or "conductor" in message or "api_key" in message:
                task.status = TaskStatus.WAITING
                task.payload["handoff"] = {
                    "status": "READY_FOR_CONDUCTOR",
                    "reason": task.failure_reason,
                    "next_action": "Connect the configured Conductor runtime; do not fall back to a paid provider.",
                }
                self.store.update_task(task)
                self.harness._event(
                    "CONDUCTOR_HANDOFF_READY",
                    task_id=task.id,
                    output=task.payload["handoff"],
                    decision="WAITING_FOR_CONDUCTOR",
                )
                return task, {"review_status": "READY_FOR_CONDUCTOR", "errors": [task.failure_reason]}

            task.status = TaskStatus.FAILED if task.retry_count >= task.max_retries else TaskStatus.RETRYING
            self.store.update_task(task)
            self.harness._event(
                "PIPELINE_FAILED",
                task_id=task.id,
                output={"error_type": type(exc).__name__, "error": str(exc)},
                decision=task.status.value,
            )
            raise

    def recover(self) -> list[dict[str, Any]]:
        return self.recovery.inspect()


__all__ = ["PipelineHarness"]

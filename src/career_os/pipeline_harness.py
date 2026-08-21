"""Durable harness boundary for the real Career OS pipeline.

This module is deliberately small: Career OS keeps its domain pipeline while
AgentHarness owns lifecycle, checkpointing, recovery and audit semantics. It
prevents the repository from growing a second fake agent loop beside the real
AgentRuntime.
"""
from __future__ import annotations

import inspect
from typing import Any, Awaitable, Callable

from .agent_harness import AgentHarness, HarnessRecovery
from .control_plane import ControlPlaneStore, TaskRecord, TaskStatus


class PipelineHarness:
    """Run one real Career OS pipeline execution as a durable harness task."""

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
            task.result = summary
            task.status = TaskStatus.COMPLETED
            self.store.update_task(task)
            self.harness.end_step(task.id, step_index=0, output={"review_status": summary.get("review_status")})
            self.harness.end_session(task.id, output={"review_status": summary.get("review_status")})
            return task, output
        except Exception as exc:
            task.retry_count += 1
            task.failure_reason = f"{type(exc).__name__}: {exc}"
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

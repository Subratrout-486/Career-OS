"""DeepSeek-inspired runtime primitives for Career OS.

This is an architectural adaptation, not a copy of DeepSeek Harness. It adds
explicit session/step lifecycle events, durable checkpoints, fail-closed action
policy, approval gates, and restart recovery on top of the existing
ControlPlaneStore.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .control_plane import (
    ApprovalRequest,
    ApprovalStatus,
    AuditEvent,
    ControlPlaneStore,
    TaskRecord,
    TaskStatus,
    utc_now,
)


@dataclass(frozen=True)
class HarnessCheckpoint:
    task_id: str
    phase: str
    step_index: int
    state: dict[str, Any]
    created_at: str


@dataclass(frozen=True)
class ActionDecision:
    status: str
    reason: str
    approval_id: str | None = None


class AgentHarness:
    """Durable session/step lifecycle facade over the existing control plane."""

    def __init__(self, store: ControlPlaneStore | None = None, *, actor_id: str = "career-os-harness"):
        self.store = store or ControlPlaneStore()
        self.actor_id = actor_id

    def _event(self, event_type: str, *, task_id: str | None = None, input_data: dict[str, Any] | str | None = None, output: dict[str, Any] | str | None = None, decision: str | None = None, model: str | None = None, changes: list[str] | None = None) -> AuditEvent:
        return self.store.add_audit(AuditEvent(
            event_type=event_type,
            actor_type="harness",
            actor_id=self.actor_id,
            model=model,
            source="agent-harness",
            task_id=task_id,
            input=input_data,
            output=output,
            decision=decision,
            changes=changes or [],
        ))

    def start_session(self, task_id: str, *, objective: str, input_data: dict[str, Any] | None = None) -> AuditEvent:
        self._set_checkpoint(task_id, phase="SESSION_STARTED", step_index=0, state={"objective": objective, "input": input_data or {}})
        return self._event("SESSION_STARTED", task_id=task_id, input_data={"objective": objective, "input": input_data or {}})

    def start_step(self, task_id: str, *, step_index: int, model: str | None = None, input_data: dict[str, Any] | None = None) -> AuditEvent:
        self._set_checkpoint(task_id, phase="STEP_STARTED", step_index=step_index, state=input_data or {})
        return self._event("STEP_STARTED", task_id=task_id, input_data=input_data or {}, model=model)

    def model_request(self, task_id: str, *, step_index: int, model: str, prompt: str) -> AuditEvent:
        self._set_checkpoint(task_id, phase="MODEL_REQUESTED", step_index=step_index, state={"model": model})
        return self._event("MODEL_REQUESTED", task_id=task_id, input_data={"prompt": prompt}, model=model)

    def tool_call(self, task_id: str, *, step_index: int, tool: str, arguments: dict[str, Any]) -> AuditEvent:
        # Persist before the side effect so a restart knows an external action
        # may already be in flight and must be reconciled rather than replayed.
        self._set_checkpoint(task_id, phase="TOOL_CALLING", step_index=step_index, state={"tool": tool, "arguments": arguments})
        return self._event("TOOL_CALL_STARTED", task_id=task_id, input_data={"tool": tool, "arguments": arguments})

    def tool_result(self, task_id: str, *, step_index: int, tool: str, result: dict[str, Any] | str, verified: bool) -> AuditEvent:
        decision = "VERIFIED" if verified else "UNVERIFIED"
        self._set_checkpoint(task_id, phase="TOOL_RESULT", step_index=step_index, state={"tool": tool, "verified": verified})
        return self._event("TOOL_CALL_COMPLETED", task_id=task_id, output={"tool": tool, "result": result}, decision=decision)

    def end_step(self, task_id: str, *, step_index: int, output: dict[str, Any] | str | None = None) -> AuditEvent:
        self._set_checkpoint(task_id, phase="STEP_COMPLETED", step_index=step_index, state={"output": output})
        return self._event("STEP_COMPLETED", task_id=task_id, output=output)

    def end_session(self, task_id: str, *, output: dict[str, Any] | str | None = None) -> AuditEvent:
        self._set_checkpoint(task_id, phase="SESSION_COMPLETED", step_index=self._current_step(task_id), state={"output": output})
        return self._event("SESSION_COMPLETED", task_id=task_id, output=output, decision="COMPLETED")

    def checkpoint(self, task_id: str) -> HarnessCheckpoint | None:
        task = self.store.get_task(task_id)
        raw = task.payload.get("_harness_checkpoint")
        if not isinstance(raw, dict):
            return None
        return HarnessCheckpoint(task_id=task_id, phase=str(raw.get("phase", "UNKNOWN")), step_index=int(raw.get("step_index", 0)), state=dict(raw.get("state") or {}), created_at=str(raw.get("created_at") or ""))

    def _set_checkpoint(self, task_id: str, *, phase: str, step_index: int, state: dict[str, Any]) -> None:
        task = self.store.get_task(task_id)
        task.payload["_harness_checkpoint"] = {"phase": phase, "step_index": step_index, "state": state, "created_at": utc_now()}
        self.store.update_task(task)

    def _current_step(self, task_id: str) -> int:
        checkpoint = self.checkpoint(task_id)
        return checkpoint.step_index if checkpoint else 0


class ActionPolicy:
    """Fail-closed policy for externally visible Career OS actions."""

    HIGH_RISK_ACTIONS = frozenset({"SUBMIT_APPLICATION", "SEND_MESSAGE", "DELETE_DATA", "CHANGE_ACCOUNT_SETTINGS", "PUBLISH_EXTERNAL_CONTENT"})

    def __init__(self, store: ControlPlaneStore | None = None, *, actor_id: str = "career-os-policy"):
        self.store = store or ControlPlaneStore()
        self.actor_id = actor_id

    def decide(self, *, task_id: str, action: str, resource_type: str, resource_id: str, summary: str, approval_available: bool = True) -> ActionDecision:
        if action not in self.HIGH_RISK_ACTIONS:
            self.store.add_audit(AuditEvent(event_type="ACTION_ALLOWED", actor_type="policy", actor_id=self.actor_id, source="agent-harness", task_id=task_id, decision="ALLOW", input={"action": action, "resource_type": resource_type, "resource_id": resource_id}))
            return ActionDecision("ALLOWED", "Action is outside the high-risk approval set.")
        if not approval_available:
            self.store.add_audit(AuditEvent(event_type="ACTION_BLOCKED", actor_type="policy", actor_id=self.actor_id, source="agent-harness", task_id=task_id, decision="BLOCK", input={"action": action}))
            return ActionDecision("BLOCKED", "Approval service is unavailable; policy fails closed.")
        approval = self.store.create_approval(ApprovalRequest(action=action, resource_type=resource_type, resource_id=resource_id, summary=summary, requested_by=self.actor_id))
        self.store.add_audit(AuditEvent(event_type="ACTION_APPROVAL_REQUIRED", actor_type="policy", actor_id=self.actor_id, source="agent-harness", task_id=task_id, decision="WAITING_FOR_APPROVAL", approval_status=ApprovalStatus.PENDING.value, input={"approval_id": approval.id, "action": action}))
        return ActionDecision("WAITING_FOR_APPROVAL", "High-risk action requires explicit approval.", approval.id)

    def consume_approval(self, approval_id: str, *, task_id: str, decided_by: str) -> ActionDecision:
        approval = self.store.get_approval(approval_id)
        task = self.store.get_task(task_id)
        consumed = set(task.payload.get("_consumed_approval_ids") or [])
        if approval.status != ApprovalStatus.APPROVED:
            return ActionDecision("BLOCKED", f"Approval is not approved: {approval.status.value}.")
        if approval_id in consumed:
            return ActionDecision("BLOCKED", "Approval has already been consumed.")
        consumed.add(approval_id)
        task.payload["_consumed_approval_ids"] = sorted(consumed)
        self.store.update_task(task)
        self.store.add_audit(AuditEvent(event_type="ACTION_APPROVAL_CONSUMED", actor_type="policy", actor_id=self.actor_id, source="agent-harness", task_id=task_id, decision="ALLOW_ONCE", approval_status="APPROVED", input={"approval_id": approval_id, "decided_by": decided_by}))
        return ActionDecision("ALLOWED", "Approved action may execute once.")


class ToolExecutionPipeline:
    """Pre-policy -> execute -> verify -> post-audit pipeline."""

    def __init__(self, harness: AgentHarness | None = None, policy: ActionPolicy | None = None):
        self.harness = harness or AgentHarness()
        self.policy = policy or ActionPolicy(self.harness.store)

    def execute(self, *, task_id: str, step_index: int, tool: str, arguments: dict[str, Any], action: str, resource_type: str, resource_id: str, summary: str, executor: Callable[[], dict[str, Any] | str], verifier: Callable[[dict[str, Any] | str], bool], approval_available: bool = True, approval_id: str | None = None, approved_by: str = "user") -> tuple[ActionDecision, dict[str, Any] | str | None]:
        self.harness.tool_call(task_id, step_index=step_index, tool=tool, arguments=arguments)
        if approval_id:
            decision = self.policy.consume_approval(approval_id, task_id=task_id, decided_by=approved_by)
        else:
            decision = self.policy.decide(task_id=task_id, action=action, resource_type=resource_type, resource_id=resource_id, summary=summary, approval_available=approval_available)
        if decision.status != "ALLOWED":
            self.harness.tool_result(task_id, step_index=step_index, tool=tool, result={"blocked": True, "reason": decision.reason}, verified=False)
            return decision, None
        try:
            result = executor()
        except Exception as exc:
            self.harness.tool_result(task_id, step_index=step_index, tool=tool, result={"error": str(exc)}, verified=False)
            return ActionDecision("FAILED", f"Tool execution failed: {exc}"), None
        verified = bool(verifier(result))
        self.harness.tool_result(task_id, step_index=step_index, tool=tool, result=result, verified=verified)
        if not verified:
            return ActionDecision("FAILED_VERIFICATION", "External action completed but post-execution verification failed."), result
        return ActionDecision("COMPLETED", "Action executed and verified."), result


class HarnessRecovery:
    """Find work that needs reconciliation after a process restart."""

    RECOVERABLE = frozenset({TaskStatus.RUNNING, TaskStatus.RETRYING, TaskStatus.WAITING})

    def __init__(self, store: ControlPlaneStore | None = None):
        self.store = store or ControlPlaneStore()

    def inspect(self) -> list[dict[str, Any]]:
        pending: list[dict[str, Any]] = []
        for task in self.store.tasks():
            if task.status not in self.RECOVERABLE:
                continue
            checkpoint = task.payload.get("_harness_checkpoint") if isinstance(task.payload, dict) else None
            pending.append({"task_id": task.id, "status": task.status.value, "phase": checkpoint.get("phase") if isinstance(checkpoint, dict) else None, "step_index": checkpoint.get("step_index") if isinstance(checkpoint, dict) else None, "action_required": "RECONCILE_EXTERNAL_SIDE_EFFECT" if isinstance(checkpoint, dict) and checkpoint.get("phase") == "TOOL_CALLING" else "RESUME_FROM_CHECKPOINT"})
        return pending

    def mark_for_reconciliation(self, task_id: str, *, reason: str) -> TaskRecord:
        task = self.store.get_task(task_id)
        task.status = TaskStatus.RETRYING
        task.failure_reason = reason
        self.store.update_task(task)
        self.store.add_audit(AuditEvent(event_type="RECOVERY_RECONCILIATION_REQUIRED", actor_type="recovery", actor_id="career-os-recovery", source="agent-harness", task_id=task_id, decision="RECONCILE", input={"reason": reason}))
        return task

"""Durable control-plane contracts for the browser-first Career OS.

The existing pipeline remains the execution engine. This module adds a small,
provider-agnostic state layer that can be backed by a managed database later.
Until then, records are persisted atomically to a JSON file so the platform is
restart-safe and remains useful when every AI provider is unavailable.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class TaskStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    RETRYING = "RETRYING"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    COMPLETED = "COMPLETED"


class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EDIT_REQUIRED = "EDIT_REQUIRED"
    RETRY_REQUESTED = "RETRY_REQUESTED"


class MemoryType(str, Enum):
    CAREER = "CAREER"
    PROJECT = "PROJECT"
    AGENT = "AGENT"
    TASK = "TASK"
    DECISION = "DECISION"


class AgentRecord(BaseModel):
    id: str
    name: str
    department: str
    provider: str = "deterministic"
    model: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    supported_tools: list[str] = Field(default_factory=list)
    availability: Literal["AVAILABLE", "DEGRADED", "UNAVAILABLE"] = "AVAILABLE"
    reliability: float | None = None
    quality_score: float | None = None
    latency_ms: int | None = None
    usage_today: int = 0
    last_seen: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelRecord(BaseModel):
    id: str
    provider: str
    model: str
    departments: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    cost_tier: Literal["FREE", "LOW", "MEDIUM", "HIGH", "UNKNOWN"] = "UNKNOWN"
    free_tier_status: str = "UNKNOWN"
    context_limit: int | None = None
    availability: Literal["AVAILABLE", "DEGRADED", "UNAVAILABLE"] = "AVAILABLE"
    reliability: float | None = None
    quality_score: float | None = None
    latency_ms: int | None = None
    supported_tools: list[str] = Field(default_factory=list)
    connector_method: str | None = None
    usage_today: int = 0
    task_history: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskRecord(BaseModel):
    id: str = Field(default_factory=lambda: new_id("task"))
    objective: str
    department: str = "orchestrator"
    agent_id: str | None = None
    parent_task_id: str | None = None
    dependency_ids: list[str] = Field(default_factory=list)
    status: TaskStatus = TaskStatus.QUEUED
    payload: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    retry_count: int = 0
    max_retries: int = 2
    timeout_seconds: int = 120
    fallback_agent_id: str | None = None
    failure_reason: str | None = None
    human_escalation: str | None = None
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)


class AgentMessage(BaseModel):
    id: str = Field(default_factory=lambda: new_id("msg"))
    task_id: str
    from_agent: str
    to_agent: str
    objective: str
    input: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any] | str] = Field(default_factory=list)
    confidence: float | None = None
    status: TaskStatus = TaskStatus.QUEUED
    created_at: str = Field(default_factory=utc_now)


class MemoryItem(BaseModel):
    id: str = Field(default_factory=lambda: new_id("mem"))
    memory_type: MemoryType
    key: str
    content: dict[str, Any] | str
    source: str
    timestamp: str = Field(default_factory=utc_now)
    confidence: float | None = None
    status: Literal["AUTHORITATIVE", "VERIFIED", "UNVERIFIED", "REJECTED"] = "UNVERIFIED"
    provenance: list[str] = Field(default_factory=list)
    authoritative: bool = False


class ApprovalRequest(BaseModel):
    id: str = Field(default_factory=lambda: new_id("approval"))
    action: str
    resource_type: str
    resource_id: str
    summary: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    requested_by: str = "orchestrator"
    evidence: list[str] = Field(default_factory=list)
    decision_note: str | None = None
    decided_by: str | None = None
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)


class AuditEvent(BaseModel):
    id: str = Field(default_factory=lambda: new_id("audit"))
    event_type: str
    actor_type: str
    actor_id: str
    model: str | None = None
    source: str | None = None
    task_id: str | None = None
    input: dict[str, Any] | str | None = None
    output: dict[str, Any] | str | None = None
    decision: str | None = None
    confidence: float | None = None
    changes: list[str] = Field(default_factory=list)
    approval_status: str | None = None
    timestamp: str = Field(default_factory=utc_now)


class UsageEvent(BaseModel):
    id: str = Field(default_factory=lambda: new_id("usage"))
    provider: str
    model: str | None = None
    task_id: str | None = None
    operation: str
    estimated_tokens: int = 0
    credits: float = 0.0
    duration_ms: int | None = None
    success: bool = True
    created_at: str = Field(default_factory=utc_now)


class RouteRequest(BaseModel):
    department: str
    task_type: str
    required_capabilities: list[str] = Field(default_factory=list)
    max_cost_tier: Literal["FREE", "LOW", "MEDIUM", "HIGH", "UNKNOWN"] | None = None
    minimum_quality_score: float = 0.0


class RouteDecision(BaseModel):
    status: Literal["ROUTED", "WAITING"]
    model_id: str | None = None
    reason: str
    candidates_considered: list[str] = Field(default_factory=list)


class ControlPlaneStore:
    """Atomic JSON persistence with a database-shaped interface.

    The interface deliberately uses plain Pydantic records. A managed database
    adapter can replace this class without changing orchestrator contracts.
    """

    COLLECTIONS = (
        "agents", "models", "tasks", "messages", "memory", "approvals",
        "audit_events", "usage_events",
    )

    def __init__(self, path: str | Path | None = None):
        configured = path or os.getenv("CAREER_OS_CONTROL_PLANE_PATH") or ".career_os/control_plane.json"
        self.path = Path(configured)
        self._lock = threading.RLock()
        self._state = self._load()

    def _empty(self) -> dict[str, list[dict[str, Any]]]:
        return {name: [] for name in self.COLLECTIONS}

    def _load(self) -> dict[str, list[dict[str, Any]]]:
        if not self.path.exists():
            return self._empty()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self._empty()
        state = self._empty()
        for name in self.COLLECTIONS:
            if isinstance(raw.get(name), list):
                state[name] = raw[name]
        return state

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(self._state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(self.path)

    def _append(self, collection: str, value: BaseModel) -> BaseModel:
        with self._lock:
            self._state[collection].append(value.model_dump(mode="json"))
            self._save()
        return value

    def _replace(self, collection: str, record_id: str, value: BaseModel) -> BaseModel:
        with self._lock:
            for index, current in enumerate(self._state[collection]):
                if current.get("id") == record_id:
                    self._state[collection][index] = value.model_dump(mode="json")
                    self._save()
                    return value
        raise KeyError(f"Unknown {collection} id: {record_id}")

    def _records(self, collection: str, model: type[BaseModel]) -> list[BaseModel]:
        with self._lock:
            return [model.model_validate(item) for item in self._state[collection]]

    def register_agent(self, record: AgentRecord) -> AgentRecord:
        return self._upsert("agents", record)

    def register_model(self, record: ModelRecord) -> ModelRecord:
        return self._upsert("models", record)

    def _upsert(self, collection: str, record: BaseModel) -> BaseModel:
        with self._lock:
            for index, current in enumerate(self._state[collection]):
                if current.get("id") == getattr(record, "id"):
                    self._state[collection][index] = record.model_dump(mode="json")
                    self._save()
                    return record
        return self._append(collection, record)

    def agents(self) -> list[AgentRecord]:
        return self._records("agents", AgentRecord)  # type: ignore[return-value]

    def models(self) -> list[ModelRecord]:
        return self._records("models", ModelRecord)  # type: ignore[return-value]

    def create_task(self, record: TaskRecord) -> TaskRecord:
        return self._append("tasks", record)  # type: ignore[return-value]

    def get_task(self, task_id: str) -> TaskRecord:
        for record in self._records("tasks", TaskRecord):
            if record.id == task_id:
                return record
        raise KeyError(f"Unknown task id: {task_id}")

    def update_task(self, record: TaskRecord) -> TaskRecord:
        record.updated_at = utc_now()
        return self._replace("tasks", record.id, record)  # type: ignore[return-value]

    def tasks(self) -> list[TaskRecord]:
        return self._records("tasks", TaskRecord)  # type: ignore[return-value]

    def add_message(self, record: AgentMessage) -> AgentMessage:
        return self._append("messages", record)  # type: ignore[return-value]

    def messages(self, task_id: str | None = None) -> list[AgentMessage]:
        records = self._records("messages", AgentMessage)
        return [record for record in records if task_id is None or record.task_id == task_id]

    def add_memory(self, record: MemoryItem) -> MemoryItem:
        if record.authoritative and record.status not in {"AUTHORITATIVE", "VERIFIED"}:
            raise ValueError("Only verified memory may be authoritative")
        return self._append("memory", record)  # type: ignore[return-value]

    def memory(self, memory_type: MemoryType | None = None) -> list[MemoryItem]:
        records = self._records("memory", MemoryItem)
        return [record for record in records if memory_type is None or record.memory_type == memory_type]

    def create_approval(self, record: ApprovalRequest) -> ApprovalRequest:
        return self._append("approvals", record)  # type: ignore[return-value]

    def get_approval(self, approval_id: str) -> ApprovalRequest:
        for record in self._records("approvals", ApprovalRequest):
            if record.id == approval_id:
                return record
        raise KeyError(f"Unknown approval id: {approval_id}")

    def decide_approval(self, approval_id: str, status: ApprovalStatus, *, decided_by: str, note: str | None = None) -> ApprovalRequest:
        record = self.get_approval(approval_id)
        record.status = status
        record.decided_by = decided_by
        record.decision_note = note
        record.updated_at = utc_now()
        return self._replace("approvals", approval_id, record)  # type: ignore[return-value]

    def approvals(self, pending_only: bool = False) -> list[ApprovalRequest]:
        records = self._records("approvals", ApprovalRequest)
        if pending_only:
            return [record for record in records if record.status == ApprovalStatus.PENDING]
        return records

    def add_audit(self, record: AuditEvent) -> AuditEvent:
        return self._append("audit_events", record)  # type: ignore[return-value]

    def audit_events(self, task_id: str | None = None) -> list[AuditEvent]:
        records = self._records("audit_events", AuditEvent)
        return [record for record in records if task_id is None or record.task_id == task_id]

    def add_usage(self, record: UsageEvent) -> UsageEvent:
        return self._append("usage_events", record)  # type: ignore[return-value]

    def usage_events(self) -> list[UsageEvent]:
        return self._records("usage_events", UsageEvent)  # type: ignore[return-value]

    def snapshot(self) -> dict[str, list[dict[str, Any]]]:
        with self._lock:
            return json.loads(json.dumps(self._state))


def bootstrap_registry(store: ControlPlaneStore) -> None:
    """Install safe built-in department and model records idempotently."""
    departments = [
        ("orchestrator", "CEO / Orchestrator", "coordination", ["plan", "delegate"]),
        ("strategy", "Strategy Department", "strategy", ["reasoning", "prioritization"]),
        ("job-research", "Job Research Department", "job-research", ["research", "deduplicate"]),
        ("jd-analyzer", "JD Analysis Department", "jd-analysis", ["extract", "classify"]),
        ("career-profile", "Career Profile Department", "career-profile", ["provenance", "classify"]),
        ("resume", "Resume Department", "resume", ["generation", "tailoring"]),
        ("truth-guardian", "Truth Guardian", "quality", ["validate", "provenance"]),
        ("ats", "ATS Department", "ats", ["score", "validate"]),
        ("engineering", "Engineering Department", "engineering", ["coding", "test"]),
    ]
    for agent_id, name, department, capabilities in departments:
        store.register_agent(AgentRecord(
            id=agent_id,
            name=name,
            department=department,
            provider="deterministic" if agent_id in {"orchestrator", "truth-guardian", "ats"} else "unconfigured",
            capabilities=capabilities,
            availability="AVAILABLE" if agent_id in {"orchestrator", "truth-guardian", "ats"} else "DEGRADED",
            last_seen=utc_now(),
        ))
    store.register_model(ModelRecord(
        id="deterministic-rules-v1",
        provider="builtin",
        model="rules-v1",
        departments=["orchestrator", "jd-analysis", "quality", "ats", "engineering"],
        capabilities=["plan", "delegate", "extract", "classify", "validate", "score", "provenance"],
        cost_tier="FREE",
        free_tier_status="BUILT_IN",
        availability="AVAILABLE",
        quality_score=0.70,
        connector_method="local-deterministic",
    ))

    configured_providers = [
        ("manus-managed", "manus-managed", os.getenv("MANUS_MODEL") or os.getenv("OPENAI_MODEL"), os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_API_BASE")),
        ("gemini", "google", os.getenv("GEMINI_MODEL"), os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")),
        ("deepseek", "deepseek", os.getenv("DEEPSEEK_MODEL", "deepseek-chat"), os.getenv("DEEPSEEK_API_KEY")),
        ("xai", "xai", os.getenv("XAI_MODEL") or os.getenv("GROK_MODEL"), os.getenv("XAI_API_KEY")),
    ]
    for model_id, provider, model_name, credential in configured_providers:
        if credential:
            store.register_model(ModelRecord(
                id=model_id,
                provider=provider,
                model=model_name or "configured",
                departments=["strategy", "job-research", "jd-analysis", "career-profile", "resume", "quality", "ats", "engineering"],
                capabilities=["reasoning", "research", "extract", "classify", "generation", "tailoring", "validate", "coding"],
                cost_tier="UNKNOWN",
                free_tier_status="UNKNOWN",
                availability="AVAILABLE",
                connector_method=provider,
            ))


class ModelRouter:
    """Choose the least expensive available capable model without fabricating availability."""

    COST_ORDER = {"FREE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "UNKNOWN": 4}

    def __init__(self, store: ControlPlaneStore):
        self.store = store

    def route(self, request: RouteRequest) -> RouteDecision:
        candidates = []
        required = {item.strip().lower() for item in request.required_capabilities if item.strip()}
        max_cost = self.COST_ORDER.get(request.max_cost_tier, 4) if request.max_cost_tier else 4
        for model in self.store.models():
            capabilities = {item.strip().lower() for item in model.capabilities}
            department_ok = not model.departments or request.department in model.departments
            capable = required.issubset(capabilities)
            quality_ok = (model.quality_score or 0.0) >= request.minimum_quality_score
            cost_ok = self.COST_ORDER.get(model.cost_tier, 4) <= max_cost
            if model.availability == "AVAILABLE" and department_ok and capable and quality_ok and cost_ok:
                candidates.append(model)
        if not candidates:
            return RouteDecision(
                status="WAITING",
                reason="No registered available model satisfies the department, capability, quality, and cost constraints.",
                candidates_considered=[model.id for model in self.store.models()],
            )
        candidates.sort(key=lambda model: (
            self.COST_ORDER.get(model.cost_tier, 4),
            -(model.quality_score or 0.0),
            -(model.reliability or 0.0),
            model.latency_ms or 10**9,
        ))
        selected = candidates[0]
        return RouteDecision(
            status="ROUTED",
            model_id=selected.id,
            reason=f"Selected the lowest-cost available model capable of {request.task_type}.",
            candidates_considered=[model.id for model in candidates],
        )


class PlatformOrchestrator:
    """Controlled task delegation facade over the existing Career OS pipeline."""

    def __init__(self, store: ControlPlaneStore | None = None, *, actor_id: str = "career-os-orchestrator"):
        self.store = store or ControlPlaneStore()
        self.actor_id = actor_id

    def submit_objective(self, objective: str, *, payload: dict[str, Any] | None = None, department: str = "orchestrator") -> TaskRecord:
        task = self.store.create_task(TaskRecord(objective=objective, payload=payload or {}, department=department))
        self.store.add_audit(AuditEvent(
            event_type="OBJECTIVE_SUBMITTED",
            actor_type="user",
            actor_id=self.actor_id,
            source="platform",
            task_id=task.id,
            input={"objective": objective},
            decision="QUEUED",
        ))
        return task

    def create_execution_plan(self, objective: str, steps: list[dict[str, Any]]) -> tuple[TaskRecord, list[TaskRecord]]:
        root = self.submit_objective(objective)
        children: list[TaskRecord] = []
        previous_id: str | None = None
        for step in steps:
            child = self.store.create_task(TaskRecord(
                objective=str(step["objective"]),
                department=str(step.get("department", "orchestrator")),
                parent_task_id=root.id,
                dependency_ids=[previous_id] if previous_id else [],
                payload=dict(step.get("payload", {})),
                timeout_seconds=int(step.get("timeout_seconds", 120)),
                max_retries=int(step.get("max_retries", 2)),
                fallback_agent_id=step.get("fallback_agent_id"),
            ))
            children.append(child)
            previous_id = child.id
        self.store.add_audit(AuditEvent(
            event_type="EXECUTION_PLAN_CREATED",
            actor_type="orchestrator",
            actor_id=self.actor_id,
            source="platform",
            task_id=root.id,
            output={"child_task_ids": [child.id for child in children]},
            decision="QUEUED",
        ))
        return root, children

    def delegate(self, task_id: str, *, to_agent: str, objective: str, input_data: dict[str, Any] | None = None, evidence: list[dict[str, Any] | str] | None = None, from_agent: str | None = None, confidence: float | None = None) -> AgentMessage:
        task = self.store.get_task(task_id)
        if task.status in {TaskStatus.FAILED, TaskStatus.BLOCKED, TaskStatus.COMPLETED}:
            raise ValueError(f"Cannot delegate a terminal task in status {task.status.value}")
        known_agent_ids = {agent.id for agent in self.store.agents()}
        if to_agent not in known_agent_ids:
            raise ValueError(f"Agent is not registered: {to_agent}")
        message = self.store.add_message(AgentMessage(
            task_id=task_id,
            from_agent=from_agent or self.actor_id,
            to_agent=to_agent,
            objective=objective,
            input=input_data or {},
            evidence=evidence or [],
            confidence=confidence,
        ))
        task.agent_id = to_agent
        task.status = TaskStatus.RUNNING
        self.store.update_task(task)
        self.store.add_audit(AuditEvent(
            event_type="TASK_DELEGATED",
            actor_type="orchestrator",
            actor_id=self.actor_id,
            source="platform",
            task_id=task_id,
            input={"to_agent": to_agent, "objective": objective},
            decision="RUNNING",
        ))
        return message

    def record_result(self, task_id: str, *, status: TaskStatus, result: dict[str, Any] | None = None, failure_reason: str | None = None, human_escalation: str | None = None, model: str | None = None) -> TaskRecord:
        task = self.store.get_task(task_id)
        task.status = status
        task.result = result
        task.failure_reason = failure_reason
        task.human_escalation = human_escalation
        if status == TaskStatus.RETRYING:
            task.retry_count += 1
        task = self.store.update_task(task)
        self.store.add_audit(AuditEvent(
            event_type="TASK_RESULT_RECORDED",
            actor_type="agent" if task.agent_id else "orchestrator",
            actor_id=task.agent_id or self.actor_id,
            model=model,
            source="platform",
            task_id=task_id,
            output=result,
            decision=status.value,
            approval_status="REQUIRED" if status == TaskStatus.AWAITING_APPROVAL else None,
        ))
        return task

    def request_approval(self, *, action: str, resource_type: str, resource_id: str, summary: str, evidence: list[str] | None = None, task_id: str | None = None) -> ApprovalRequest:
        approval = self.store.create_approval(ApprovalRequest(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            summary=summary,
            evidence=evidence or [],
        ))
        if task_id:
            task = self.store.get_task(task_id)
            task.status = TaskStatus.AWAITING_APPROVAL
            self.store.update_task(task)
        self.store.add_audit(AuditEvent(
            event_type="APPROVAL_REQUESTED",
            actor_type="orchestrator",
            actor_id=self.actor_id,
            source="platform",
            task_id=task_id,
            output={"approval_id": approval.id, "action": action},
            decision="AWAITING_APPROVAL",
            approval_status=approval.status.value,
        ))
        return approval

    def decide_approval(self, approval_id: str, status: ApprovalStatus, *, decided_by: str, note: str | None = None) -> ApprovalRequest:
        if status == ApprovalStatus.PENDING:
            raise ValueError("An approval decision must be final or an explicit edit/retry request")
        approval = self.store.decide_approval(approval_id, status, decided_by=decided_by, note=note)
        self.store.add_audit(AuditEvent(
            event_type="APPROVAL_DECIDED",
            actor_type="user",
            actor_id=decided_by,
            source="platform",
            output={"approval_id": approval_id, "note": note},
            decision=status.value,
            approval_status=status.value,
        ))
        return approval

    def add_memory(self, item: MemoryItem) -> MemoryItem:
        stored = self.store.add_memory(item)
        self.store.add_audit(AuditEvent(
            event_type="MEMORY_RECORDED",
            actor_type="user" if item.authoritative else "agent",
            actor_id=self.actor_id,
            source=item.source,
            output={"memory_id": stored.id, "key": stored.key},
            decision=stored.status,
            confidence=stored.confidence,
            changes=stored.provenance,
        ))
        return stored

    def record_usage(self, event: UsageEvent) -> UsageEvent:
        stored = self.store.add_usage(event)
        self.store.add_audit(AuditEvent(
            event_type="USAGE_RECORDED",
            actor_type="system",
            actor_id=self.actor_id,
            model=event.model,
            source=event.provider,
            task_id=event.task_id,
            output={"estimated_tokens": event.estimated_tokens, "credits": event.credits},
            decision="SUCCESS" if event.success else "FAILED",
        ))
        return stored

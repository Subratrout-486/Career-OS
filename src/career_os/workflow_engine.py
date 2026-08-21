"""Local-first AgentFlow workflow engine.

DeepSeek Harness-inspired capabilities are expressed as replaceable services;
Dagu-inspired workflow semantics add dependencies, retries, schedules and
human gates without introducing an external workflow platform.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class WorkflowNode:
    id: str
    kind: str
    agent_id: str | None = None
    depends_on: tuple[str, ...] = ()
    input_from: tuple[str, ...] = ()
    retry_limit: int = 0
    requires_approval: bool = False
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkflowDefinition:
    id: str
    name: str
    nodes: tuple[WorkflowNode, ...]
    schedule: str | None = None
    max_concurrency: int = 1


@dataclass
class NodeExecution:
    node_id: str
    status: str = "PENDING"
    attempts: int = 0
    output: Any = None
    error: str | None = None


@dataclass
class WorkflowRun:
    run_id: str
    workflow_id: str
    status: str = "PENDING"
    nodes: dict[str, NodeExecution] = field(default_factory=dict)
    started_at: float | None = None
    finished_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "workflow_id": self.workflow_id,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "nodes": {k: vars(v) for k, v in self.nodes.items()},
        }


class WorkflowEngine:
    """Deterministic local workflow coordinator for AgentFlow."""

    def __init__(self, *, state_dir: str | Path = "jobs/workflow_runtime") -> None:
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.workflows: dict[str, WorkflowDefinition] = {}
        self.handlers: dict[str, Callable[..., Any]] = {}

    def register(self, workflow: WorkflowDefinition) -> None:
        self._validate(workflow)
        self.workflows[workflow.id] = workflow

    def register_handler(self, kind: str, handler: Callable[..., Any]) -> None:
        self.handlers[kind] = handler

    def run(self, workflow_id: str, *, input_data: dict[str, Any] | None = None, run_id: str | None = None) -> WorkflowRun:
        workflow = self.workflows[workflow_id]
        run = WorkflowRun(run_id or f"{workflow.id}-{int(time.time() * 1000)}", workflow.id)
        run.nodes = {n.id: NodeExecution(n.id) for n in workflow.nodes}
        run.status = "RUNNING"
        run.started_at = time.time()
        context: dict[str, Any] = dict(input_data or {})
        remaining = {n.id: n for n in workflow.nodes}

        try:
            while remaining:
                ready = [
                    n for n in remaining.values()
                    if all(run.nodes[d].status == "COMPLETED" for d in n.depends_on)
                ]
                if not ready:
                    blocked = ", ".join(sorted(remaining))
                    raise RuntimeError(f"Workflow deadlock or failed dependency: {blocked}")

                for node in ready[: max(1, workflow.max_concurrency)]:
                    execution = run.nodes[node.id]
                    if node.requires_approval:
                        execution.status = "AWAITING_APPROVAL"
                        run.status = "AWAITING_APPROVAL"
                        self._persist(run)
                        return run
                    self._execute_node(node, execution, context, run)
                    if execution.status != "COMPLETED":
                        run.status = "FAILED"
                        run.finished_at = time.time()
                        self._persist(run)
                        return run
                    context[node.id] = execution.output
                    remaining.pop(node.id)

            run.status = "COMPLETED"
            run.finished_at = time.time()
            self._persist(run)
            return run
        except Exception as exc:
            run.status = "FAILED"
            run.finished_at = time.time()
            for node_id in remaining:
                if run.nodes[node_id].status == "PENDING":
                    run.nodes[node_id].error = str(exc)
            self._persist(run)
            return run

    def resume(self, run_id: str, *, approval_granted: bool = False) -> WorkflowRun:
        run = self._load(run_id)
        if run.status != "AWAITING_APPROVAL":
            raise ValueError(f"Run {run_id} is not awaiting approval")
        if not approval_granted:
            return run
        workflow = self.workflows[run.workflow_id]
        # Resume from persisted node state; completed nodes are never repeated.
        run.status = "RUNNING"
        context = {node_id: execution.output for node_id, execution in run.nodes.items() if execution.status == "COMPLETED"}
        remaining = {n.id: n for n in workflow.nodes if run.nodes[n.id].status != "COMPLETED"}
        for node in remaining.values():
            if node.requires_approval:
                run.nodes[node.id].status = "PENDING"
        # Approval itself is an execution boundary, not a new workflow.
        for node in list(remaining.values()):
            if all(run.nodes[d].status == "COMPLETED" for d in node.depends_on):
                self._execute_node(node, run.nodes[node.id], context, run)
                if run.nodes[node.id].status == "COMPLETED":
                    context[node.id] = run.nodes[node.id].output
        run.status = "COMPLETED" if all(x.status == "COMPLETED" for x in run.nodes.values()) else "FAILED"
        run.finished_at = time.time() if run.status == "COMPLETED" else None
        self._persist(run)
        return run

    def _execute_node(self, node: WorkflowNode, execution: NodeExecution, context: dict[str, Any], run: WorkflowRun) -> None:
        handler = self.handlers.get(node.kind)
        if handler is None:
            execution.status = "FAILED"
            execution.error = f"No handler registered for node kind: {node.kind}"
            return
        for attempt in range(node.retry_limit + 1):
            execution.attempts = attempt + 1
            execution.status = "RUNNING"
            try:
                inputs = {key: context[key] for key in node.input_from if key in context}
                execution.output = handler(node=node, inputs=inputs, context=context, run=run)
                execution.status = "COMPLETED"
                execution.error = None
                return
            except Exception as exc:
                execution.error = f"{type(exc).__name__}: {exc}"
                if attempt < node.retry_limit:
                    execution.status = "RETRYING"
                    continue
        execution.status = "FAILED"

    def _validate(self, workflow: WorkflowDefinition) -> None:
        ids = [n.id for n in workflow.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("Workflow node IDs must be unique")
        known = set(ids)
        for node in workflow.nodes:
            unknown = set(node.depends_on) - known
            if unknown:
                raise ValueError(f"Node {node.id} depends on unknown nodes: {sorted(unknown)}")
            if node.retry_limit < 0:
                raise ValueError("retry_limit cannot be negative")
        # Kahn-style cycle check.
        pending = {n.id: set(n.depends_on) for n in workflow.nodes}
        while pending:
            free = [node_id for node_id, deps in pending.items() if not deps]
            if not free:
                raise ValueError("Workflow contains a dependency cycle")
            for node_id in free:
                pending.pop(node_id)
                for deps in pending.values():
                    deps.discard(node_id)

    def _persist(self, run: WorkflowRun) -> None:
        (self.state_dir / f"{run.run_id}.json").write_text(json.dumps(run.to_dict(), indent=2), encoding="utf-8")

    def _load(self, run_id: str) -> WorkflowRun:
        raw = json.loads((self.state_dir / f"{run_id}.json").read_text(encoding="utf-8"))
        run = WorkflowRun(raw["run_id"], raw["workflow_id"], raw["status"], started_at=raw.get("started_at"), finished_at=raw.get("finished_at"))
        run.nodes = {k: NodeExecution(**v) for k, v in raw["nodes"].items()}
        return run

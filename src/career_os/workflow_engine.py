"""Local-first AgentFlow workflow engine.

The execution model combines the DeepSeek Harness separation of replaceable
capabilities with Dagu-style workflow semantics: dependency graphs, bounded
concurrency, retry policies, timeouts, overlap control, durable state and
human waitpoints. No external workflow service is required.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
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
    retry_interval_sec: float = 0.0
    timeout_sec: float | None = None
    continue_on_failure: bool = False
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkflowDefinition:
    id: str
    name: str
    nodes: tuple[WorkflowNode, ...]
    schedule: str | None = None
    max_concurrency: int = 1
    overlap_policy: str = "allow"  # allow | skip


@dataclass
class NodeExecution:
    node_id: str
    status: str = "PENDING"
    attempts: int = 0
    output: Any = None
    error: str | None = None
    started_at: float | None = None
    finished_at: float | None = None


@dataclass
class WorkflowRun:
    run_id: str
    workflow_id: str
    status: str = "PENDING"
    nodes: dict[str, NodeExecution] = field(default_factory=dict)
    started_at: float | None = None
    finished_at: float | None = None
    input_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "workflow_id": self.workflow_id,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "input_data": self.input_data,
            "nodes": {k: vars(v) for k, v in self.nodes.items()},
        }


class WorkflowEngine:
    """Durable local workflow coordinator for AgentFlow."""

    def __init__(self, *, state_dir: str | Path = "jobs/workflow_runtime") -> None:
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.workflows: dict[str, WorkflowDefinition] = {}
        self.handlers: dict[str, Callable[..., Any]] = {}
        self._active_runs: dict[str, str] = {}
        self._lock = threading.RLock()

    def register(self, workflow: WorkflowDefinition) -> None:
        self._validate(workflow)
        if workflow.overlap_policy not in {"allow", "skip"}:
            raise ValueError("overlap_policy must be allow or skip")
        self.workflows[workflow.id] = workflow

    def register_handler(self, kind: str, handler: Callable[..., Any]) -> None:
        self.handlers[kind] = handler

    def run(self, workflow_id: str, *, input_data: dict[str, Any] | None = None, run_id: str | None = None) -> WorkflowRun:
        workflow = self.workflows[workflow_id]
        with self._lock:
            active = self._active_runs.get(workflow_id)
            if workflow.overlap_policy == "skip" and active:
                active_run = self._load(active)
                if active_run.status in {"RUNNING", "AWAITING_APPROVAL"}:
                    return active_run
            run = WorkflowRun(
                run_id or f"{workflow.id}-{int(time.time() * 1000)}",
                workflow.id,
                input_data=dict(input_data or {}),
            )
            run.nodes = {n.id: NodeExecution(n.id) for n in workflow.nodes}
            run.status = "RUNNING"
            run.started_at = time.time()
            self._active_runs[workflow_id] = run.run_id
            self._persist(run)

        context: dict[str, Any] = dict(run.input_data)
        remaining = {n.id: n for n in workflow.nodes}
        try:
            while remaining:
                ready = [n for n in remaining.values() if all(run.nodes[d].status == "COMPLETED" for d in n.depends_on)]
                if not ready:
                    blocked = ", ".join(sorted(remaining))
                    raise RuntimeError(f"Workflow deadlock or failed dependency: {blocked}")

                runnable = [n for n in ready if not n.requires_approval]
                gates = [n for n in ready if n.requires_approval]
                if gates:
                    # Complete independent ready work first; then persist a durable waitpoint.
                    if runnable:
                        self._execute_batch(runnable[: max(1, workflow.max_concurrency)], run, context)
                        for node in runnable[: max(1, workflow.max_concurrency)]:
                            if run.nodes[node.id].status == "COMPLETED":
                                context[node.id] = run.nodes[node.id].output
                                remaining.pop(node.id)
                            elif not node.continue_on_failure:
                                return self._finish_failed(run)
                        self._persist(run)
                        continue
                    gate = gates[0]
                    run.nodes[gate.id].status = "AWAITING_APPROVAL"
                    run.status = "AWAITING_APPROVAL"
                    self._persist(run)
                    return run

                batch = runnable[: max(1, workflow.max_concurrency)]
                self._execute_batch(batch, run, context)
                for node in batch:
                    execution = run.nodes[node.id]
                    if execution.status == "COMPLETED":
                        context[node.id] = execution.output
                        remaining.pop(node.id)
                    elif node.continue_on_failure:
                        context[node.id] = {"error": execution.error, "status": "FAILED"}
                        remaining.pop(node.id)
                    else:
                        return self._finish_failed(run)
                self._persist(run)

            run.status = "COMPLETED"
            run.finished_at = time.time()
            self._clear_active(run)
            self._persist(run)
            return run
        except Exception as exc:
            run.status = "FAILED"
            run.finished_at = time.time()
            for node_id in remaining:
                if run.nodes[node_id].status == "PENDING":
                    run.nodes[node_id].error = str(exc)
            self._clear_active(run)
            self._persist(run)
            return run

    def resume(self, run_id: str, *, approval_granted: bool = False) -> WorkflowRun:
        run = self._load(run_id)
        if run.status != "AWAITING_APPROVAL":
            raise ValueError(f"Run {run_id} is not awaiting approval")
        workflow = self.workflows[run.workflow_id]
        if not approval_granted:
            return run
        for execution in run.nodes.values():
            if execution.status == "AWAITING_APPROVAL":
                execution.status = "PENDING"
        run.status = "RUNNING"
        context = dict(run.input_data)
        context.update({k: v.output for k, v in run.nodes.items() if v.status == "COMPLETED"})
        remaining = {n.id: n for n in workflow.nodes if run.nodes[n.id].status != "COMPLETED"}
        self._active_runs[workflow.id] = run.run_id
        while remaining:
            ready = [n for n in remaining.values() if all(run.nodes[d].status == "COMPLETED" for d in n.depends_on)]
            if not ready:
                run.status = "FAILED"
                run.finished_at = time.time()
                self._clear_active(run)
                self._persist(run)
                return run
            gates = [n for n in ready if n.requires_approval]
            if gates:
                gate = gates[0]
                run.nodes[gate.id].status = "AWAITING_APPROVAL"
                run.status = "AWAITING_APPROVAL"
                self._persist(run)
                return run
            batch = ready[: max(1, workflow.max_concurrency)]
            self._execute_batch(batch, run, context)
            for node in batch:
                execution = run.nodes[node.id]
                if execution.status == "COMPLETED":
                    context[node.id] = execution.output
                    remaining.pop(node.id)
                elif node.continue_on_failure:
                    context[node.id] = {"error": execution.error, "status": "FAILED"}
                    remaining.pop(node.id)
                else:
                    return self._finish_failed(run)
            self._persist(run)
        run.status = "COMPLETED"
        run.finished_at = time.time()
        self._clear_active(run)
        self._persist(run)
        return run

    def _execute_batch(self, nodes: list[WorkflowNode], run: WorkflowRun, context: dict[str, Any]) -> None:
        if len(nodes) == 1:
            self._execute_node(nodes[0], run.nodes[nodes[0].id], context, run)
            return
        with ThreadPoolExecutor(max_workers=len(nodes), thread_name_prefix="agentflow") as pool:
            futures = {
                pool.submit(self._execute_node, node, run.nodes[node.id], dict(context), run): node
                for node in nodes
            }
            for future, node in futures.items():
                try:
                    future.result(timeout=node.timeout_sec + 1 if node.timeout_sec else None)
                except FutureTimeout:
                    execution = run.nodes[node.id]
                    execution.status = "FAILED"
                    execution.error = f"TimeoutError: node exceeded {node.timeout_sec}s"
                except Exception as exc:
                    execution = run.nodes[node.id]
                    execution.status = "FAILED"
                    execution.error = f"{type(exc).__name__}: {exc}"

    def _execute_node(self, node: WorkflowNode, execution: NodeExecution, context: dict[str, Any], run: WorkflowRun) -> None:
        handler = self.handlers.get(node.kind)
        if handler is None:
            execution.status = "FAILED"
            execution.error = f"No handler registered for node kind: {node.kind}"
            return
        for attempt in range(node.retry_limit + 1):
            execution.attempts = attempt + 1
            execution.status = "RUNNING"
            execution.started_at = time.time()
            try:
                inputs = {key: context[key] for key in node.input_from if key in context}
                value = handler(node=node, inputs=inputs, context=context, run=run)
                if inspect.isawaitable(value):
                    value = self._await(value)
                execution.output = value
                execution.status = "COMPLETED"
                execution.error = None
                execution.finished_at = time.time()
                return
            except Exception as exc:
                execution.error = f"{type(exc).__name__}: {exc}"
                execution.finished_at = time.time()
                if attempt < node.retry_limit:
                    execution.status = "RETRYING"
                    if node.retry_interval_sec > 0:
                        time.sleep(node.retry_interval_sec)
                    continue
        execution.status = "FAILED"

    @staticmethod
    def _await(value: Any) -> Any:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(value)
        result: list[Any] = []
        error: list[BaseException] = []
        def runner() -> None:
            try:
                result.append(asyncio.run(value))
            except BaseException as exc:
                error.append(exc)
        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        thread.join()
        if error:
            raise error[0]
        return result[0] if result else None

    def _validate(self, workflow: WorkflowDefinition) -> None:
        ids = [n.id for n in workflow.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("Workflow node IDs must be unique")
        known = set(ids)
        if workflow.max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        for node in workflow.nodes:
            unknown = set(node.depends_on) - known
            if unknown:
                raise ValueError(f"Node {node.id} depends on unknown nodes: {sorted(unknown)}")
            if node.retry_limit < 0 or node.retry_interval_sec < 0:
                raise ValueError("retry policy values cannot be negative")
            if node.timeout_sec is not None and node.timeout_sec <= 0:
                raise ValueError("timeout_sec must be positive")
        pending = {n.id: set(n.depends_on) for n in workflow.nodes}
        while pending:
            free = [node_id for node_id, deps in pending.items() if not deps]
            if not free:
                raise ValueError("Workflow contains a dependency cycle")
            for node_id in free:
                pending.pop(node_id)
                for deps in pending.values():
                    deps.discard(node_id)

    def _finish_failed(self, run: WorkflowRun) -> WorkflowRun:
        run.status = "FAILED"
        run.finished_at = time.time()
        self._clear_active(run)
        self._persist(run)
        return run

    def _clear_active(self, run: WorkflowRun) -> None:
        with self._lock:
            if self._active_runs.get(run.workflow_id) == run.run_id:
                self._active_runs.pop(run.workflow_id, None)

    def _persist(self, run: WorkflowRun) -> None:
        path = self.state_dir / f"{run.run_id}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(run.to_dict(), indent=2, default=str), encoding="utf-8")
        tmp.replace(path)

    def _load(self, run_id: str) -> WorkflowRun:
        raw = json.loads((self.state_dir / f"{run_id}.json").read_text(encoding="utf-8"))
        run = WorkflowRun(
            raw["run_id"], raw["workflow_id"], raw["status"],
            started_at=raw.get("started_at"), finished_at=raw.get("finished_at"),
            input_data=raw.get("input_data", {}),
        )
        run.nodes = {k: NodeExecution(**v) for k, v in raw["nodes"].items()}
        return run

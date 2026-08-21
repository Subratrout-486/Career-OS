"""Reusable child-workflow execution for AgentFlow.

Inspired by Dagu's synchronous ``dag.run`` and asynchronous ``dag.enqueue``
semantics and Activepieces' callable subflows. A child workflow is a real
WorkflowEngine run with its own durable run state; the parent receives a
small, serializable result boundary.
"""
from __future__ import annotations

from typing import Any

from .workflow_engine import WorkflowEngine, WorkflowNode, WorkflowRun


def register_subworkflow_handler(engine: WorkflowEngine) -> None:
    engine.register_handler("SUBWORKFLOW", lambda **kwargs: subworkflow_handler(engine=engine, **kwargs))


def subworkflow_handler(*, engine: WorkflowEngine, node: WorkflowNode, inputs: dict[str, Any], context: dict[str, Any], run: WorkflowRun) -> dict[str, Any]:
    config = dict(node.config or {})
    workflow_id = config.get("workflow_id")
    if not isinstance(workflow_id, str) or not workflow_id:
        raise ValueError("SUBWORKFLOW requires config.workflow_id")
    if workflow_id == run.workflow_id:
        raise ValueError("SUBWORKFLOW cannot directly invoke its own parent workflow")
    if workflow_id not in engine.workflows:
        raise ValueError(f"Unknown child workflow: {workflow_id}")

    mode = str(config.get("mode", "RUN")).upper()
    if mode not in {"RUN", "ENQUEUE"}:
        raise ValueError("SUBWORKFLOW mode must be RUN or ENQUEUE")

    child_input = config.get("input", {})
    if not isinstance(child_input, dict):
        raise ValueError("SUBWORKFLOW config.input must be an object")
    child_input = _resolve_input(child_input, context, inputs)
    child_input.setdefault("parent_run_id", run.run_id)
    child_input.setdefault("parent_node_id", node.id)

    if mode == "RUN":
        child = engine.run(workflow_id, input_data=child_input)
        return _result(child, mode=mode)

    # ENQUEUE is deliberately a durable local queue boundary rather than a
    # background thread. The scheduler/worker can consume this record later,
    # while the parent continues immediately and retains the child run id.
    child_run_id = f"{workflow_id}-queued-{run.run_id}-{node.id}"
    queue_record = {
        "run_id": child_run_id,
        "workflow_id": workflow_id,
        "input_data": child_input,
        "status": "QUEUED",
        "parent_run_id": run.run_id,
        "parent_node_id": node.id,
    }
    engine._persist_queue_record(queue_record)
    return {
        "mode": mode,
        "status": "QUEUED",
        "child_run_id": child_run_id,
        "workflow_id": workflow_id,
    }


def _resolve_input(value: Any, context: dict[str, Any], inputs: dict[str, Any]) -> Any:
    values = {**context, **inputs}
    if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
        current: Any = values
        for part in value[2:-2].strip().split("."):
            if not isinstance(current, dict) or part not in current:
                raise ValueError(f"SUBWORKFLOW input reference not found: {value}")
            current = current[part]
        return current
    if isinstance(value, dict):
        return {k: _resolve_input(v, context, inputs) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_input(v, context, inputs) for v in value]
    return value


def _result(child: WorkflowRun, *, mode: str) -> dict[str, Any]:
    return {
        "mode": mode,
        "status": child.status,
        "child_run_id": child.run_id,
        "workflow_id": child.workflow_id,
        "outputs": {key: value.output for key, value in child.nodes.items() if value.status == "COMPLETED"},
    }

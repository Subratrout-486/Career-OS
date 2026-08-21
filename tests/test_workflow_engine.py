from pathlib import Path
import asyncio
import time

import pytest

from career_os.workflow_engine import WorkflowDefinition, WorkflowEngine, WorkflowNode


def test_dag_executes_in_dependency_order(tmp_path: Path):
    engine = WorkflowEngine(state_dir=tmp_path)
    seen = []

    def handler(*, node, inputs, context, run):
        seen.append(node.id)
        return {"node": node.id, "inputs": inputs}

    engine.register_handler("step", handler)
    engine.register(WorkflowDefinition(
        id="demo", name="demo",
        nodes=(WorkflowNode("a", "step"), WorkflowNode("b", "step", depends_on=("a",), input_from=("a",)), WorkflowNode("c", "step", depends_on=("b",), input_from=("b",))),
    ))
    run = engine.run("demo", input_data={"seed": True})
    assert run.status == "COMPLETED"
    assert seen == ["a", "b", "c"]
    assert (tmp_path / f"{run.run_id}.json").exists()


def test_retry_reexecutes_same_node_and_waits(tmp_path: Path):
    engine = WorkflowEngine(state_dir=tmp_path)
    attempts = {"count": 0}
    timestamps = []

    def flaky(*, node, inputs, context, run):
        attempts["count"] += 1
        timestamps.append(time.monotonic())
        if attempts["count"] == 1:
            raise RuntimeError("transient")
        return {"ok": True}

    engine.register_handler("flaky", flaky)
    engine.register(WorkflowDefinition("retry", "retry", (WorkflowNode("a", "flaky", retry_limit=1, retry_interval_sec=0.02),)))
    run = engine.run("retry")
    assert run.status == "COMPLETED"
    assert run.nodes["a"].attempts == 2
    assert timestamps[1] - timestamps[0] >= 0.015


def test_cycle_is_rejected(tmp_path: Path):
    engine = WorkflowEngine(state_dir=tmp_path)
    with pytest.raises(ValueError, match="cycle"):
        engine.register(WorkflowDefinition("cycle", "cycle", (WorkflowNode("a", "step", depends_on=("b",)), WorkflowNode("b", "step", depends_on=("a",)))))


def test_approval_pauses_and_resume_does_not_repeat_completed_nodes(tmp_path: Path):
    engine = WorkflowEngine(state_dir=tmp_path)
    counts = {"pre": 0, "approval": 0, "post": 0}

    def pre(*, node, inputs, context, run):
        counts["pre"] += 1
        return {"ready": True}

    def approval(*, node, inputs, context, run):
        counts["approval"] += 1
        return {"approved": True}

    def post(*, node, inputs, context, run):
        counts["post"] += 1
        return {"done": True}

    engine.register_handler("pre", pre)
    engine.register_handler("approval", approval)
    engine.register_handler("post", post)
    engine.register(WorkflowDefinition("approval", "approval", (
        WorkflowNode("pre", "pre"),
        WorkflowNode("gate", "approval", depends_on=("pre",), requires_approval=True),
        WorkflowNode("post", "post", depends_on=("gate",), input_from=("gate",)),
    )))
    run = engine.run("approval")
    assert run.status == "AWAITING_APPROVAL"
    run = engine.resume(run.run_id, approval_granted=True)
    assert run.status == "COMPLETED"
    assert counts == {"pre": 1, "approval": 1, "post": 1}


def test_independent_ready_nodes_run_concurrently(tmp_path: Path):
    engine = WorkflowEngine(state_dir=tmp_path)
    started = {"a": 0.0, "b": 0.0}

    def work(*, node, inputs, context, run):
        started[node.id] = time.monotonic()
        time.sleep(0.05)
        return node.id

    engine.register_handler("work", work)
    engine.register(WorkflowDefinition("parallel", "parallel", (WorkflowNode("a", "work"), WorkflowNode("b", "work")), max_concurrency=2))
    run = engine.run("parallel")
    assert run.status == "COMPLETED"
    assert abs(started["a"] - started["b"]) < 0.04


def test_async_handler_is_supported(tmp_path: Path):
    engine = WorkflowEngine(state_dir=tmp_path)

    async def async_work(*, node, inputs, context, run):
        await asyncio.sleep(0)
        return {"async": True}

    engine.register_handler("async", async_work)
    engine.register(WorkflowDefinition("async", "async", (WorkflowNode("a", "async"),)))
    run = engine.run("async")
    assert run.status == "COMPLETED"
    assert run.nodes["a"].output == {"async": True}


def test_overlap_policy_skips_active_run(tmp_path: Path):
    engine = WorkflowEngine(state_dir=tmp_path)
    engine.register_handler("noop", lambda **kwargs: {"ok": True})
    engine.register(WorkflowDefinition("scheduled", "scheduled", (WorkflowNode("a", "noop"),), overlap_policy="skip"))
    first = engine.run("scheduled")
    assert first.status == "COMPLETED"
    assert engine._active_runs.get("scheduled") is None

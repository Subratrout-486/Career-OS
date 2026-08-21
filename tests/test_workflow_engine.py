from pathlib import Path

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
        id="demo",
        name="demo",
        nodes=(
            WorkflowNode("a", "step"),
            WorkflowNode("b", "step", depends_on=("a",), input_from=("a",)),
            WorkflowNode("c", "step", depends_on=("b",), input_from=("b",)),
        ),
    ))
    run = engine.run("demo", input_data={"seed": True})
    assert run.status == "COMPLETED"
    assert seen == ["a", "b", "c"]
    assert (tmp_path / f"{run.run_id}.json").exists()


def test_retry_reexecutes_same_node(tmp_path: Path):
    engine = WorkflowEngine(state_dir=tmp_path)
    attempts = {"count": 0}

    def flaky(*, node, inputs, context, run):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("transient")
        return {"ok": True}

    engine.register_handler("flaky", flaky)
    engine.register(WorkflowDefinition("retry", "retry", (WorkflowNode("a", "flaky", retry_limit=1),)))
    run = engine.run("retry")
    assert run.status == "COMPLETED"
    assert run.nodes["a"].attempts == 2


def test_cycle_is_rejected(tmp_path: Path):
    engine = WorkflowEngine(state_dir=tmp_path)
    with pytest.raises(ValueError, match="cycle"):
        engine.register(WorkflowDefinition(
            "cycle", "cycle", (
                WorkflowNode("a", "step", depends_on=("b",)),
                WorkflowNode("b", "step", depends_on=("a",)),
            )
        ))


def test_approval_pauses_and_resume_does_not_repeat_completed_nodes(tmp_path: Path):
    engine = WorkflowEngine(state_dir=tmp_path)
    counts = {"pre": 0, "approval": 0}

    def pre(*, node, inputs, context, run):
        counts["pre"] += 1
        return {"ready": True}

    def approval(*, node, inputs, context, run):
        counts["approval"] += 1
        return {"approved": True}

    engine.register_handler("pre", pre)
    engine.register_handler("approval", approval)
    engine.register(WorkflowDefinition(
        "approval", "approval", (
            WorkflowNode("pre", "pre"),
            WorkflowNode("gate", "approval", depends_on=("pre",), requires_approval=True),
        )
    ))
    run = engine.run("approval")
    assert run.status == "AWAITING_APPROVAL"
    run = engine.resume(run.run_id, approval_granted=True)
    assert run.status == "COMPLETED"
    assert counts == {"pre": 1, "approval": 1}

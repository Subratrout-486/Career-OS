from pathlib import Path

from career_os.subworkflow import register_subworkflow_handler
from career_os.workflow_engine import WorkflowDefinition, WorkflowEngine, WorkflowNode


def test_sync_subworkflow_returns_child_run_and_outputs(tmp_path: Path):
    engine = WorkflowEngine(state_dir=tmp_path)
    register_subworkflow_handler(engine)

    engine.register_handler("echo", lambda *, node, inputs, context, run: {"value": context["value"]})
    engine.register(WorkflowDefinition("child", "child", (WorkflowNode("echo", "echo"),)))
    engine.register(WorkflowDefinition(
        "parent", "parent", (
            WorkflowNode("child", "SUBWORKFLOW", config={"workflow_id": "child", "mode": "RUN", "input": {"value": "{{value}}"}}),
        ),
    ))

    result = engine.run("parent", input_data={"value": "ok"})
    assert result.status == "COMPLETED"
    child_result = result.nodes["child"].output
    assert child_result["status"] == "COMPLETED"
    assert child_result["outputs"]["echo"] == {"value": "ok"}
    assert (tmp_path / f"{child_result['child_run_id']}.json").exists()


def test_enqueue_subworkflow_is_durable_and_parent_continues(tmp_path: Path):
    engine = WorkflowEngine(state_dir=tmp_path)
    register_subworkflow_handler(engine)
    engine.register(WorkflowDefinition("child", "child", ()))
    engine.register(WorkflowDefinition(
        "parent", "parent", (
            WorkflowNode("queue", "SUBWORKFLOW", config={"workflow_id": "child", "mode": "ENQUEUE"}),
        ),
    ))

    result = engine.run("parent")
    assert result.status == "COMPLETED"
    child_result = result.nodes["queue"].output
    assert child_result["status"] == "QUEUED"
    queue_files = list((tmp_path / "queue").glob("*.json"))
    assert len(queue_files) == 1


def test_subworkflow_rejects_self_reference(tmp_path: Path):
    engine = WorkflowEngine(state_dir=tmp_path)
    register_subworkflow_handler(engine)
    engine.register(WorkflowDefinition("loop", "loop", (WorkflowNode("child", "SUBWORKFLOW", config={"workflow_id": "loop"}),)))
    result = engine.run("loop")
    assert result.status == "FAILED"
    assert "own parent" in (result.nodes["child"].error or "")

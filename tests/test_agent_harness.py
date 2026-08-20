from __future__ import annotations

from pathlib import Path

from career_os.agent_harness import ActionPolicy, AgentHarness, HarnessRecovery, ToolExecutionPipeline
from career_os.control_plane import ApprovalStatus, ControlPlaneStore, TaskRecord, TaskStatus


def store(tmp_path: Path) -> ControlPlaneStore:
    return ControlPlaneStore(tmp_path / "control-plane.json")


def test_session_step_checkpoint_and_recovery(tmp_path: Path):
    cp = store(tmp_path)
    task = cp.create_task(TaskRecord(objective="test objective", status=TaskStatus.RUNNING))
    harness = AgentHarness(cp)

    harness.start_session(task.id, objective="test objective")
    harness.start_step(task.id, step_index=1, model="test-model")
    harness.tool_call(task.id, step_index=1, tool="browser", arguments={"url": "https://example.com"})

    checkpoint = AgentHarness(cp).checkpoint(task.id)
    assert checkpoint is not None
    assert checkpoint.phase == "TOOL_CALLING"
    assert checkpoint.step_index == 1

    pending = HarnessRecovery(cp).inspect()
    assert pending[0]["action_required"] == "RECONCILE_EXTERNAL_SIDE_EFFECT"


def test_high_risk_action_fails_closed_when_approval_unavailable(tmp_path: Path):
    cp = store(tmp_path)
    task = cp.create_task(TaskRecord(objective="submit application", status=TaskStatus.RUNNING))
    policy = ActionPolicy(cp)

    decision = policy.decide(
        task_id=task.id,
        action="SUBMIT_APPLICATION",
        resource_type="job",
        resource_id="job-1",
        summary="Submit application",
        approval_available=False,
    )
    assert decision.status == "BLOCKED"
    assert cp.approvals() == []


def test_approved_action_is_one_shot_and_verified(tmp_path: Path):
    cp = store(tmp_path)
    task = cp.create_task(TaskRecord(objective="submit application", status=TaskStatus.RUNNING))
    policy = ActionPolicy(cp)
    requested = policy.decide(
        task_id=task.id,
        action="SUBMIT_APPLICATION",
        resource_type="job",
        resource_id="job-1",
        summary="Submit application",
    )
    assert requested.status == "WAITING_FOR_APPROVAL"
    cp.decide_approval(requested.approval_id, ApprovalStatus.APPROVED, decided_by="user")

    pipeline = ToolExecutionPipeline(policy=policy, harness=AgentHarness(cp))
    calls = {"count": 0}

    def execute():
        calls["count"] += 1
        return {"submitted": True}

    decision, result = pipeline.execute(
        task_id=task.id,
        step_index=1,
        tool="browser_submit",
        arguments={"job_id": "job-1"},
        action="SUBMIT_APPLICATION",
        resource_type="job",
        resource_id="job-1",
        summary="Submit application",
        executor=execute,
        verifier=lambda value: value == {"submitted": True},
        approval_id=requested.approval_id,
    )
    assert decision.status == "COMPLETED"
    assert result == {"submitted": True}
    assert calls["count"] == 1

    second = policy.consume_approval(requested.approval_id, task_id=task.id, decided_by="user")
    assert second.status == "BLOCKED"

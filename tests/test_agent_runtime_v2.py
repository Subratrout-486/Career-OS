from career_os.agent_runtime import MultiAgentRuntime, default_registry
from career_os.control_plane import ApprovalStatus, ControlPlaneStore, TaskStatus


def test_registry_exposes_career_agents(tmp_path):
    runtime = MultiAgentRuntime(ControlPlaneStore(tmp_path / "cp.json"), default_registry())
    ids = {spec.id for spec in runtime.registry.list()}
    assert {"ceo", "job-research", "career-analyst", "resume-agent", "engineering-copilot", "application-agent"} <= ids


def test_agent_run_is_durable(tmp_path):
    store = ControlPlaneStore(tmp_path / "cp.json")
    runtime = MultiAgentRuntime(store, default_registry())
    result = runtime.run(agent_id="career-analyst", objective="Score this job")
    assert result.status == TaskStatus.COMPLETED.value
    task = store.get_task(result.task_id)
    assert task.status == TaskStatus.COMPLETED
    assert task.result["mode"] == "career-analysis"
    assert any(e.event_type == "SESSION_STARTED" for e in store.audit_events(result.task_id))
    assert any(e.event_type == "SESSION_COMPLETED" for e in store.audit_events(result.task_id))


def test_parent_can_delegate_to_specialist(tmp_path):
    store = ControlPlaneStore(tmp_path / "cp.json")
    runtime = MultiAgentRuntime(store, default_registry())
    parent = runtime.run(agent_id="ceo", objective="Find suitable jobs")
    child = runtime.delegate(parent_task_id=parent.task_id, agent_id="job-research", objective="Research jobs")
    assert child.status == TaskStatus.COMPLETED.value
    assert child.task_id != parent.task_id
    assert store.get_task(child.task_id).parent_task_id == parent.task_id
    assert len(store.messages(parent.task_id)) == 1


def test_critical_action_fails_closed_without_approval(tmp_path):
    store = ControlPlaneStore(tmp_path / "cp.json")
    runtime = MultiAgentRuntime(store, default_registry())
    task = runtime.run(agent_id="application-agent", objective="Prepare application")
    decision, result = runtime.execute_external_action(
        task_id=task.task_id,
        step_index=1,
        tool="browser",
        arguments={"action": "submit"},
        action="SUBMIT_APPLICATION",
        resource_type="job_application",
        resource_id="job-123",
        summary="Submit application",
        executor=lambda: "submitted",
        verifier=lambda value: True,
        approval_available=False,
    )
    assert decision.status == "BLOCKED"
    assert result is None


def test_approval_is_one_shot(tmp_path):
    store = ControlPlaneStore(tmp_path / "cp.json")
    runtime = MultiAgentRuntime(store, default_registry())
    task = runtime.run(agent_id="application-agent", objective="Prepare application")
    decision, _ = runtime.execute_external_action(
        task_id=task.task_id,
        step_index=1,
        tool="browser",
        arguments={"action": "submit"},
        action="SUBMIT_APPLICATION",
        resource_type="job_application",
        resource_id="job-123",
        summary="Submit application",
        executor=lambda: "submitted",
        verifier=lambda value: True,
    )
    assert decision.status == "WAITING_FOR_APPROVAL"
    approval_id = decision.approval_id
    store.decide_approval(approval_id, ApprovalStatus.APPROVED, decided_by="user")
    approved, result = runtime.execute_external_action(
        task_id=task.task_id,
        step_index=1,
        tool="browser",
        arguments={"action": "submit"},
        action="SUBMIT_APPLICATION",
        resource_type="job_application",
        resource_id="job-123",
        summary="Submit application",
        executor=lambda: "submitted",
        verifier=lambda value: True,
        approval_id=approval_id,
    )
    assert approved.status == "COMPLETED"
    assert result == "submitted"
    second, _ = runtime.execute_external_action(
        task_id=task.task_id,
        step_index=1,
        tool="browser",
        arguments={"action": "submit"},
        action="SUBMIT_APPLICATION",
        resource_type="job_application",
        resource_id="job-123",
        summary="Submit application",
        executor=lambda: "submitted-again",
        verifier=lambda value: True,
        approval_id=approval_id,
    )
    assert second.status == "BLOCKED"

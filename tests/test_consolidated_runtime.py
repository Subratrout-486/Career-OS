from __future__ import annotations

from pathlib import Path

import pytest

from career_os.agent_harness import AgentHarness, ToolExecutionPipeline
from career_os.agent_runtime import MultiAgentRuntime
from career_os.control_plane import ControlPlaneStore, TaskRecord, TaskStatus


class FakeProviderRuntime:
    async def fit(self, profile, job, evidence_pack=None, jd_analysis=None):
        return {"stage": "fit", "profile": profile, "company": job.company}

    async def resume(self, profile, job, fit, evidence_pack=None, jd_analysis=None):
        return {"stage": "resume", "company": job.company}

    async def challenge(self, profile, job, fit, resume, evidence_pack=None):
        return "independent review"


def make_store(tmp_path: Path) -> ControlPlaneStore:
    return ControlPlaneStore(tmp_path / "control-plane.json")


@pytest.mark.asyncio
async def test_real_specialist_executes_through_consolidated_runtime(tmp_path: Path):
    from career_os.models import Job

    store = make_store(tmp_path)
    parent = store.create_task(TaskRecord(objective="run career analysis", status=TaskStatus.RUNNING))
    runtime = MultiAgentRuntime(store, provider_runtime=FakeProviderRuntime())

    output = await runtime.execute_real_agent_async(
        parent_task_id=parent.id,
        agent_id="career-analyst",
        objective="Analyze fit",
        context={"profile": "verified profile", "job": Job(title="Engineer", company="Example", description="Build systems")},
    )

    assert output["stage"] == "fit"
    children = [task for task in store.tasks() if task.parent_task_id == parent.id]
    assert len(children) == 1
    assert children[0].status == TaskStatus.COMPLETED
    assert children[0].payload["runtime"] == "career-os-harness-v1"
    assert store.messages(parent.id)[0].to_agent == "career-analyst"
    assert {event.event_type for event in store.audit_events(children[0].id)} >= {
        "SESSION_STARTED", "STEP_STARTED", "STEP_COMPLETED", "SESSION_COMPLETED"
    }


@pytest.mark.asyncio
async def test_async_delegation_and_recovery_are_durable(tmp_path: Path):
    store = make_store(tmp_path)
    parent = store.create_task(TaskRecord(objective="delegate", status=TaskStatus.RUNNING))
    runtime = MultiAgentRuntime(store)

    result = await runtime.delegate_async(
        parent_task_id=parent.id,
        agent_id="career-analyst",
        objective="Perform bounded analysis",
        context={"request": "safe"},
    )

    assert result.status == TaskStatus.COMPLETED.value
    assert [item for item in runtime.recover() if item["task_id"] == result.task_id] == []

    waiting = store.create_task(TaskRecord(objective="resume me", status=TaskStatus.WAITING))
    AgentHarness(store).start_session(waiting.id, objective=waiting.objective)
    pending = MultiAgentRuntime(store).recover()
    waiting_pending = next(item for item in pending if item["task_id"] == waiting.id)
    assert waiting_pending["action_required"] == "RESUME_FROM_CHECKPOINT"


def test_verification_failure_is_audited_and_owner_takeover_is_persisted(tmp_path: Path):
    store = make_store(tmp_path)
    task = store.create_task(TaskRecord(objective="external action", status=TaskStatus.RUNNING))
    runtime = MultiAgentRuntime(store)
    decision, result = runtime.execute_external_action(
        task_id=task.id,
        step_index=1,
        tool="browser",
        arguments={"operation": "prepare"},
        action="OPEN_BROWSER_CONTEXT",
        resource_type="job",
        resource_id="job-1",
        summary="Prepare a browser context",
        executor=lambda: {"opened": True},
        verifier=lambda value: False,
    )
    assert decision.status == "FAILED_VERIFICATION"
    assert result == {"opened": True}
    assert any(event.event_type == "TOOL_CALL_COMPLETED" and event.decision == "UNVERIFIED" for event in store.audit_events(task.id))

    approval = runtime.request_human_takeover(task_id=task.id, boundary="Owner must complete the authenticated browser authorization.")
    assert approval.status.value == "PENDING"
    assert store.get_task(task.id).status == TaskStatus.AWAITING_APPROVAL
    assert any(event.event_type == "HUMAN_TAKEOVER_REQUIRED" for event in store.audit_events(task.id))


def test_unconfigured_runtime_does_not_claim_provider_capability(tmp_path: Path):
    store = make_store(tmp_path)
    runtime = MultiAgentRuntime(store)
    assert runtime.provider_runtime is None
    assert runtime.registry.get("career-analyst").metadata == {}
    assert runtime.registry.get("career-analyst").capabilities

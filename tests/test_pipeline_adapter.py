from types import SimpleNamespace

import pytest

from career_os.control_plane import ApprovalStatus, ControlPlaneStore, TaskStatus
from career_os.models import Job, PipelineResult
from career_os.pipeline_adapter import ControlledCareerPipeline


class FakePipeline:
    def __init__(self, result):
        self.runtime = SimpleNamespace(last_provider_used="deterministic")
        self.result = result

    async def process(self, profile, job, **kwargs):
        return self.result


@pytest.mark.asyncio
async def test_controlled_pipeline_records_success_and_usage(tmp_path):
    job = Job(title="Support Engineer", company="Example", description="Work with customers")
    result = PipelineResult(job=job, application_mode="REVIEW_REQUIRED", review_status="READY_FOR_REVIEW")
    store = ControlPlaneStore(tmp_path / "state.json")

    controlled = ControlledCareerPipeline(FakePipeline(result), store)
    returned = await controlled.process("profile", job)

    assert returned is result
    tasks = store.tasks()
    assert len(tasks) == 1
    assert tasks[0].status == TaskStatus.COMPLETED
    assert store.usage_events()[0].operation == "career_os_pipeline"
    assert {event.event_type for event in store.audit_events()} >= {"OBJECTIVE_SUBMITTED", "TASK_DELEGATED", "TASK_RESULT_RECORDED"}


@pytest.mark.asyncio
async def test_controlled_pipeline_never_executes_auto_apply_without_approval(tmp_path):
    job = Job(title="Support Engineer", company="Example", description="Work with customers")
    result = PipelineResult(job=job, application_mode="AUTO_APPLY", review_status="READY_FOR_REVIEW")
    store = ControlPlaneStore(tmp_path / "state.json")

    await ControlledCareerPipeline(FakePipeline(result), store).process("profile", job)

    assert len(store.approvals(pending_only=True)) == 1
    assert store.tasks()[0].status == TaskStatus.AWAITING_APPROVAL
    assert store.approvals()[0].status == ApprovalStatus.PENDING


def test_supplied_career_os_pipeline_uses_consolidated_harness(tmp_path):
    from career_os.agents import AgentRuntime
    from career_os.orchestrator import CareerOS

    runtime = object.__new__(AgentRuntime)
    pipeline = CareerOS(runtime=runtime, write_to_notion=False)
    controlled = ControlledCareerPipeline(pipeline, ControlPlaneStore(tmp_path / "state.json"))

    assert pipeline.harness_runtime is controlled.harness
    assert controlled.harness.provider_runtime is runtime

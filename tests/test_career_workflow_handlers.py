import asyncio

from career_os.career_workflow_handlers import register_career_workflow_handlers
from career_os.workflow_engine import WorkflowEngine, WorkflowNode


class FakeRuntime:
    async def execute_real_agent_async(self, **kwargs):
        return {"agent_id": kwargs["agent_id"], "job": kwargs["context"].get("job")}


def test_registers_career_workflow_handlers(tmp_path):
    engine = WorkflowEngine(state_dir=tmp_path)
    register_career_workflow_handlers(engine, runtime=FakeRuntime())
    expected = {
        "job_discovery", "deduplicate", "jd_enrichment", "career_fit",
        "resume_builder", "truth_guard", "ats_review", "independent_review",
        "application_approval", "browser_application",
    }
    assert expected.issubset(engine.handlers)


def test_discovery_and_deduplication_are_deterministic(tmp_path):
    engine = WorkflowEngine(state_dir=tmp_path)
    register_career_workflow_handlers(engine, runtime=FakeRuntime())
    discovery = asyncio.run(engine.handlers["job_discovery"](
        node=WorkflowNode("job_discovery", "job_discovery"),
        inputs={}, context={"jobs": [{"url": "a"}, {"url": "a"}, {"url": "b"}]}, run=None,
    ))
    dedup = engine.handlers["deduplicate"](
        node=WorkflowNode("deduplicate", "deduplicate"),
        inputs={"job_discovery": discovery}, context={}, run=None,
    )
    assert len(dedup["jobs"]) == 2


def test_career_fit_fans_out_over_all_jobs(tmp_path):
    engine = WorkflowEngine(state_dir=tmp_path)
    register_career_workflow_handlers(engine, runtime=FakeRuntime())
    result = asyncio.run(engine.handlers["career_fit"](
        node=WorkflowNode("career_fit", "career_fit", agent_id="career-fit"),
        inputs={"jd_enrichment": {"jobs": [{"title": "A"}, {"title": "B"}]}},
        context={"profile": {"name": "test"}, "parent_task_id": "run-1"}, run=None,
    ))
    assert result["count"] == 2
    assert [item["job"]["title"] for item in result["items"]] == ["A", "B"]
    assert all(item["status"] == "COMPLETED" for item in result["items"])


def test_browser_handler_is_fail_closed(tmp_path):
    engine = WorkflowEngine(state_dir=tmp_path)
    register_career_workflow_handlers(engine, runtime=FakeRuntime())
    result = engine.handlers["browser_application"](
        node=WorkflowNode("browser_application", "browser_application"),
        inputs={}, context={}, run=None,
    )
    assert result["status"] == "READY_FOR_APPROVED_BROWSER_EXECUTION"

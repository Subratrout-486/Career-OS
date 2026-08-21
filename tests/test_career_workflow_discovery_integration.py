import asyncio

from career_os.career_workflow_handlers import register_career_workflow_handlers
from career_os.job_sources import JobCandidate
from career_os.workflow_engine import WorkflowEngine, WorkflowNode


class FakeRuntime:
    async def execute_real_agent_async(self, **kwargs):
        return {"agent_id": kwargs["agent_id"]}


class FakeRegistry:
    async def discover_new(self):
        return {"company-a": [JobCandidate(title="Analyst", company="A", url="https://a.example/jobs/1")]}


def test_discovery_node_consumes_registry(monkeypatch, tmp_path):
    import career_os.career_workflow_handlers as handlers
    monkeypatch.setattr(handlers, "_load_source_registry", lambda context: FakeRegistry())
    engine = WorkflowEngine(state_dir=tmp_path)
    register_career_workflow_handlers(engine, runtime=FakeRuntime())
    result = asyncio.run(engine.handlers["job_discovery"](
        node=WorkflowNode("discover", "job_discovery"), inputs={}, context={}, run=None
    ))
    assert result["new_job_count"] == 1
    assert result["jobs"][0]["url"] == "https://a.example/jobs/1"
    assert result["jobs"][0]["source_id"] == "company-a"

from __future__ import annotations

from pathlib import Path

from career_os.control_plane import ControlPlaneStore, TaskStatus
from career_os.models import FitReport
from career_os.runtime import CareerOSAgentRuntime


class FakeConductor:
    def __init__(self, failures: int = 0):
        self.failures = failures
        self.calls = 0
        self.last_provider_used = "fake:test"

    async def fit(self, profile, job, evidence_pack=None, jd_analysis=None):
        self.calls += 1
        if self.calls <= self.failures:
            raise RuntimeError("temporary provider failure")
        return FitReport(
            fit_score=80,
            recommendation="APPLY",
            band="B",
            rationale="test",
        )


def make_store(tmp_path: Path) -> ControlPlaneStore:
    return ControlPlaneStore(tmp_path / "control-plane.json")


def test_real_agent_runtime_persists_child_lifecycle(tmp_path: Path):
    cp = make_store(tmp_path)
    runtime = CareerOSAgentRuntime(cp, FakeConductor())
    root = runtime.create_root_task("process one job", payload={"job_id": "job-1"})

    import asyncio
    result = asyncio.run(runtime.execute_real_agent_async(
        parent_task_id=root.id,
        agent_id="career-analyst",
        objective="Analyze fit",
        context={"profile": "profile", "job": {"title": "Test"}, "evidence_pack": [], "jd_analysis": {}},
    ))

    assert result.fit_score == 80
    children = [task for task in cp.tasks() if task.parent_task_id == root.id]
    assert len(children) == 1
    assert children[0].status == TaskStatus.COMPLETED
    assert cp.audit_events(children[0].id)


def test_real_agent_runtime_retries_without_provider_fallback(tmp_path: Path):
    cp = make_store(tmp_path)
    conductor = FakeConductor(failures=1)
    runtime = CareerOSAgentRuntime(cp, conductor)
    root = runtime.create_root_task("process one job")

    import asyncio
    result = asyncio.run(runtime.execute_real_agent_async(
        parent_task_id=root.id,
        agent_id="career-analyst",
        objective="Analyze fit",
        context={"profile": "profile", "job": {"title": "Test"}, "evidence_pack": [], "jd_analysis": {}},
    ))

    assert result.fit_score == 80
    assert conductor.calls == 2
    child = [task for task in cp.tasks() if task.parent_task_id == root.id][0]
    assert child.status == TaskStatus.COMPLETED
    assert child.retry_count == 1

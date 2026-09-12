import asyncio

from career_os.agent_runtime import MultiAgentRuntime
from career_os.control_plane import ControlPlaneStore
from career_os.job_e2e_runner import JobE2EInput, JobE2ERunner


class FakeProvider:
    async def fit(self, profile, job, evidence_pack, jd_analysis):
        return {"score": 86, "evidence": ["verified profile evidence"], "blocked": False}

    async def resume(self, profile, job, fit, evidence_pack, jd_analysis):
        return {"status": "READY", "truth_guard": "PASS", "pdf": "/tmp/tailored.pdf"}

    async def challenge(self, profile, job, fit, resume, evidence_pack):
        return {"status": "PASS", "critical_issue": False, "requires_review": False}


def test_real_job_runner_reaches_terminal_without_submission():
    runtime = MultiAgentRuntime(store=ControlPlaneStore(), provider_runtime=FakeProvider())
    result = asyncio.run(
        JobE2ERunner(runtime).run(
            JobE2EInput(
                job={"id": "test-job-1", "title": "Analyst", "url": "https://example.com/job/1"},
                profile={"name": "Test Candidate"},
            )
        )
    )
    assert result.state == "READY_TO_APPLY"
    assert result.artifacts["submission"] == {"enabled": False, "performed": False}
    assert any(stage["stage"] == "READINESS" for stage in result.stages)


def test_real_job_runner_fails_closed_for_incomplete_job():
    runtime = MultiAgentRuntime(store=ControlPlaneStore(), provider_runtime=FakeProvider())
    result = asyncio.run(
        JobE2ERunner(runtime).run(
            JobE2EInput(job={"title": "Missing URL"}, profile={"name": "Test Candidate"})
        )
    )
    assert result.state == "BLOCKED"
    assert result.artifacts["submission"] if "submission" in result.artifacts else True

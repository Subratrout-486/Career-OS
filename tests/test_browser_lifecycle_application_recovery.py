import hashlib
import json

from career_os.browser_execution_state import BrowserExecutionStateStore
from career_os.browser_lifecycle import run_automatic_lifecycle


def test_lifecycle_recovers_missing_application_record_before_preflight(tmp_path, monkeypatch):
    workspace = tmp_path / "browser_lifecycle"
    results_dir = workspace / "pipeline_results"
    resumes_dir = workspace / "generated_resumes"
    results_dir.mkdir(parents=True)
    resumes_dir.mkdir(parents=True)
    resume = resumes_dir / "ghx-support-tailored.pdf"
    resume.write_bytes(b"exact tailored resume")
    job_url = "https://job-boards.greenhouse.io/example/jobs/123"

    candidate = {
        "job": {"company": "GHX", "title": "Customer Support Analyst I", "url": job_url},
        "job_verification": {"status": "ACTIVE", "active": True, "application_url": job_url},
        "resume": {"experience": []},
        "resume_files": {"pdf": str(resume)},
    }
    path = results_dir / "ghx-result.json"
    path.write_text(json.dumps(candidate), encoding="utf-8")

    calls = {"create_record": 0, "start": 0}

    class FakeApplicationsTracker:
        def __init__(self):
            pass

        async def create_review_record(self, result):
            calls["create_record"] += 1
            assert result["job"]["url"] == job_url
            return "application-ghx-123"

    monkeypatch.setattr("career_os.browser_lifecycle.ApplicationsTracker", FakeApplicationsTracker)

    def preflight_start(result, *, approved_questions, state):
        calls["start"] += 1
        assert result["application_page_id"] == "application-ghx-123"
        digest = hashlib.sha256(resume.read_bytes()).hexdigest()
        record = {
            "application_id": result["application_page_id"],
            "job_url": job_url,
            "resume_sha256": digest,
        }
        state.reserve(record, stage="preflight")
        state.record_task(record, stage="preflight", task_id="preflight-ghx")
        return {"status": "TASK_CREATED"}

    def preflight_poll(result, *, approved_questions, state, manifest_output):
        assert result["application_page_id"] == "application-ghx-123"
        return {"status": "PENDING"}

    async def reconcile(state):
        return []

    summary = run_automatic_lifecycle(
        workspace,
        preflight_start=preflight_start,
        preflight_poll=preflight_poll,
        dispatch_records=lambda records, *, state: [],
        reconcile_state=reconcile,
    )

    assert calls == {"create_record": 1, "start": 1}
    assert summary["candidates"][0]["application_record_recovered"] is True
    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert persisted["application_page_id"] == "application-ghx-123"
    assert summary["continuation_required"] is True


def test_lifecycle_does_not_guess_application_record_without_exact_job_url(tmp_path, monkeypatch):
    workspace = tmp_path / "browser_lifecycle"
    results_dir = workspace / "pipeline_results"
    resumes_dir = workspace / "generated_resumes"
    results_dir.mkdir(parents=True)
    resumes_dir.mkdir(parents=True)
    resume = resumes_dir / "tailored.pdf"
    resume.write_bytes(b"resume")
    (results_dir / "candidate.json").write_text(
        json.dumps({
            "job": {"company": "Example", "title": "Support", "url": ""},
            "resume_files": {"pdf": str(resume)},
        }),
        encoding="utf-8",
    )

    class ShouldNotCreate:
        def __init__(self):
            pass

        async def create_review_record(self, result):
            raise AssertionError("must not create an ambiguous application record")

    monkeypatch.setattr("career_os.browser_lifecycle.ApplicationsTracker", ShouldNotCreate)

    summary = run_automatic_lifecycle(
        workspace,
        preflight_start=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("preflight must not run")),
        preflight_poll=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("preflight must not run")),
        dispatch_records=lambda records, *, state: [],
        reconcile_state=lambda state: __import__("asyncio").sleep(0, result=[]),
    )

    assert summary["candidates"][0]["status"] == "BLOCKED"
    assert "no exact job URL" in summary["candidates"][0]["reason"]

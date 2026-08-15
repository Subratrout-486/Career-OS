import asyncio
import hashlib
import json
from pathlib import Path

from career_os.browser_execution_state import BrowserExecutionStateStore
from career_os.browser_lifecycle import run_automatic_lifecycle


def _resume_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_automatic_lifecycle_chains_persisted_candidate_without_manual_staging(tmp_path):
    workspace = tmp_path / "browser_lifecycle"
    results_dir = workspace / "pipeline_results"
    resumes_dir = workspace / "generated_resumes"
    results_dir.mkdir(parents=True)
    resumes_dir.mkdir(parents=True)
    resume = resumes_dir / "tcs-support-engineer-tailored.pdf"
    resume.write_bytes(b"exact tcs tailored resume")
    expected_hash = _resume_hash(resume)
    # Simulates a result produced on an earlier ephemeral Actions runner. The
    # lifecycle may restore only the artifact with the same declared filename.
    candidate = {
        "application_page_id": "application-tcs-1",
        "job": {
            "company": "TCS",
            "title": "Support Engineer",
            "url": "https://www.linkedin.com/jobs/view/tcs-1",
        },
        "job_verification": {"application_url": "https://www.linkedin.com/jobs/view/tcs-1"},
        "resume_files": {"pdf": "/ephemeral/runner/generated_resumes/tcs-support-engineer-tailored.pdf"},
    }
    (results_dir / "tcs-result.json").write_text(json.dumps(candidate), encoding="utf-8")
    calls = {"start": 0, "poll": 0, "dispatch": 0, "reconcile": 0}

    def handoff_record(result):
        return {
            "application_id": result["application_page_id"],
            "job_url": result["job_verification"]["application_url"],
            "resume_sha256": _resume_hash(Path(result["resume_files"]["pdf"])),
        }

    def preflight_start(result, *, approved_questions, state):
        calls["start"] += 1
        assert Path(result["resume_files"]["pdf"]).resolve() == resume.resolve()
        record = handoff_record(result)
        reserved, _ = state.reserve(record, stage="preflight")
        assert reserved is True
        state.record_task(record, stage="preflight", task_id="preflight-tcs", task_url="https://manus/preflight-tcs")
        return {"status": "TASK_CREATED", "task_id": "preflight-tcs"}

    def preflight_poll(result, *, approved_questions, state, manifest_output):
        calls["poll"] += 1
        record = handoff_record(result)
        state.record_snapshot(
            record["application_id"],
            stage="preflight",
            snapshot={"agent_status": "STOPPED"},
            outcome={"status": "AUTO_APPLY_READY"},
        )
        manifest_output.write_text(json.dumps({"applications": [record]}), encoding="utf-8")
        return {"status": "AUTO_APPLY_READY"}

    def dispatch(records, *, state):
        calls["dispatch"] += 1
        assert len(records) == 1
        record = records[0]
        assert record["resume_sha256"] == expected_hash
        reserved, _ = state.reserve(record, stage="execution")
        assert reserved is True
        state.record_task(record, stage="execution", task_id="execution-tcs", task_url="https://manus/execution-tcs")
        return [{"status": "TASK_CREATED", "application_id": record["application_id"]}]

    async def reconcile(state):
        calls["reconcile"] += 1
        record = handoff_record({**candidate, "resume_files": {"pdf": str(resume)}})
        execution = state.load()["applications"][record["application_id"]]["execution"]
        if execution["status"] in {"SUBMITTED_CONFIRMED", "RECONCILED_REVIEW"}:
            return [{"status": "TERMINAL_SKIPPED"}]
        state.record_snapshot(
            record["application_id"],
            stage="execution",
            snapshot={"agent_status": "STOPPED"},
            outcome={"status": "REVIEW_REQUIRED"},
        )
        return [{"status": "RECORDED"}]

    first = run_automatic_lifecycle(
        workspace,
        preflight_start=preflight_start,
        preflight_poll=preflight_poll,
        dispatch_records=dispatch,
        reconcile_state=reconcile,
    )

    assert first["dispatch"] == [{"status": "TASK_CREATED", "application_id": "application-tcs-1"}]
    assert first["reconciliation"] == [{"status": "RECORDED"}]
    assert first["continuation_required"] is False
    assert (workspace / "browser_execution_manifests" / "application-tcs-1.json").is_file()
    assert (workspace / "browser_execution_state.json").is_file()
    assert (workspace / "browser_lifecycle_summary.json").is_file()
    assert calls == {"start": 1, "poll": 1, "dispatch": 1, "reconcile": 1}

    # The next scheduled invocation restores the same workspace. It must not
    # stage files manually or recreate any Manus task after terminal review.
    second = run_automatic_lifecycle(
        workspace,
        preflight_start=preflight_start,
        preflight_poll=preflight_poll,
        dispatch_records=dispatch,
        reconcile_state=reconcile,
    )

    assert second["dispatch"] == []
    assert second["continuation_required"] is False
    assert second["candidates"][0]["status"] == "EXECUTION_ALREADY_PERSISTED"
    assert second["candidates"][0]["execution_state"] == "RECONCILED_REVIEW"
    assert calls == {"start": 1, "poll": 1, "dispatch": 1, "reconcile": 2}


def test_lifecycle_continues_only_when_a_persisted_task_is_unfinished(tmp_path):
    workspace = tmp_path / "browser_lifecycle"
    (workspace / "pipeline_results").mkdir(parents=True)
    (workspace / "generated_resumes").mkdir(parents=True)
    resume = workspace / "generated_resumes" / "tailored.pdf"
    resume.write_bytes(b"resume")
    digest = _resume_hash(resume)
    (workspace / "pipeline_results" / "candidate.json").write_text(
        json.dumps({
            "application_page_id": "app-waiting",
            "job": {"company": "TCS", "title": "Support", "url": "https://jobs.example/tcs"},
            "job_verification": {"application_url": "https://jobs.example/tcs"},
            "resume_files": {"pdf": str(resume)},
        }),
        encoding="utf-8",
    )
    state = BrowserExecutionStateStore(workspace / "browser_execution_state.json")
    record = {"application_id": "app-waiting", "job_url": "https://jobs.example/tcs", "resume_sha256": digest}
    state.reserve(record, stage="execution")
    state.record_task(record, stage="execution", task_id="waiting-task")

    async def reconcile_waiting(current_state):
        assert current_state.load()["applications"]["app-waiting"]["execution"]["status"] == "TASK_CREATED"
        return [{"status": "PENDING"}]

    summary = run_automatic_lifecycle(
        workspace,
        preflight_start=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("preflight must not restart")),
        preflight_poll=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("preflight must not repoll")),
        dispatch_records=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("dispatch must not duplicate")),
        reconcile_state=reconcile_waiting,
    )

    assert summary["continuation_required"] is True
    assert summary["candidates"][0]["execution_state"] == "TASK_CREATED"


def test_stale_task_block_preserves_identity_and_prevents_automatic_recreation(tmp_path):
    state = BrowserExecutionStateStore(tmp_path / "browser_execution_state.json")
    record = {
        "application_id": "app-stale",
        "job_url": "https://jobs.example/stale",
        "resume_sha256": "b" * 64,
    }
    reserved, _ = state.reserve(record, stage="execution")
    assert reserved is True
    state.record_task(record, stage="execution", task_id="dead-task", task_url="https://manus/dead-task")

    state.mark_stale_task(
        record["application_id"],
        stage="execution",
        task_id="dead-task",
        reason="Manus returned HTTP 404; no execution result exists.",
    )

    stored = state.load()["applications"][record["application_id"]]
    assert stored["fingerprint"] == "app-stale|https://jobs.example/stale|" + ("b" * 64)
    assert stored["execution"]["task_id"] == "dead-task"
    assert stored["execution"]["task_url"] == "https://manus/dead-task"
    assert stored["execution"]["status"] == "BLOCKED"
    assert stored["execution"]["stale_task"] is True

    retry_reserved, existing = state.reserve(record, stage="execution")
    assert retry_reserved is False
    assert existing["execution"]["task_id"] == "dead-task"


def test_stale_preflight_task_is_blocked_without_creating_manifest(tmp_path, monkeypatch):
    from scripts import run_manus_browser_preflight as preflight
    from career_os.manus_browser_runner import ManusTaskNotFoundError

    monkeypatch.setenv("MANUS_API_KEY", "test-key")
    resume = tmp_path / "tailored.pdf"
    resume.write_bytes(b"exact resume")
    candidate = {
        "application_page_id": "app-stale-preflight",
        "job": {"company": "Example", "title": "Support", "url": "https://jobs.example/support"},
        "job_verification": {"application_url": "https://jobs.example/support"},
        "resume_files": {"pdf": str(resume)},
    }
    state = BrowserExecutionStateStore(tmp_path / "state.json")
    request = {
        "application": {
            "company": "Example",
            "title": "Support",
            "job_url": "https://jobs.example/support",
            "application_id": "app-stale-preflight",
        },
        "resume_path": str(resume),
        "resume_filename": resume.name,
        "resume_sha256": hashlib.sha256(resume.read_bytes()).hexdigest(),
        "approved_questions": [],
    }
    monkeypatch.setattr(preflight, "build_preflight_request", lambda *_args, **_kwargs: request)
    record = preflight._state_record(request)
    state.reserve(record, stage="preflight")
    state.record_task(record, stage="preflight", task_id="dead-preflight")

    class DeadRunner:
        def __init__(self):
            pass

        def inspect_task(self, task_id):
            raise ManusTaskNotFoundError("Manus API HTTP 404: task not found")

    monkeypatch.setattr(preflight, "ManusBrowserRunner", DeadRunner)
    result = preflight.poll(candidate, approved_questions=[], state=state, manifest_output=tmp_path / "manifest.json")

    assert result["status"] == "STALE_TASK_BLOCKED"
    assert not (tmp_path / "manifest.json").exists()
    stored = state.load()["applications"]["app-stale-preflight"]["preflight"]
    assert stored["status"] == "BLOCKED"
    assert stored["stale_task"] is True

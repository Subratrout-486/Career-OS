import os

import pytest

from career_os.manus_browser_runner import ManusApiError, ManusBrowserRunner


def test_runner_requires_api_key(monkeypatch):
    monkeypatch.delenv("MANUS_API_KEY", raising=False)
    with pytest.raises(ManusApiError, match="MANUS_API_KEY"):
        ManusBrowserRunner()


def test_execution_task_attaches_exact_uploaded_resume_and_has_hard_stops(monkeypatch, tmp_path):
    monkeypatch.setenv("MANUS_API_KEY", "test-key")
    runner = ManusBrowserRunner()
    monkeypatch.setattr(runner, "upload_resume", lambda _: {"id": "file_verified_resume"})
    captured = {}

    def fake_request(method, path, payload=None):
        captured.update({"method": method, "path": path, "payload": payload})
        return {"ok": True, "task_id": "task_123", "task_url": "https://manus.example/task_123"}

    monkeypatch.setattr(runner, "_json_request", fake_request)
    resume_path = tmp_path / "candidate.pdf"
    resume_path.write_bytes(b"not inspected because upload is mocked")
    created = runner.create_execution_task(
        {
            "company": "Example Co",
            "title": "Production Support Engineer",
            "job_url": "https://jobs.example/apply/123",
            "application_id": "notion-page-123",
        },
        resume_path,
    )

    assert created["task_id"] == "task_123"
    assert captured["method"] == "POST"
    assert captured["path"] == "/task.create"
    parts = captured["payload"]["message"]["content"]
    assert parts[1] == {"type": "file", "file_id": "file_verified_resume", "filename": "candidate.pdf"}
    prompt = parts[0]["text"]
    assert "CAPTCHA, OTP/MFA" in prompt
    assert "Never invent or guess" in prompt
    assert captured["payload"]["structured_output_schema"]["additionalProperties"] is False


def test_execution_task_rejects_missing_verified_job_identity(monkeypatch, tmp_path):
    monkeypatch.setenv("MANUS_API_KEY", "test-key")
    runner = ManusBrowserRunner()
    with pytest.raises(ManusApiError, match="job_url"):
        runner.create_execution_task({"company": "Example", "title": "Support"}, tmp_path / "resume.pdf")


def test_preflight_task_requires_non_submitting_exact_upload_and_hash_contract(monkeypatch, tmp_path):
    monkeypatch.setenv("MANUS_API_KEY", "test-key")
    runner = ManusBrowserRunner()
    monkeypatch.setattr(runner, "upload_resume", lambda _: {"id": "file_tailored_resume"})
    captured = {}

    def fake_request(method, path, payload=None):
        captured.update({"method": method, "path": path, "payload": payload})
        return {"ok": True, "task_id": "preflight_123", "task_url": "https://manus.example/preflight_123"}

    monkeypatch.setattr(runner, "_json_request", fake_request)
    resume_path = tmp_path / "tcs-tailored.pdf"
    resume_path.write_bytes(b"exact tailored artifact")
    resume_hash = "a" * 64
    created = runner.create_preflight_task(
        {
            "company": "TCS",
            "title": "Support Engineer",
            "job_url": "https://www.linkedin.com/jobs/view/123",
            "application_id": "notion-tcs-123",
        },
        resume_path,
        resume_sha256=resume_hash,
        approved_questions=[
            {
                "question": "How many years of engineering experience do you have?",
                "answer": "0",
                "status": "APPROVED",
                "required": True,
            }
        ],
    )

    assert created["task_id"] == "preflight_123"
    prompt = captured["payload"]["message"]["content"][0]["text"]
    schema = captured["payload"]["structured_output_schema"]
    assert "compute the SHA-256 of the attached JD-tailored resume" in prompt
    assert "selected_resume_sha256" in prompt
    assert "do not claim that the employer form itself displayed a hash" in prompt
    assert "Never submit the form during preflight" in prompt
    assert "does not need to upload" not in prompt
    assert resume_hash in prompt
    for key in (
        "normal_upload_attempted",
        "normal_upload_succeeded",
        "file_chooser_retry_attempted",
        "file_chooser_retry_succeeded",
        "input_retry_attempted",
        "input_retry_succeeded",
        "selected_resume_filename",
        "selected_resume_sha256",
        "resume_attachment_visible",
    ):
        assert key in schema["required"]
    assert captured["payload"]["message"]["content"][1] == {
        "type": "file", "file_id": "file_tailored_resume", "filename": "tcs-tailored.pdf"
    }


def test_selects_exactly_one_authorized_browser_without_exposing_client_metadata(monkeypatch):
    monkeypatch.setenv("MANUS_API_KEY", "test-key")
    runner = ManusBrowserRunner()
    captured = {}

    monkeypatch.setattr(runner, "online_browsers", lambda: [{"client_id": "runtime-browser-client", "label": "User browser"}])

    def fake_request(method, path, payload=None):
        captured.update({"method": method, "path": path, "payload": payload})
        return {"ok": True}

    monkeypatch.setattr(runner, "_json_request", fake_request)
    snapshot = {
        "task_id": "task-123",
        "agent_status": "WAITING",
        "browser_connection_required": True,
        "_browser_connect_event_id": "event-runtime-only",
        "_browser_connect_schema": {"properties": {"action": {}, "client_id": {}}},
        "waiting": {
            "waiting_for_event_type": "needConnectMyBrowser",
            "waiting_for_event_id": "event-runtime-only",
            "confirm_input_schema": {"properties": {"action": {}, "client_id": {}}},
        },
        "errors": ["diagnostic must not persist"],
    }

    assert runner.confirm_authorized_browser("task-123", snapshot) == {"status": "AUTHORIZED_BROWSER_SELECTED"}
    assert captured == {
        "method": "POST",
        "path": "/task.confirmAction",
        "payload": {
            "task_id": "task-123",
            "event_id": "event-runtime-only",
            "input": {"action": "select", "client_id": "runtime-browser-client"},
        },
    }
    public = runner.public_browser_snapshot(snapshot)
    assert "runtime-browser-client" not in repr(public)
    assert "event-runtime-only" not in repr(public)
    assert "diagnostic must not persist" not in repr(public)
    assert public["error_count"] == 1


def test_browser_selection_fails_closed_for_zero_or_multiple_clients(monkeypatch):
    monkeypatch.setenv("MANUS_API_KEY", "test-key")
    runner = ManusBrowserRunner()
    snapshot = {
        "browser_connection_required": True,
        "_browser_connect_event_id": "event",
        "_browser_connect_schema": {"properties": {"action": {}, "client_id": {}}},
    }
    monkeypatch.setattr(runner, "online_browsers", lambda: [])
    assert runner.confirm_authorized_browser("task", snapshot) == {
        "status": "REVIEW_REQUIRED", "blocker": "BROWSER_CONNECTION_REQUIRED"
    }
    monkeypatch.setattr(runner, "online_browsers", lambda: [{"client_id": "one"}, {"client_id": "two"}])
    assert runner.confirm_authorized_browser("task", snapshot) == {
        "status": "REVIEW_REQUIRED", "blocker": "BROWSER_SELECTION_REQUIRED"
    }


def test_public_browser_snapshot_drops_authentication_shaped_runtime_values(monkeypatch):
    monkeypatch.setenv("MANUS_API_KEY", "test-key")
    public = ManusBrowserRunner.public_browser_snapshot({
        "task_id": "task-123",
        "browser_connection_required": True,
        "_browser_connect_event_id": "event-hidden",
        "_browser_connect_schema": {"properties": {"client_id": {}}},
        "waiting": {
            "waiting_for_event_type": "needConnectMyBrowser",
            "waiting_for_event_id": "event-hidden",
            "confirm_input_schema": {"properties": {"client_id": {}}},
        },
        "errors": ["Authorization: bearer must not be written"],
    })
    assert "event-hidden" not in repr(public)
    assert "Authorization" not in repr(public)
    assert "client_id" not in repr(public)
    assert public["waiting"] == {"waiting_for_event_type": "needConnectMyBrowser", "waiting_description": ""}

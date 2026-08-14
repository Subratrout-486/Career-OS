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

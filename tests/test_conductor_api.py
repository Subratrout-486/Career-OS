from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from career_os.api_boundary import IdempotencyStore, create_conductor_router


class FakePipeline:
    async def process(self, profile, job, **kwargs):
        return SimpleNamespace(
            model_dump=lambda mode="json": {
                "review_status": "REVIEW_ONLY",
                "application_mode": "REVIEW_ONLY",
                "errors": [],
                "resume_files": [],
            }
        )


def make_app(monkeypatch, idempotency_path=None):
    monkeypatch.setenv("CAREER_OS_CONDUCTOR_TOKEN", "test-secret")
    app = FastAPI()
    store = IdempotencyStore(str(idempotency_path)) if idempotency_path else None
    app.include_router(create_conductor_router(pipeline=FakePipeline(), idempotency=store))
    return TestClient(app)


def test_conductor_health_requires_service_token(monkeypatch):
    client = make_app(monkeypatch)
    assert client.get("/api/conductor/v1/health").status_code == 401
    response = client.get("/api/conductor/v1/health", headers={"X-Conductor-Token": "test-secret"})
    assert response.status_code == 200
    assert response.json()["submission"] == "disabled"
    assert response.json()["engine"] == "existing-career-os-process"


def test_boundary_rejects_submission_controls(monkeypatch):
    client = make_app(monkeypatch)
    response = client.post(
        "/api/conductor/v1/pipeline/run",
        headers={"X-Conductor-Token": "test-secret"},
        json={
            "profile": "candidate profile",
            "job": {"title": "Support", "company": "Acme", "description": "Support role"},
            "idempotency_key": "idem-123456",
            "browser_context": {"auto_apply": True},
        },
    )
    assert response.status_code == 422
    assert "automatic application submission" in response.text


def test_idempotency_rejects_replay_without_persisting_payload_or_token(monkeypatch, tmp_path):
    path = tmp_path / "idempotency.json"
    client = make_app(monkeypatch, path)
    payload = {
        "profile": "private candidate profile",
        "job": {"title": "Support", "company": "Acme", "description": "Support role"},
        "idempotency_key": "idem-replay-123",
    }
    headers = {"X-Conductor-Token": "test-secret"}
    first = client.post("/api/conductor/v1/pipeline/run", headers=headers, json=payload)
    second = client.post("/api/conductor/v1/pipeline/run", headers=headers, json=payload)
    assert first.status_code == 200
    assert second.status_code == 409
    stored = path.read_text(encoding="utf-8")
    assert "private candidate profile" not in stored
    assert "test-secret" not in stored
    assert json.loads(stored)["idem-replay-123"]["trace_id"] == first.json()["trace_id"]

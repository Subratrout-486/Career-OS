from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from career_os.applications import (
    APPLICATION_STATUS_REVIEW,
    APPLICATION_STATUS_SUBMITTED,
    ApplicationsTracker,
)


class _Response:
    def __init__(self, *, status: str | None = None):
        self.status_code = 200
        self.text = ""
        self.is_error = False
        self._status = status

    def json(self):
        return {
            "properties": {
                "Application Status": {"select": {"name": self._status}}
            }
        }


class _Client:
    def __init__(self, existing_status: str):
        self.existing_status = existing_status
        self.patch_payloads: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def get(self, *_args, **_kwargs):
        return _Response(status=self.existing_status)

    async def patch(self, *_args, **kwargs):
        self.patch_payloads.append(kwargs["json"])
        return _Response()


def _result() -> dict:
    return {
        "application_mode": "REVIEW_REQUIRED",
        "job": {"company": "HighRadius", "title": "Product Support Engineer"},
        "resume_files": {},
        "application_mode_blockers": ["Truth Guard remains blocked"],
    }


@pytest.mark.asyncio
async def test_automatic_reevaluation_reuses_existing_review_record(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "test-token")
    tracker = ApplicationsTracker()
    client = _Client(APPLICATION_STATUS_REVIEW)

    with patch("career_os.applications.httpx.AsyncClient", return_value=client):
        status = await tracker.update_review_record("3bc8bc1d-ce0e-81db-aebd-ef3f9c65f943", _result())

    assert status == APPLICATION_STATUS_REVIEW
    assert len(client.patch_payloads) == 1
    properties = client.patch_payloads[0]["properties"]
    assert properties["Application Status"]["select"]["name"] == APPLICATION_STATUS_REVIEW
    assert "Truth Guard remains blocked" in properties["Notes"]["rich_text"][0]["text"]["content"]


@pytest.mark.asyncio
async def test_automatic_reevaluation_refuses_existing_applied_record(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "test-token")
    tracker = ApplicationsTracker()
    client = _Client(APPLICATION_STATUS_SUBMITTED)

    with patch("career_os.applications.httpx.AsyncClient", return_value=client):
        with pytest.raises(RuntimeError, match="already Applied"):
            await tracker.update_review_record("3bc8bc1d-ce0e-81db-aebd-ef3f9c65f943", _result())

    assert client.patch_payloads == []


def test_trusted_intake_workflow_requires_verified_marker_before_stage_two():
    workflow = Path(".github/workflows/career-os-job-intake.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "STAGE_2_GATED" in workflow
    assert "CAREER_OS_JOB_V1" in workflow
    assert "contains(github.event.issue.body, '<!-- CAREER_OS_JOB_V1 -->')" in workflow
    assert "dispatch_manus_browser_tasks.py" not in workflow

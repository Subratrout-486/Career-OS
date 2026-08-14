"""Manus task handoff for verified Career OS browser execution.

This adapter intentionally creates a separately auditable Manus task rather than
attempting unmanaged browser automation from a GitHub runner.  The task receives
the exact candidate-facing resume file and a constrained execution brief.  Any
browser attachment, CAPTCHA, identity challenge, question requiring judgement,
or submission confirmation remains an explicit task event; the runner never
silently answers or confirms it.
"""
from __future__ import annotations

import json
import mimetypes
import os
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_BASE = "https://api.manus.ai/v2"


class ManusApiError(RuntimeError):
    """Raised when the Manus API returns a non-success envelope or HTTP error."""


class ManusBrowserRunner:
    """Create browser execution tasks after Career OS has passed every gate."""

    def __init__(self, api_key: str | None = None, *, timeout_seconds: int = 30) -> None:
        self.api_key = api_key or os.getenv("MANUS_API_KEY")
        self.timeout_seconds = timeout_seconds
        if not self.api_key:
            raise ManusApiError("MANUS_API_KEY is required to create a browser execution task.")

    @property
    def _headers(self) -> dict[str, str]:
        return {"x-manus-api-key": self.api_key or "", "Accept": "application/json"}

    def _json_request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {**self._headers}
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(f"{API_BASE}{path}", data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                parsed = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise ManusApiError(f"Manus API HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')}") from exc
        except URLError as exc:
            raise ManusApiError(f"Manus API network error: {exc.reason}") from exc
        if parsed.get("ok") is not True:
            error = parsed.get("error") or {}
            raise ManusApiError(f"Manus API error {error.get('code', 'unknown')}: {error.get('message', parsed)}")
        return parsed

    def upload_resume(self, resume_path: str | Path) -> dict[str, Any]:
        """Upload the exact prepared PDF/DOCX and verify its ready status."""
        path = Path(resume_path)
        if not path.is_file():
            raise ManusApiError(f"Resume file does not exist: {path}")
        created = self._json_request("POST", "/file.upload", {"filename": path.name})
        file_record = created.get("file") or {}
        file_id = str(file_record.get("id") or "")
        upload_url = str(created.get("upload_url") or "")
        if not file_id or not upload_url:
            raise ManusApiError("File upload response did not include file.id and upload_url.")

        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        upload = Request(upload_url, data=path.read_bytes(), headers={"Content-Type": mime_type}, method="PUT")
        try:
            with urlopen(upload, timeout=self.timeout_seconds) as response:
                if response.status not in {200, 201, 204}:
                    raise ManusApiError(f"Resume upload returned unexpected HTTP {response.status}.")
        except HTTPError as exc:
            raise ManusApiError(f"Resume upload failed with HTTP {exc.code}.") from exc
        except URLError as exc:
            raise ManusApiError(f"Resume upload network error: {exc.reason}") from exc

        for _ in range(6):
            detail = self._json_request("GET", f"/file.detail?{urlencode({'file_id': file_id})}")
            uploaded = detail.get("file") or {}
            if uploaded.get("status") == "uploaded":
                return uploaded
            time.sleep(1)
        raise ManusApiError("Uploaded resume did not reach status=uploaded before the handoff timeout.")

    @staticmethod
    def _execution_prompt(application: dict[str, Any]) -> str:
        return f"""You are the Career OS Browser Executor for one pre-gated application.

Application identity:
- Company: {application['company']}
- Role: {application['title']}
- Verified job URL: {application['job_url']}
- Application record ID: {application.get('application_id', 'not supplied')}

The attached file is the exact Career OS JD-specific resume. Do not replace it,
modify it, invent claims, or upload another resume.

Execution contract:
1. Open only the verified job URL and inspect the actual form before any action.
2. Request an authenticated user browser when required. If a browser is not
   available, report `BROWSER_UNAVAILABLE`; do not substitute an unmanaged one.
3. Use only verified profile data and the attached resume. Never invent or guess.
4. Stop and report `REVIEW_REQUIRED` for CAPTCHA, OTP/MFA, identity verification,
   assessment, work-authorisation/sponsorship uncertainty, salary/CTC decision,
   relocation or notice-period judgement, a required custom cover letter, unknown
   mandatory fields, suspicious redirects, or any question requiring human input.
5. A resume upload is not proof of submission. Submit only if every field is
   deterministic and approved. After any submission, verify the employer or ATS
   confirmation screen and report the exact evidence.
6. Do not contact recruiters, send connection requests, pay for services, or make
   changes beyond this single application.

Return the required structured outcome truthfully. """

    @staticmethod
    def _outcome_schema() -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["SUBMITTED", "REVIEW_REQUIRED", "BROWSER_UNAVAILABLE", "NOT_SUBMITTED", "ERROR"],
                },
                "submitted": {"type": "boolean"},
                "confirmation_evidence": {"type": "string"},
                "blockers": {"type": "array", "items": {"type": "string"}},
                "application_record_id": {"type": "string"},
            },
            "required": ["status", "submitted", "confirmation_evidence", "blockers", "application_record_id"],
            "additionalProperties": False,
        }

    def create_execution_task(self, application: dict[str, Any], resume_path: str | Path) -> dict[str, Any]:
        """Create a private structured-output task with the verified resume attached."""
        required = ("company", "title", "job_url")
        missing = [name for name in required if not str(application.get(name) or "").strip()]
        if missing:
            raise ManusApiError("Application handoff missing required fields: " + ", ".join(missing))
        uploaded = self.upload_resume(resume_path)
        file_id = str(uploaded.get("id"))
        filename = Path(resume_path).name
        payload = {
            "title": f"Career OS browser execution — {application['company']} — {application['title']}"[:250],
            "interactive_mode": False,
            "share_visibility": "private",
            "agent_profile": os.getenv("MANUS_BROWSER_AGENT_PROFILE", "manus-1.6"),
            "structured_output_schema": self._outcome_schema(),
            "message": {
                "content": [
                    {"type": "text", "text": self._execution_prompt(application)},
                    {"type": "file", "file_id": file_id, "filename": filename},
                ]
            },
        }
        return self._json_request("POST", "/task.create", payload)

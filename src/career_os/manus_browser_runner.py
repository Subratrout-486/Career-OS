"""Manus task handoff for verified Career OS browser execution.

The adapter creates auditable Manus tasks rather than running uncontrolled browser
automation from GitHub.  It supports two deliberate stages: a non-submitting
preflight that inspects the complete form and verifies the exact tailored-resume
upload, and a constrained execution task that is reconciled only after
independent employer/ATS/LinkedIn confirmation. Neither stage can invent profile
data, substitute a master resume, or silently clear a human-controlled blocker.
"""
from __future__ import annotations

import json
import mimetypes
import os
import time
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_BASE = "https://api.manus.ai/v2"


class ManusApiError(RuntimeError):
    """Raised when the Manus API returns a non-success envelope or HTTP error."""


class ManusBrowserRunner:
    """Create and reconcile preflight and execution tasks through Manus API v2."""

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
    def _require_application(application: Mapping[str, Any]) -> dict[str, str]:
        required = ("company", "title", "job_url", "application_id")
        prepared = {key: str(application.get(key) or "").strip() for key in required}
        missing = [name for name, value in prepared.items() if not value]
        if missing:
            raise ManusApiError("Application handoff missing required fields: " + ", ".join(missing))
        return prepared

    @staticmethod
    def _preflight_prompt(application: Mapping[str, str], *, resume_filename: str, resume_sha256: str, approved_questions: list[dict[str, Any]]) -> str:
        questions = json.dumps(approved_questions, ensure_ascii=False)
        return f"""You are the Career OS Browser Preflight Inspector. This is an inspection-only task.

Application identity:
- Company: {application['company']}
- Role: {application['title']}
- Verified job/application URL: {application['job_url']}
- Durable application record ID: {application['application_id']}
- Exact attached JD-tailored resume: {resume_filename}
- Exact SHA-256: {resume_sha256}
- Approved required answers (and no others): {questions}

Preflight contract:
1. Open only the verified URL and inspect every stage of the actual application form. Do not submit.
2. Request an authenticated user browser when required. If no browser is connected, return BROWSER_UNAVAILABLE. Do not invent browser facts.
3. Use only the attached JD-specific resume. Never substitute, search for, alter, or upload a master/generic resume.
4. Inspect all required questions. Verify an answer only when it exactly matches a supplied approved answer. Never reinterpret technical-support experience as engineering experience. In particular, if the form asks years of engineering experience and the approved answer is 0, report exactly 0.
5. Identify any CAPTCHA, OTP/MFA, identity check, assessment, suspicious redirect, sensitive/legal/personal question, compensation/CTC decision, sponsorship/work-authorisation uncertainty, unknown field, free-text request, cover letter, relocation, notice period, or other human-controlled blocker.
6. Before any upload, compute the SHA-256 of the attached JD-tailored resume and compare it to the required SHA-256 in this contract. Upload only when they match. First use the normal form upload. If it does not visibly succeed, force the same attached file through the browser file chooser and then the file-input retry. Report each attempt truthfully. A preflight-ready result requires the visible selected filename plus the computed attached-file SHA-256 in selected_resume_sha256; do not claim that the employer form itself displayed a hash. Never submit the form during preflight.

Return only truthful structured observations. A preflight-ready result is not a submission and must not claim it is."""

    @staticmethod
    def _execution_prompt(application: Mapping[str, str], *, resume_filename: str, resume_sha256: str) -> str:
        return f"""You are the Career OS Browser Executor for one pre-gated application.

Application identity:
- Company: {application['company']}
- Role: {application['title']}
- Verified job URL: {application['job_url']}
- Application record ID: {application['application_id']}
- Exact attached JD-tailored resume: {resume_filename}
- Required SHA-256: {resume_sha256}

The attached file is the exact Career OS JD-specific resume. Do not replace it,
modify it, invent claims, or upload another resume.

Execution contract:
1. Open only the verified job URL and inspect the complete form before any action.
2. Request an authenticated user browser when required. If a browser is not available, report BROWSER_UNAVAILABLE; do not substitute an unmanaged one.
3. Use only verified profile data and approved answers. Never invent or guess. Do not reinterpret technical-support experience as engineering experience; use the exact approved answer for every experience question.
4. Stop and report REVIEW_REQUIRED for CAPTCHA, OTP/MFA, identity verification, assessment, work-authorisation/sponsorship uncertainty, salary/CTC decision, relocation or notice-period judgement, a required custom cover letter, unknown mandatory fields, suspicious redirects, or any question requiring human input.
5. Before upload, compute the attached file's SHA-256 and compare it with Required SHA-256. Upload the attached tailored resume normally only when they match. If the normal upload does not visibly succeed, force the exact same attached file through the browser file chooser and then the file-input retry. Verify the visible selected filename and report the computed attached-file SHA-256; do not claim the employer form displayed a hash. Never use a master, generic, or another-job resume.
6. A resume upload is not proof of submission. Submit only if every field is deterministic and approved. After submission, verify an employer, ATS, or LinkedIn confirmation screen and report the exact source, URL, and evidence.
7. Do not contact recruiters, send connection requests, pay for services, or make changes beyond this single application.

Return the required structured outcome truthfully."""

    @staticmethod
    def _safety_flags_schema() -> dict[str, Any]:
        names = [
            "captcha", "otp", "mfa", "identity_verification", "login_or_identity_challenge",
            "assessment_or_test", "unknown_required_question", "unusual_free_text", "custom_cover_letter",
            "sensitive_or_legal_question", "additional_personal_question", "salary_judgment",
            "salary_or_ctc_question", "notice_period_judgment", "ambiguous_work_authorization",
            "work_authorization_unknown", "sponsorship_or_authorization_ambiguity", "unsupported_experience_question",
            "relocation_judgment", "on_site_availability_unknown", "shift_availability_unknown",
            "unexpected_site_behavior", "contradictory_profile_data", "unapproved_request", "suspicious_redirect",
        ]
        return {
            "type": "object",
            "properties": {name: {"type": "boolean"} for name in names},
            "required": names,
            "additionalProperties": False,
        }

    @classmethod
    def _preflight_schema(cls) -> dict[str, Any]:
        question = {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "required": {"type": "boolean"},
                "approved_answer": {"type": "string"},
                "approval_status": {"type": "string"},
            },
            "required": ["question", "required", "approved_answer", "approval_status"],
            "additionalProperties": False,
        }
        return {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["PREFLIGHT_READY", "REVIEW_REQUIRED", "BROWSER_UNAVAILABLE", "ERROR"]},
                "application_type": {"type": "string", "enum": ["easy_apply", "straightforward_form", "other"]},
                "application_method": {"type": "string"},
                "observed_application_url": {"type": "string"},
                "application_url_verified": {"type": "boolean"},
                "complete_form_verified": {"type": "boolean"},
                "required_answers_verified": {"type": "boolean"},
                "required_questions": {"type": "array", "items": question},
                "normal_upload_attempted": {"type": "boolean"},
                "normal_upload_succeeded": {"type": "boolean"},
                "file_chooser_retry_attempted": {"type": "boolean"},
                "file_chooser_retry_succeeded": {"type": "boolean"},
                "input_retry_attempted": {"type": "boolean"},
                "input_retry_succeeded": {"type": "boolean"},
                "selected_resume_filename": {"type": "string"},
                "selected_resume_sha256": {"type": "string"},
                "resume_attachment_visible": {"type": "boolean"},
                "safety_flags": cls._safety_flags_schema(),
                "blockers": {"type": "array", "items": {"type": "string"}},
                "application_record_id": {"type": "string"},
            },
            "required": [
                "status", "application_type", "application_method", "observed_application_url", "application_url_verified",
                "complete_form_verified", "required_answers_verified", "required_questions", "normal_upload_attempted",
                "normal_upload_succeeded", "file_chooser_retry_attempted", "file_chooser_retry_succeeded", "input_retry_attempted", "input_retry_succeeded", "selected_resume_filename",
                "selected_resume_sha256", "resume_attachment_visible", "safety_flags", "blockers", "application_record_id",
            ],
            "additionalProperties": False,
        }

    @staticmethod
    def _outcome_schema() -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["SUBMITTED", "REVIEW_REQUIRED", "BROWSER_UNAVAILABLE", "NOT_SUBMITTED", "ERROR"]},
                "submitted": {"type": "boolean"},
                "confirmation_source": {"type": "string", "enum": ["employer", "ats", "linkedin", "none"]},
                "confirmation_evidence": {"type": "string"},
                "confirmation_url": {"type": "string"},
                "resume_attachment_verified": {"type": "boolean"},
                "resume_sha256_verified": {"type": "boolean"},
                "selected_resume_filename": {"type": "string"},
                "selected_resume_sha256": {"type": "string"},
                "normal_upload_attempted": {"type": "boolean"},
                "normal_upload_succeeded": {"type": "boolean"},
                "file_chooser_retry_attempted": {"type": "boolean"},
                "input_retry_attempted": {"type": "boolean"},
                "blockers": {"type": "array", "items": {"type": "string"}},
                "application_record_id": {"type": "string"},
            },
            "required": [
                "status", "submitted", "confirmation_source", "confirmation_evidence", "confirmation_url",
                "resume_attachment_verified", "resume_sha256_verified", "selected_resume_filename", "selected_resume_sha256",
                "normal_upload_attempted", "normal_upload_succeeded", "file_chooser_retry_attempted", "input_retry_attempted",
                "blockers", "application_record_id",
            ],
            "additionalProperties": False,
        }

    def _create_task(self, *, title: str, prompt: str, file_id: str, filename: str, schema: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "title": title[:250],
            "interactive_mode": False,
            "share_visibility": "private",
            "agent_profile": os.getenv("MANUS_BROWSER_AGENT_PROFILE", "manus-1.6"),
            "structured_output_schema": schema,
            "message": {
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "file", "file_id": file_id, "filename": filename},
                ]
            },
        }
        return self._json_request("POST", "/task.create", payload)

    def create_preflight_task(
        self,
        application: Mapping[str, Any],
        resume_path: str | Path,
        *,
        resume_sha256: str,
        approved_questions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Create the inspection-only Manus browser preflight task."""
        prepared = self._require_application(application)
        expected_hash = str(resume_sha256 or "").strip().lower()
        if len(expected_hash) != 64:
            raise ManusApiError("A SHA-256 for the exact tailored resume is required for preflight.")
        uploaded = self.upload_resume(resume_path)
        return self._create_task(
            title=f"Career OS browser preflight — {prepared['company']} — {prepared['title']}",
            prompt=self._preflight_prompt(
                prepared,
                resume_filename=Path(resume_path).name,
                resume_sha256=expected_hash,
                approved_questions=approved_questions,
            ),
            file_id=str(uploaded.get("id") or ""),
            filename=Path(resume_path).name,
            schema=self._preflight_schema(),
        )

    def create_execution_task(
        self,
        application: Mapping[str, Any],
        resume_path: str | Path,
        *,
        resume_sha256: str | None = None,
    ) -> dict[str, Any]:
        """Create a private structured-output task with the exact resume attached."""
        prepared = self._require_application(application)
        path = Path(resume_path)
        if not path.is_file():
            raise ManusApiError(f"Resume file does not exist: {path}")
        expected_hash = str(resume_sha256 or "").strip().lower()
        if not expected_hash:
            import hashlib

            expected_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        uploaded = self.upload_resume(path)
        return self._create_task(
            title=f"Career OS browser execution — {prepared['company']} — {prepared['title']}",
            prompt=self._execution_prompt(prepared, resume_filename=path.name, resume_sha256=expected_hash),
            file_id=str(uploaded.get("id") or ""),
            filename=path.name,
            schema=self._outcome_schema(),
        )

    def list_messages(self, task_id: str, *, limit: int = 100) -> dict[str, Any]:
        if not str(task_id).strip():
            raise ManusApiError("task_id is required to list task messages.")
        return self._json_request("GET", f"/task.listMessages?{urlencode({'task_id': task_id, 'order': 'asc', 'limit': limit})}")

    def online_browsers(self) -> list[dict[str, Any]]:
        """Return available user browser clients without selecting one automatically."""
        response = self._json_request("GET", "/browser.onlineList")
        for key in ("clients", "browsers", "data", "results"):
            value = response.get(key)
            if isinstance(value, list):
                return [dict(item) for item in value if isinstance(item, Mapping)]
            if isinstance(value, Mapping):
                nested = value.get("clients") or value.get("results")
                if isinstance(nested, list):
                    return [dict(item) for item in nested if isinstance(item, Mapping)]
        return []

    @staticmethod
    def _events(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
        for key in ("messages", "results", "data"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                return [dict(item) for item in candidate if isinstance(item, Mapping)]
            if isinstance(candidate, Mapping):
                for nested_key in ("messages", "results", "items"):
                    nested = candidate.get(nested_key)
                    if isinstance(nested, list):
                        return [dict(item) for item in nested if isinstance(item, Mapping)]
        return []

    def inspect_task(self, task_id: str) -> dict[str, Any]:
        """Return a conservative task snapshot from Manus message events.

        The method never confirms a browser action.  A `needConnectMyBrowser`
        event is surfaced as a connection requirement, allowing an operator to
        select their intended authenticated browser through the supported API.
        """
        payload = self.list_messages(task_id)
        events = self._events(payload)
        agent_status = "unknown"
        waiting: dict[str, Any] = {}
        structured: dict[str, Any] | None = None
        errors: list[str] = []
        for event in events:
            source = event
            if isinstance(event.get("data"), Mapping):
                source = {**event, **dict(event["data"])}
            if source.get("type") == "status_update" or isinstance(source.get("status_update"), Mapping):
                update = source.get("status_update") or source
                if isinstance(update, Mapping):
                    agent_status = str(update.get("agent_status") or agent_status)
                    detail = update.get("status_detail")
                    if isinstance(detail, Mapping):
                        waiting = dict(detail)
            result = source.get("structured_output_result")
            if isinstance(result, Mapping):
                structured = dict(result)
            if source.get("type") == "error_message":
                errors.append(str(source.get("message") or source.get("error") or "Manus task returned an error"))
        browser_connection_required = waiting.get("waiting_for_event_type") == "needConnectMyBrowser"
        clients_available: bool | None = None
        if browser_connection_required:
            try:
                clients_available = bool(self.online_browsers())
            except ManusApiError as exc:
                errors.append(str(exc))
                clients_available = False
        return {
            "task_id": task_id,
            "agent_status": agent_status,
            "waiting": waiting,
            "browser_connection_required": browser_connection_required,
            "browser_clients_available": clients_available,
            "structured_output": structured,
            "errors": errors,
            "raw_message_count": len(events),
        }

    @staticmethod
    def structured_value(snapshot: Mapping[str, Any]) -> dict[str, Any] | None:
        """Return a completed structured value only when extraction succeeded."""
        structured = snapshot.get("structured_output")
        if not isinstance(structured, Mapping) or structured.get("success") is not True:
            return None
        value = structured.get("value")
        return dict(value) if isinstance(value, Mapping) else None

"""Secure server-side boundary between Conductor and the existing Career OS engine.

This module is an adapter only: all job-search business logic remains in
CareerOS.process and ControlledCareerPipeline. The endpoint is deliberately
review-oriented and cannot trigger browser application submission.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from .models import Job
from .pipeline_adapter import ControlledCareerPipeline


class ConductorPipelineRequest(BaseModel):
    profile: str = Field(min_length=1, max_length=200_000)
    job: Job
    browser_context: dict[str, Any] | None = None
    existing_application_page_id: str | None = Field(default=None, max_length=200)
    idempotency_key: str = Field(min_length=8, max_length=200)

    @field_validator("browser_context")
    @classmethod
    def reject_submission_controls(cls, value: dict[str, Any] | None):
        if not value:
            return value
        forbidden = {"submit_application", "auto_apply", "execute_application", "apply_now"}
        if any(key in forbidden for key in value):
            raise ValueError("automatic application submission is not supported by this boundary")
        return value


class ConductorPipelineResponse(BaseModel):
    boundary: str = "career-os"
    trace_id: str
    idempotency_key: str
    review_only: bool = True
    result: dict[str, Any]


class IdempotencyStore:
    """Persist only request keys and trace metadata; never persist payloads or secrets."""

    def __init__(self, path: str | None = None):
        self.path = Path(path or os.getenv("CAREER_OS_IDEMPOTENCY_PATH", ".career_os/conductor_idempotency.json"))
        self._lock = threading.Lock()

    def _read(self) -> dict[str, dict[str, Any]]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def reserve(self, key: str, trace_id: str) -> bool:
        with self._lock:
            records = self._read()
            if key in records:
                return False
            self.path.parent.mkdir(parents=True, exist_ok=True)
            records[key] = {"trace_id": trace_id, "reserved_at": int(time.time())}
            temp = self.path.with_suffix(".tmp")
            temp.write_text(json.dumps(records, separators=(",", ":")), encoding="utf-8")
            temp.replace(self.path)
            return True

    def release(self, key: str) -> None:
        with self._lock:
            records = self._read()
            if key not in records:
                return
            records.pop(key, None)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix(".tmp")
            temp.write_text(json.dumps(records, separators=(",", ":")), encoding="utf-8")
            temp.replace(self.path)


def _expected_token() -> str:
    return os.getenv("CAREER_OS_CONDUCTOR_TOKEN", "").strip()


def _authorize(token: str | None) -> None:
    expected = _expected_token()
    if not expected or not token or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="valid Conductor service token required")


def create_conductor_router(
    pipeline: ControlledCareerPipeline | None = None,
    idempotency: IdempotencyStore | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/conductor/v1", tags=["conductor"])
    controlled = pipeline or ControlledCareerPipeline()
    replay_guard = idempotency or IdempotencyStore()

    @router.get("/health")
    def conductor_health(x_conductor_token: str | None = Header(default=None)) -> dict[str, Any]:
        _authorize(x_conductor_token)
        return {
            "status": "ok",
            "boundary": "career-os",
            "review_only": True,
            "engine": "existing-career-os-process",
            "submission": "disabled",
            "capabilities": ["pipeline.review", "readiness.evaluate", "evidence.validate"],
        }

    @router.post("/pipeline/run", response_model=ConductorPipelineResponse)
    async def run_pipeline(
        request: Request,
        payload: ConductorPipelineRequest,
        x_conductor_token: str | None = Header(default=None),
    ) -> ConductorPipelineResponse:
        _authorize(x_conductor_token)
        trace_seed = f"{payload.idempotency_key}:{request.client.host if request.client else 'unknown'}"
        trace_id = hashlib.sha256(trace_seed.encode()).hexdigest()[:24]
        if not replay_guard.reserve(payload.idempotency_key, trace_id):
            raise HTTPException(status_code=409, detail="idempotency key has already been used")
        try:
            result = await controlled.process(
                payload.profile,
                payload.job,
                browser_context=payload.browser_context,
                existing_application_page_id=payload.existing_application_page_id,
            )
        except Exception as exc:
            replay_guard.release(payload.idempotency_key)
            # Do not echo exception text: provider errors can contain credentials or request data.
            raise HTTPException(status_code=502, detail={"trace_id": trace_id, "error": "career-os pipeline failed"}) from exc
        result_payload = result.model_dump(mode="json")
        result_payload["application_mode"] = "REVIEW_ONLY"
        result_payload["submission_enabled"] = False
        return ConductorPipelineResponse(
            trace_id=trace_id,
            idempotency_key=payload.idempotency_key,
            result=result_payload,
        )

    return router

"""Conductor-backed AI runtime for Career OS.

The Career OS process owns truth, evidence, deterministic validation and durable
state. Conductor owns model/provider execution. This keeps provider API keys out
of Career OS while preserving the DeepSeek-inspired harness contract: durable
handoff before execution, bounded retries, explicit wait/fail states, and
recoverable stage boundaries.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, TypeVar

import httpx

from .models import FitReport, TailoredResume
from .structured_output import StructuredOutputError, extract_first_json_object

T = TypeVar("T")


class ConductorRuntimeError(RuntimeError):
    """Safe, non-secret Conductor execution error."""


class ConductorRuntime:
    """Provider-neutral runtime that delegates AI work to AgentFlow/Conductor."""

    def __init__(self) -> None:
        base = os.getenv("CONDUCTOR_BASE_URL", "").rstrip("/")
        self.mcp_url = (os.getenv("CONDUCTOR_MCP_URL") or (base + "/api/conductor/mcp" if base else "")).strip()
        self.token = os.getenv("CONDUCTOR_BRIDGE_TOKEN", "").strip()
        self.poll_seconds = float(os.getenv("CONDUCTOR_POLL_SECONDS", "3"))
        self.timeout_seconds = float(os.getenv("CONDUCTOR_TIMEOUT_SECONDS", "300"))
        self.last_provider_used: str | None = None
        self.gemini_diagnostic: dict[str, object] = {"status": "NOT_USED", "credential_available": False, "provider_call_succeeded": None}
        self.challenger_diagnostic: dict[str, object] = {"selected_provider": "conductor", "status": "NOT_RUN"}

    def _require_config(self) -> None:
        if not self.mcp_url:
            raise ConductorRuntimeError("CONDUCTOR_MCP_URL is not configured")
        if not self.token:
            raise ConductorRuntimeError("CONDUCTOR_BRIDGE_TOKEN is not configured")

    async def _rpc(self, method: str, params: dict[str, Any] | None = None) -> Any:
        self._require_config()
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json", "Accept": "application/json"}
        body = {"jsonrpc": "2.0", "id": f"career-os-{int(time.time() * 1000)}", "method": method, "params": params or {}}
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(self.mcp_url, headers=headers, json=body)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            raise ConductorRuntimeError(f"Conductor transport failed: {type(exc).__name__}") from exc
        if payload.get("error"):
            error = payload["error"]
            raise ConductorRuntimeError(f"Conductor RPC failed: {error.get('message', 'unknown error')}")
        return payload.get("result")

    @staticmethod
    def _content_json(result: Any) -> Any:
        if isinstance(result, dict) and "content" in result:
            for item in result.get("content") or []:
                if isinstance(item, dict) and item.get("text"):
                    text = str(item["text"])
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        return text
        return result

    async def health(self) -> dict[str, Any]:
        result = await self._rpc("tools/call", {"name": "conductor_health", "arguments": {}})
        value = self._content_json(result)
        if not isinstance(value, dict):
            raise ConductorRuntimeError("Conductor health returned an invalid response")
        return value

    async def _submit(self, *, objective: str, workflow: str) -> str:
        result = await self._rpc("tools/call", {"name": "conductor_submit_objective", "arguments": {"objective": objective, "workflow": workflow, "provider": "auto"}})
        value = self._content_json(result)
        if not isinstance(value, dict) or not value.get("runId"):
            raise ConductorRuntimeError("Conductor accepted no durable run")
        return str(value["runId"])

    async def _get_run(self, run_id: str) -> dict[str, Any]:
        result = await self._rpc("tools/call", {"name": "conductor_get_run", "arguments": {"runId": run_id}})
        value = self._content_json(result)
        if not isinstance(value, dict):
            raise ConductorRuntimeError("Conductor returned an invalid run payload")
        return value

    @staticmethod
    def _run_output(run: dict[str, Any]) -> Any:
        if "output" in run:
            return run["output"]
        if isinstance(run.get("run"), dict) and "output" in run["run"]:
            return run["run"]["output"]
        return None

    async def _execute(self, *, objective: str, workflow: str) -> dict[str, Any]:
        run_id = await self._submit(objective=objective, workflow=workflow)
        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            run = await self._get_run(run_id)
            status = str(run.get("status") or run.get("run", {}).get("status") or "").upper()
            if status in {"COMPLETED", "SUCCEEDED", "SUCCESS"}:
                output = self._run_output(run)
                if output is None:
                    raise ConductorRuntimeError("Conductor marked the run complete without output")
                provider = run.get("provider") or run.get("run", {}).get("provider") or "conductor"
                model = run.get("model") or run.get("run", {}).get("model")
                self.last_provider_used = f"{provider}:{model}" if model else str(provider)
                return {"run_id": run_id, "output": output}
            if status in {"FAILED", "ERROR", "CANCELLED"}:
                raise ConductorRuntimeError(f"Conductor run {status.lower()}")
            if status in {"WAITING_FOR_INPUT", "WAITING_FOR_APPROVAL", "WAITING"}:
                raise ConductorRuntimeError(f"Conductor run requires continuation: {status}")
            await asyncio.sleep(self.poll_seconds)
        raise ConductorRuntimeError("Conductor run timed out")

    @staticmethod
    def _parse_json_output(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            nested = value.get("output")
            if nested is not None and nested is not value:
                return ConductorRuntime._parse_json_output(nested)
            return value
        text = str(value)
        try:
            cleaned = extract_first_json_object(text)
            parsed = json.loads(cleaned)
        except (StructuredOutputError, json.JSONDecodeError) as exc:
            raise ConductorRuntimeError("Conductor returned malformed JSON stage output") from exc
        if not isinstance(parsed, dict):
            raise ConductorRuntimeError("Conductor stage output must be a JSON object")
        return parsed

    async def _structured(self, *, workflow: str, objective: str, model_cls: type[T]) -> T:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                execution = await self._execute(objective=objective, workflow=workflow)
                return model_cls.model_validate(self._parse_json_output(execution["output"]))
            except ConductorRuntimeError as exc:
                last_error = exc
                if attempt == 1:
                    raise
            except (ValueError, TypeError) as exc:
                last_error = exc
                if attempt == 1:
                    raise ConductorRuntimeError("Conductor structured output validation failed") from exc
        raise ConductorRuntimeError("Conductor structured execution failed") from last_error

    async def fit(self, profile: str, job: Any, evidence_pack: Any = None, jd_analysis: Any = None) -> FitReport:
        objective = f"""Career OS FIT stage. Return ONLY one JSON object matching the FitReport schema.
Do not invent facts. Use only MASTER_PROFILE and EVIDENCE_PACK. Preserve employer mapping.
MASTER_PROFILE:\n{profile}\nEVIDENCE_PACK:\n{json.dumps(evidence_pack or [], default=str)}\nJD_ANALYSIS:\n{json.dumps(jd_analysis.model_dump() if hasattr(jd_analysis, 'model_dump') else (jd_analysis or {}), default=str)}\nJOB:\n{job.model_dump_json()}"""
        return await self._structured(workflow="CAREER_OS_FIT", objective=objective, model_cls=FitReport)

    async def resume(self, profile: str, job: Any, fit: FitReport, evidence_pack: Any = None, jd_analysis: Any = None) -> TailoredResume:
        objective = f"""Career OS RESUME stage. Return ONLY one JSON object matching the TailoredResume schema.
Use only supported evidence. Put confirmed tools under the correct employer. Never fabricate missing JD requirements.
MASTER_PROFILE:\n{profile}\nEVIDENCE_PACK:\n{json.dumps(evidence_pack or [], default=str)}\nFIT:\n{fit.model_dump_json()}\nJD_ANALYSIS:\n{json.dumps(jd_analysis.model_dump() if hasattr(jd_analysis, 'model_dump') else (jd_analysis or {}), default=str)}\nJOB:\n{job.model_dump_json()}"""
        return await self._structured(workflow="CAREER_OS_RESUME", objective=objective, model_cls=TailoredResume)

    async def challenge(self, profile: str, job: Any, fit: FitReport, resume: TailoredResume, evidence_pack: Any = None) -> str:
        objective = f"""Career OS INDEPENDENT REVIEW stage. Act as an adversarial recruiter reviewer.
Return concise plain text with exactly VERDICT, ISSUES, REQUIRED_FIXES. Do not rewrite the resume.
Challenge unsupported claims, employer mapping, missing requirements and keyword stuffing.
PROFILE:\n{profile}\nJOB:\n{job.model_dump_json()}\nFIT:\n{fit.model_dump_json()}\nRESUME:\n{resume.model_dump_json()}\nEVIDENCE_PACK:\n{json.dumps(evidence_pack or [], default=str)}"""
        execution = await self._execute(objective=objective, workflow="CAREER_OS_REVIEW")
        self.challenger_diagnostic = {"selected_provider": "conductor", "status": "READY", "run_id": execution["run_id"]}
        return str(execution["output"])

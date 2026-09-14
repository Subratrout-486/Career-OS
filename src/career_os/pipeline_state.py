"""Canonical sequential Career OS pipeline state machine.

This module is intentionally side-effect free. Departments use it to validate
inputs and produce durable state metadata; it never invokes another department.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import hashlib
from typing import Any


class Stage(StrEnum):
    DISCOVERY_INTAKE = "DISCOVERY_INTAKE"
    JD_ENRICHMENT = "JD_ENRICHMENT"
    MATCHING = "MATCHING"
    RESUME_RECOMMENDATION = "RESUME_RECOMMENDATION"
    NOTION_SYNC = "NOTION_SYNC"
    READY_TO_APPLY_VALIDATION = "READY_TO_APPLY_VALIDATION"
    AUTO_APPLY = "AUTO_APPLY"


class PipelineStatus(StrEnum):
    DISCOVERED = "DISCOVERED"
    INTAKED = "INTAKED"
    JD_PENDING = "JD_PENDING"
    JD_READY = "JD_READY"
    MATCH_PENDING = "MATCH_PENDING"
    MATCHED = "MATCHED"
    RESUME_PENDING = "RESUME_PENDING"
    RESUME_READY = "RESUME_READY"
    NOTION_PENDING = "NOTION_PENDING"
    NOTION_READY = "NOTION_READY"
    READY_TO_APPLY = "READY_TO_APPLY"
    APPLICATION_PENDING = "APPLICATION_PENDING"
    APPLIED = "APPLIED"


@dataclass(frozen=True)
class StageContract:
    stage: Stage
    input_status: PipelineStatus
    success_status: PipelineStatus
    pending_status: PipelineStatus


CONTRACTS: dict[Stage, StageContract] = {
    Stage.DISCOVERY_INTAKE: StageContract(Stage.DISCOVERY_INTAKE, PipelineStatus.DISCOVERED, PipelineStatus.INTAKED, PipelineStatus.DISCOVERED),
    Stage.JD_ENRICHMENT: StageContract(Stage.JD_ENRICHMENT, PipelineStatus.INTAKED, PipelineStatus.JD_READY, PipelineStatus.JD_PENDING),
    Stage.MATCHING: StageContract(Stage.MATCHING, PipelineStatus.JD_READY, PipelineStatus.MATCHED, PipelineStatus.MATCH_PENDING),
    Stage.RESUME_RECOMMENDATION: StageContract(Stage.RESUME_RECOMMENDATION, PipelineStatus.MATCHED, PipelineStatus.RESUME_READY, PipelineStatus.RESUME_PENDING),
    Stage.NOTION_SYNC: StageContract(Stage.NOTION_SYNC, PipelineStatus.RESUME_READY, PipelineStatus.NOTION_READY, PipelineStatus.NOTION_PENDING),
    Stage.READY_TO_APPLY_VALIDATION: StageContract(Stage.READY_TO_APPLY_VALIDATION, PipelineStatus.NOTION_READY, PipelineStatus.READY_TO_APPLY, PipelineStatus.NOTION_READY),
    Stage.AUTO_APPLY: StageContract(Stage.AUTO_APPLY, PipelineStatus.READY_TO_APPLY, PipelineStatus.APPLIED, PipelineStatus.APPLICATION_PENDING),
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def execution_key(job_id: str, stage: Stage | str, pipeline_version: str = "v1") -> str:
    raw = f"{job_id}:{str(stage)}:{pipeline_version}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def require_input(record: dict[str, Any], stage: Stage) -> None:
    contract = CONTRACTS[stage]
    actual = str(record.get("status") or record.get("pipeline_status") or "")
    if actual != contract.input_status.value:
        raise ValueError(f"{stage.value} accepts only {contract.input_status.value}; received {actual or '<missing>'}")


def begin_attempt(record: dict[str, Any], stage: Stage, pipeline_version: str = "v1") -> dict[str, Any]:
    require_input(record, stage)
    updated = dict(record)
    updated["current_stage"] = stage.value
    updated["attempt_count"] = int(updated.get("attempt_count") or 0) + 1
    updated["last_attempt_at"] = now_iso()
    updated["execution_key"] = execution_key(str(updated.get("job_id") or ""), stage, pipeline_version)
    return updated


def complete(record: dict[str, Any], stage: Stage, *, status: PipelineStatus | None = None) -> dict[str, Any]:
    contract = CONTRACTS[stage]
    output = status or contract.success_status
    if output not in (contract.success_status, contract.pending_status):
        raise ValueError(f"{stage.value} may output only {contract.success_status.value} or {contract.pending_status.value}")
    updated = dict(record)
    updated["status"] = output.value
    updated["pipeline_status"] = output.value
    updated["current_stage"] = stage.value
    updated["last_error"] = None
    updated["error_code"] = None
    updated["next_retry_at"] = None
    return updated


def fail(record: dict[str, Any], stage: Stage, error: Exception | str, error_code: str) -> dict[str, Any]:
    contract = CONTRACTS[stage]
    updated = dict(record)
    updated["status"] = contract.pending_status.value
    updated["pipeline_status"] = contract.pending_status.value
    updated["current_stage"] = stage.value
    updated["last_error"] = str(error)
    updated["error_code"] = error_code
    updated["last_attempt_at"] = updated.get("last_attempt_at") or now_iso()
    return updated


def is_successfully_completed(record: dict[str, Any], stage: Stage, pipeline_version: str = "v1") -> bool:
    contract = CONTRACTS[stage]
    return (str(record.get("status") or "") == contract.success_status.value and
            str(record.get("execution_key") or "") == execution_key(str(record.get("job_id") or ""), stage, pipeline_version))

"""Small browser-facing API for the Career OS control plane.

This service exposes only durable control-plane operations. Existing GitHub
Actions and the Python pipeline remain valid clients; they do not need to be
replaced to adopt this API.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .api_boundary import create_conductor_router
from .control_plane import (
    ApprovalStatus,
    ControlPlaneStore,
    MemoryItem,
    ModelRouter,
    bootstrap_registry,
    PlatformOrchestrator,
    RouteRequest,
    TaskStatus,
)
from .department_registry import bootstrap_department_registry


class ObjectiveRequest(BaseModel):
    objective: str = Field(min_length=1, max_length=2000)
    department: str = "orchestrator"
    payload: dict[str, Any] = Field(default_factory=dict)


class ApprovalDecisionRequest(BaseModel):
    status: ApprovalStatus
    decided_by: str = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=2000)


class ApprovalCreateRequest(BaseModel):
    action: str = Field(min_length=1, max_length=200)
    resource_type: str = Field(min_length=1, max_length=200)
    resource_id: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=2000)
    evidence: list[str] = Field(default_factory=list)
    task_id: str | None = None


class TaskResultRequest(BaseModel):
    status: TaskStatus
    result: dict[str, Any] | None = None
    failure_reason: str | None = None
    human_escalation: str | None = None
    model: str | None = None


def create_app(store: ControlPlaneStore | None = None) -> FastAPI:
    control_plane = store or ControlPlaneStore()
    bootstrap_registry(control_plane)
    bootstrap_department_registry(control_plane)
    platform = PlatformOrchestrator(control_plane)
    app = FastAPI(title="Career OS Control Plane", version="0.1.0")
    app.include_router(create_conductor_router())
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "ai_optional": True,
            "tasks": len(control_plane.tasks()),
            "pending_approvals": len(control_plane.approvals(pending_only=True)),
            "departments": len(control_plane.agents()),
        }

    @app.get("/api/dashboard")
    def dashboard() -> dict[str, Any]:
        tasks = control_plane.tasks()
        approvals = control_plane.approvals()
        return {
            "tasks": [task.model_dump(mode="json") for task in tasks],
            "approvals": [approval.model_dump(mode="json") for approval in approvals],
            "agents": [agent.model_dump(mode="json") for agent in control_plane.agents()],
            "models": [model.model_dump(mode="json") for model in control_plane.models()],
            "memory": [item.model_dump(mode="json") for item in control_plane.memory()],
            "audit": [event.model_dump(mode="json") for event in control_plane.audit_events()],
            "usage": [event.model_dump(mode="json") for event in control_plane.usage_events()],
        }

    @app.get("/api/tasks")
    def tasks() -> list[dict[str, Any]]:
        return [task.model_dump(mode="json") for task in control_plane.tasks()]

    @app.post("/api/objectives", status_code=201)
    def submit_objective(request: ObjectiveRequest) -> dict[str, Any]:
        task = platform.submit_objective(request.objective, department=request.department, payload=request.payload)
        return task.model_dump(mode="json")

    @app.post("/api/tasks/{task_id}/result")
    def record_task_result(task_id: str, request: TaskResultRequest) -> dict[str, Any]:
        try:
            task = platform.record_result(
                task_id,
                status=request.status,
                result=request.result,
                failure_reason=request.failure_reason,
                human_escalation=request.human_escalation,
                model=request.model,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return task.model_dump(mode="json")

    @app.post("/api/approvals", status_code=201)
    def create_approval(request: ApprovalCreateRequest) -> dict[str, Any]:
        try:
            approval = platform.request_approval(
                action=request.action,
                resource_type=request.resource_type,
                resource_id=request.resource_id,
                summary=request.summary,
                evidence=request.evidence,
                task_id=request.task_id,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return approval.model_dump(mode="json")

    @app.get("/api/approvals")
    def approvals(pending_only: bool = False) -> list[dict[str, Any]]:
        return [approval.model_dump(mode="json") for approval in control_plane.approvals(pending_only=pending_only)]

    @app.post("/api/approvals/{approval_id}/decision")
    def decide_approval(approval_id: str, request: ApprovalDecisionRequest) -> dict[str, Any]:
        try:
            approval = platform.decide_approval(approval_id, request.status, decided_by=request.decided_by, note=request.note)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return approval.model_dump(mode="json")

    @app.post("/api/memory", status_code=201)
    def add_memory(item: MemoryItem) -> dict[str, Any]:
        try:
            stored = platform.add_memory(item)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return stored.model_dump(mode="json")

    @app.get("/api/audit")
    def audit(task_id: str | None = None) -> list[dict[str, Any]]:
        return [event.model_dump(mode="json") for event in control_plane.audit_events(task_id)]

    @app.get("/api/usage")
    def usage() -> list[dict[str, Any]]:
        return [event.model_dump(mode="json") for event in control_plane.usage_events()]

    @app.get("/api/models")
    def models() -> list[dict[str, Any]]:
        return [model.model_dump(mode="json") for model in control_plane.models()]

    @app.get("/api/agents")
    def agents() -> list[dict[str, Any]]:
        return [agent.model_dump(mode="json") for agent in control_plane.agents()]

    @app.post("/api/route")
    def route(request: RouteRequest) -> dict[str, Any]:
        return ModelRouter(control_plane).route(request).model_dump(mode="json")

    dashboard_dir = Path(__file__).resolve().parents[2] / "dashboard"
    if dashboard_dir.exists():
        app.mount("/", StaticFiles(directory=dashboard_dir, html=True), name="dashboard")

    return app


app = create_app()

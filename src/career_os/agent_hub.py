"""Agent Command Hub for Career OS.

The hub is the control-plane directory for specialist agents. Career OS submits
an intent/command; the hub resolves the command to a registered agent, applies
its approval boundary, and creates a durable agent message. If the configured
runtime bridge is present, the dispatch is forwarded after durable persistence;
otherwise it remains queued without pretending execution occurred.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .control_plane import AgentMessage, PlatformOrchestrator, TaskRecord
from .runtime_bridge import RuntimeBridge

DEFAULT_REGISTRY = Path(__file__).resolve().parents[2] / "config" / "agent_registry.json"


class AgentDefinition(BaseModel):
    id: str
    name: str
    description: str
    capabilities: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    runtime: str
    approval: str = "none"


class AgentRegistry(BaseModel):
    version: int
    description: str
    default_runtime: str
    agents: list[AgentDefinition]
    routing: dict[str, str]

    @classmethod
    def load(cls, path: str | Path | None = None) -> "AgentRegistry":
        registry_path = Path(path or DEFAULT_REGISTRY)
        data = json.loads(registry_path.read_text(encoding="utf-8"))
        return cls.model_validate(data)

    def agent(self, agent_id: str) -> AgentDefinition:
        for agent in self.agents:
            if agent.id == agent_id:
                return agent
        raise KeyError(f"Agent is not registered in command hub: {agent_id}")

    def resolve(self, command: str) -> AgentDefinition:
        agent_id = self.routing.get(command)
        if not agent_id:
            raise KeyError(f"No agent route is registered for command: {command}")
        return self.agent(agent_id)

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class AgentDispatch(BaseModel):
    command: str = Field(min_length=1, max_length=200)
    objective: str = Field(min_length=1, max_length=2000)
    input: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any] | str] = Field(default_factory=list)
    task_id: str | None = None
    from_agent: str = "career-os-orchestrator"


class AgentHub:
    """Resolve commands, persist them, and optionally forward them to runtime."""

    def __init__(self, orchestrator: PlatformOrchestrator, registry: AgentRegistry | None = None, runtime_bridge: RuntimeBridge | None = None):
        self.orchestrator = orchestrator
        self.registry = registry or AgentRegistry.load()
        self.runtime_bridge = runtime_bridge or RuntimeBridge()

    def dispatch(self, request: AgentDispatch) -> tuple[TaskRecord, AgentMessage, AgentDefinition, dict[str, Any]]:
        agent = self.registry.resolve(request.command)
        task_id = request.task_id
        if task_id is None:
            task = self.orchestrator.submit_objective(
                request.objective,
                department=agent.id,
                payload={"command": request.command, **request.input},
            )
            task_id = task.id
        else:
            task = self.orchestrator.store.get_task(task_id)

        message = self.orchestrator.delegate(
            task_id,
            to_agent=agent.id,
            objective=request.objective,
            input_data={
                "command": request.command,
                "runtime": agent.runtime,
                "approval": agent.approval,
                **request.input,
            },
            evidence=request.evidence,
            from_agent=request.from_agent,
        )

        if agent.runtime == "conductor":
            runtime = self.runtime_bridge.dispatch(task, message, agent)
        else:
            runtime = {"status": "LOCAL_RUNTIME", "reason": "Agent is registered as a built-in deterministic runtime."}
        return task, message, agent, runtime

    def describe(self) -> dict[str, Any]:
        return {
            "version": self.registry.version,
            "default_runtime": self.registry.default_runtime,
            "runtime_bridge_configured": self.runtime_bridge.configured,
            "agents": [agent.model_dump(mode="json") for agent in self.registry.agents],
            "routing": self.registry.routing,
        }

"""Provider-agnostic multi-agent runtime for Career OS.

The runtime adapts DeepSeek Harness concepts without taking a dependency on
DeepSeek Harness. Career OS remains the domain/control plane; this module
provides the executable agent/subagent seam, delegation, checkpoints, policy
and verification hooks needed by the existing pipeline.
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from .agent_harness import ActionDecision, ActionPolicy, AgentHarness, HarnessRecovery, ToolExecutionPipeline
from .control_plane import AgentMessage, ControlPlaneStore, TaskRecord, TaskStatus


class AgentExecutor(Protocol):
    def __call__(self, *, objective: str, context: dict[str, Any], tools: list[str]) -> dict[str, Any] | Any: ...


@dataclass(frozen=True)
class AgentSpec:
    id: str
    name: str
    department: str
    capabilities: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    risk_level: str = "LOW"
    parent_allowed: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentResult:
    task_id: str
    agent_id: str
    status: str
    output: dict[str, Any]
    delegated_task_ids: tuple[str, ...] = ()


class AgentRegistry:
    """Capability registry; providers are injected rather than hard-coded."""
    def __init__(self) -> None:
        self._specs: dict[str, AgentSpec] = {}
        self._executors: dict[str, AgentExecutor] = {}

    def register(self, spec: AgentSpec, executor: AgentExecutor | None = None) -> None:
        self._specs[spec.id] = spec
        if executor is not None:
            self._executors[spec.id] = executor

    def get(self, agent_id: str) -> AgentSpec:
        return self._specs[agent_id]

    def executor(self, agent_id: str) -> AgentExecutor:
        return self._executors[agent_id]

    def list(self) -> list[AgentSpec]:
        return list(self._specs.values())

    def find(self, *, capability: str | None = None, department: str | None = None) -> list[AgentSpec]:
        return [s for s in self._specs.values() if (capability is None or capability in s.capabilities) and (department is None or s.department == department)]


class MultiAgentRuntime:
    """Durable agent loop facade with parent/child delegation and recovery."""
    def __init__(self, store: ControlPlaneStore | None = None, registry: AgentRegistry | None = None) -> None:
        self.store = store or ControlPlaneStore()
        self.registry = registry or default_registry()
        self.harness = AgentHarness(self.store)
        self.policy = ActionPolicy(self.store)
        self.tools = ToolExecutionPipeline(self.harness, self.policy)
        self.recovery = HarnessRecovery(self.store)

    def _new_task(self, spec: AgentSpec, objective: str, context: dict[str, Any], parent_task_id: str | None) -> TaskRecord:
        task = self.store.create_task(TaskRecord(objective=objective, department=spec.department, agent_id=spec.id, parent_task_id=parent_task_id, payload={"runtime": "career-os-v2", "agent": spec.id, "context": context}))
        task.status = TaskStatus.RUNNING
        self.store.update_task(task)
        self.harness.start_session(task.id, objective=objective, input_data=context)
        self.harness.start_step(task.id, step_index=0, input_data=context)
        return task

    def _finish(self, task: TaskRecord, output: Any) -> AgentResult:
        if not isinstance(output, dict):
            output = {"result": output}
        task.result = output
        task.status = TaskStatus.COMPLETED
        self.store.update_task(task)
        self.harness.end_step(task.id, step_index=0, output=output)
        self.harness.end_session(task.id, output=output)
        return AgentResult(task.id, task.agent_id or "unknown", TaskStatus.COMPLETED.value, output)

    def _fail(self, task: TaskRecord, exc: Exception) -> AgentResult:
        task.status = TaskStatus.RETRYING if task.retry_count < task.max_retries else TaskStatus.FAILED
        task.retry_count += 1
        task.failure_reason = str(exc)
        self.store.update_task(task)
        self.harness._event("AGENT_FAILED", task_id=task.id, output={"error": str(exc)}, decision=task.status.value)
        return AgentResult(task.id, task.agent_id or "unknown", task.status.value, {"error": str(exc)})

    def run(self, *, agent_id: str, objective: str, context: dict[str, Any] | None = None, parent_task_id: str | None = None) -> AgentResult:
        spec = self.registry.get(agent_id)
        task = self._new_task(spec, objective, context or {}, parent_task_id)
        try:
            output = self.registry.executor(agent_id)(objective=objective, context=context or {}, tools=list(spec.tools))
            if inspect.isawaitable(output):
                raise RuntimeError("Async agent executor requires MultiAgentRuntime.run_async()")
            return self._finish(task, output)
        except Exception as exc:
            return self._fail(task, exc)

    async def run_async(self, *, agent_id: str, objective: str, context: dict[str, Any] | None = None, parent_task_id: str | None = None) -> AgentResult:
        spec = self.registry.get(agent_id)
        task = self._new_task(spec, objective, context or {}, parent_task_id)
        try:
            output = self.registry.executor(agent_id)(objective=objective, context=context or {}, tools=list(spec.tools))
            if inspect.isawaitable(output):
                output = await output
            return self._finish(task, output)
        except Exception as exc:
            return self._fail(task, exc)

    def delegate(self, *, parent_task_id: str, agent_id: str, objective: str, context: dict[str, Any] | None = None) -> AgentResult:
        spec = self.registry.get(agent_id)
        if not spec.parent_allowed:
            raise PermissionError(f"Agent {agent_id} does not allow delegation")
        child = self.run(agent_id=agent_id, objective=objective, context=context, parent_task_id=parent_task_id)
        self._record_delegation(parent_task_id, agent_id, objective, context or {}, child)
        return child

    async def delegate_async(self, *, parent_task_id: str, agent_id: str, objective: str, context: dict[str, Any] | None = None) -> AgentResult:
        spec = self.registry.get(agent_id)
        if not spec.parent_allowed:
            raise PermissionError(f"Agent {agent_id} does not allow delegation")
        child = await self.run_async(agent_id=agent_id, objective=objective, context=context, parent_task_id=parent_task_id)
        self._record_delegation(parent_task_id, agent_id, objective, context or {}, child)
        return child

    def _record_delegation(self, parent_task_id: str, agent_id: str, objective: str, context: dict[str, Any], child: AgentResult) -> None:
        parent = self.store.get_task(parent_task_id)
        self.store.add_message(AgentMessage(task_id=parent_task_id, from_agent=parent.agent_id or "orchestrator", to_agent=agent_id, objective=objective, input=context, evidence=[child.output], status=TaskStatus.COMPLETED if child.status == TaskStatus.COMPLETED.value else TaskStatus.FAILED))

    def execute_external_action(self, *, task_id: str, step_index: int, tool: str, arguments: dict[str, Any], action: str, resource_type: str, resource_id: str, summary: str, executor: Callable[[], dict[str, Any] | str], verifier: Callable[[dict[str, Any] | str], bool], approval_available: bool = True, approval_id: str | None = None) -> tuple[ActionDecision, dict[str, Any] | str | None]:
        return self.tools.execute(task_id=task_id, step_index=step_index, tool=tool, arguments=arguments, action=action, resource_type=resource_type, resource_id=resource_id, summary=summary, executor=executor, verifier=verifier, approval_available=approval_available, approval_id=approval_id)

    def recover(self) -> list[dict[str, Any]]:
        return self.recovery.inspect()


def _safe_planner(*, objective: str, context: dict[str, Any], tools: list[str]) -> dict[str, Any]:
    return {"objective": objective, "plan": ["understand objective", "select specialist", "execute", "verify"], "available_tools": tools, "context_keys": sorted(context)}


def _research_agent(*, objective: str, context: dict[str, Any], tools: list[str]) -> dict[str, Any]:
    return {"objective": objective, "mode": "research", "requires_external_execution": True, "tools": tools, "next_action": "connect approved research provider"}


def _career_analyst(*, objective: str, context: dict[str, Any], tools: list[str]) -> dict[str, Any]:
    return {"objective": objective, "mode": "career-analysis", "inputs": context, "tools": tools, "next_action": "score against verified profile and job data"}


def _resume_agent(*, objective: str, context: dict[str, Any], tools: list[str]) -> dict[str, Any]:
    return {"objective": objective, "mode": "resume", "constraints": ["preserve verified facts", "do not invent experience"], "tools": tools}


def _engineering_agent(*, objective: str, context: dict[str, Any], tools: list[str]) -> dict[str, Any]:
    return {"objective": objective, "mode": "engineering", "tools": tools, "requires_approval_for": ["merge", "deploy", "external_side_effect"]}


def _application_agent(*, objective: str, context: dict[str, Any], tools: list[str]) -> dict[str, Any]:
    return {"objective": objective, "mode": "application-preparation", "tools": tools, "submit_requires_approval": True}


def default_registry() -> AgentRegistry:
    registry = AgentRegistry()
    registry.register(AgentSpec("ceo", "Career OS Orchestrator", "orchestrator", ("plan", "delegate", "verify"), ("delegate", "memory", "approval")), _safe_planner)
    registry.register(AgentSpec("job-research", "Job Research Agent", "job-research", ("research", "deduplicate"), ("search", "browser")), _research_agent)
    registry.register(AgentSpec("career-analyst", "Career Analyst", "strategy", ("reasoning", "matching", "gap-analysis"), ("jobs", "memory")), _career_analyst)
    registry.register(AgentSpec("resume-agent", "Resume Agent", "resume", ("resume", "ats", "truth-check"), ("files", "resume")), _resume_agent)
    registry.register(AgentSpec("engineering-copilot", "Engineering Copilot", "engineering", ("coding", "testing", "github"), ("filesystem", "terminal", "github"), risk_level="HIGH"), _engineering_agent)
    registry.register(AgentSpec("application-agent", "Application Agent", "application", ("browser", "forms", "verification"), ("browser", "notion"), risk_level="CRITICAL"), _application_agent)
    return registry


__all__ = ["AgentSpec", "AgentRegistry", "AgentResult", "MultiAgentRuntime", "default_registry"]

"""Consolidated provider-agnostic Career OS harness runtime.

``AgentRuntime`` remains the provider/model adapter. This module is the single
harness facade around it: registries, durable sessions/steps, delegation,
external-tool policy, recovery, and owner-only takeover boundaries all use the
existing ``ControlPlaneStore`` and safety policies.
"""
from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from .agent_harness import ActionDecision, ActionPolicy, AgentHarness, HarnessRecovery, ToolExecutionPipeline
from .control_plane import AgentMessage, AgentRecord, ApprovalRequest, ApprovalStatus, AuditEvent, ControlPlaneStore, ModelRecord, RouteRequest, TaskRecord, TaskStatus, ModelRouter, bootstrap_registry


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
class ToolSpec:
    id: str
    name: str
    capabilities: tuple[str, ...] = ()
    risk_level: str = "LOW"
    description: str = ""


@dataclass(frozen=True)
class AgentResult:
    task_id: str
    agent_id: str
    status: str
    output: dict[str, Any]
    delegated_task_ids: tuple[str, ...] = ()


class AgentRegistry:
    """Composable agent and executable registration seam."""
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


class ToolRegistry:
    """Explicit tool schema registry; execution still goes through policy."""
    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        self._specs[spec.id] = spec

    def get(self, tool_id: str) -> ToolSpec:
        return self._specs[tool_id]

    def list(self) -> list[ToolSpec]:
        return list(self._specs.values())


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class MultiAgentRuntime:
    """The one durable harness facade used by real Career OS agents."""
    def __init__(self, store: ControlPlaneStore | None = None, registry: AgentRegistry | None = None, *, provider_runtime: Any | None = None) -> None:
        self.store = store or ControlPlaneStore()
        self.registry = registry or default_registry(provider_runtime)
        self.tools_registry = default_tool_registry()
        self.harness = AgentHarness(self.store)
        self.policy = ActionPolicy(self.store)
        self.tools = ToolExecutionPipeline(self.harness, self.policy)
        self.recovery = HarnessRecovery(self.store)
        self.model_router = ModelRouter(self.store)
        self.provider_runtime = provider_runtime

    def available_models(self) -> list[ModelRecord]:
        return self.store.models()

    def route(self, request: RouteRequest):
        return self.model_router.route(request)

    def _new_task(self, spec: AgentSpec, objective: str, context: dict[str, Any], parent_task_id: str | None) -> TaskRecord:
        task = self.store.create_task(TaskRecord(objective=objective, department=spec.department, agent_id=spec.id, parent_task_id=parent_task_id, payload={"runtime": "career-os-harness-v1", "agent": spec.id, "context": _jsonable(context)}))
        task.status = TaskStatus.RUNNING
        self.store.update_task(task)
        self.harness.start_session(task.id, objective=objective, input_data={"context_keys": sorted(context)})
        self.harness.start_step(task.id, step_index=0, input_data={"context_keys": sorted(context)})
        return task

    def _finish(self, task: TaskRecord, output: Any) -> AgentResult:
        public_output = _jsonable(output)
        output_payload = public_output if isinstance(public_output, dict) else {"result": public_output}
        task.result = output_payload
        task.status = TaskStatus.COMPLETED
        self.store.update_task(task)
        self.harness.end_step(task.id, step_index=0, output={"keys": sorted(output_payload)})
        self.harness.end_session(task.id, output={"keys": sorted(output_payload)})
        return AgentResult(task.id, task.agent_id or "unknown", TaskStatus.COMPLETED.value, output_payload)

    async def execute_real_agent_async(self, *, parent_task_id: str, agent_id: str, objective: str, context: dict[str, Any] | None = None, existing_task_id: str | None = None) -> Any:
        """Run a registered specialist with DeepSeek-Harness-style continuation.

        A transient provider failure retries the same durable child task. A
        later correction/continuation can also supply ``existing_task_id`` so
        the same task/session is resumed instead of creating a second orphan
        task. Provider selection remains inside the configured provider
        runtime; this layer never performs a provider fallback.
        """
        spec = self.registry.get(agent_id)
        ctx = context or {}
        if existing_task_id:
            task = self.store.get_task(existing_task_id)
            if task.agent_id != agent_id:
                raise ValueError(f"Continuation agent mismatch: {task.agent_id} != {agent_id}")
            if task.parent_task_id != parent_task_id:
                raise ValueError("Continuation parent task mismatch")
            task.objective = objective
            task.payload["context"] = _jsonable(ctx)
            task.payload["continuation"] = True
            task.status = TaskStatus.RUNNING
            self.store.update_task(task)
            self.harness.start_step(task.id, step_index=task.retry_count + 1, input_data={"continuation": True, "agent_id": agent_id})
        else:
            task = self._new_task(spec, objective, ctx, parent_task_id)
        last_exc: Exception | None = None

        for attempt in range(task.max_retries + 1):
            task = self.store.get_task(task.id)
            task.status = TaskStatus.RUNNING
            task.payload["_harness_attempt"] = attempt + 1
            self.store.update_task(task)
            self.harness.start_step(task.id, step_index=attempt, input_data={"attempt": attempt + 1, "max_attempts": task.max_retries + 1, "agent_id": agent_id})
            try:
                output = self.registry.executor(agent_id)(objective=objective, context=ctx, tools=list(spec.tools))
                if inspect.isawaitable(output):
                    output = await output
                result = self._finish(task, output)
                self._record_delegation(parent_task_id, agent_id, objective, ctx, result)
                return output
            except Exception as exc:
                last_exc = exc
                task = self.store.get_task(task.id)
                task.failure_reason = f"{type(exc).__name__}: {exc}"
                task.retry_count = attempt + 1
                if attempt < task.max_retries:
                    task.status = TaskStatus.RETRYING
                    self.store.update_task(task)
                    self.harness.end_step(task.id, step_index=attempt, output={"retry": True, "error_type": type(exc).__name__, "next_attempt": attempt + 2})
                    self.harness._event("AGENT_RETRY_SCHEDULED", task_id=task.id, output={"attempt": attempt + 1, "next_attempt": attempt + 2, "error_type": type(exc).__name__}, decision="RETRYING")
                    await asyncio.sleep(min(2 ** attempt, 4))
                    continue
                task.status = TaskStatus.FAILED
                self.store.update_task(task)
                self.harness.end_step(task.id, step_index=attempt, output={"failed": True, "error_type": type(exc).__name__, "attempts": attempt + 1})
                self._record_delegation(parent_task_id, agent_id, objective, ctx, AgentResult(task.id, agent_id, TaskStatus.FAILED.value, {"error": type(exc).__name__}))
                raise
        raise RuntimeError("Agent execution exhausted without a terminal result") from last_exc

    def run(self, *, agent_id: str, objective: str, context: dict[str, Any] | None = None, parent_task_id: str | None = None) -> AgentResult:
        spec = self.registry.get(agent_id)
        task = self._new_task(spec, objective, context or {}, parent_task_id)
        try:
            output = self.registry.executor(agent_id)(objective=objective, context=context or {}, tools=list(spec.tools))
            if inspect.isawaitable(output):
                raise RuntimeError("Async agent executor requires MultiAgentRuntime.run_async()")
            result = self._finish(task, output)
        except Exception as exc:
            task.status = TaskStatus.RETRYING if task.retry_count < task.max_retries else TaskStatus.FAILED
            task.retry_count += 1
            task.failure_reason = f"{type(exc).__name__}: {exc}"
            self.store.update_task(task)
            result = AgentResult(task.id, task.agent_id or "unknown", task.status.value, {"error": type(exc).__name__})
        if parent_task_id:
            self._record_delegation(parent_task_id, agent_id, objective, context or {}, result)
        return result

    async def run_async(self, *, agent_id: str, objective: str, context: dict[str, Any] | None = None, parent_task_id: str | None = None) -> AgentResult:
        return AgentResult(agent_id, agent_id, "UNUSED", {}) if False else await self._run_async_impl(agent_id=agent_id, objective=objective, context=context, parent_task_id=parent_task_id)

    async def _run_async_impl(self, *, agent_id: str, objective: str, context: dict[str, Any] | None = None, parent_task_id: str | None = None) -> AgentResult:
        spec = self.registry.get(agent_id)
        task = self._new_task(spec, objective, context or {}, parent_task_id)
        try:
            output = self.registry.executor(agent_id)(objective=objective, context=context or {}, tools=list(spec.tools))
            if inspect.isawaitable(output):
                output = await output
            result = self._finish(task, output)
        except Exception as exc:
            task.status = TaskStatus.RETRYING if task.retry_count < task.max_retries else TaskStatus.FAILED
            task.retry_count += 1
            task.failure_reason = f"{type(exc).__name__}: {exc}"
            self.store.update_task(task)
            result = AgentResult(task.id, task.agent_id or "unknown", task.status.value, {"error": type(exc).__name__})
        if parent_task_id:
            self._record_delegation(parent_task_id, agent_id, objective, context or {}, result)
        return result

    def delegate(self, *, parent_task_id: str, agent_id: str, objective: str, context: dict[str, Any] | None = None) -> AgentResult:
        spec = self.registry.get(agent_id)
        if not spec.parent_allowed:
            raise PermissionError(f"Agent {agent_id} does not allow delegation")
        return self.run(agent_id=agent_id, objective=objective, context=context, parent_task_id=parent_task_id)

    async def delegate_async(self, *, parent_task_id: str, agent_id: str, objective: str, context: dict[str, Any] | None = None) -> AgentResult:
        spec = self.registry.get(agent_id)
        if not spec.parent_allowed:
            raise PermissionError(f"Agent {agent_id} does not allow delegation")
        return await self.run_async(agent_id=agent_id, objective=objective, context=context, parent_task_id=parent_task_id)

    def _record_delegation(self, parent_task_id: str, agent_id: str, objective: str, context: dict[str, Any], child: AgentResult) -> None:
        parent = self.store.get_task(parent_task_id)
        self.store.add_message(AgentMessage(task_id=parent_task_id, from_agent=parent.agent_id or "orchestrator", to_agent=agent_id, objective=objective, input=_jsonable(context), evidence=[child.output], status=TaskStatus.COMPLETED if child.status == TaskStatus.COMPLETED.value else TaskStatus.FAILED))

    def execute_external_action(self, *, task_id: str, step_index: int, tool: str, arguments: dict[str, Any], action: str, resource_type: str, resource_id: str, summary: str, executor: Callable[[], dict[str, Any] | str], verifier: Callable[[dict[str, Any] | str], bool], approval_available: bool = True, approval_id: str | None = None) -> tuple[ActionDecision, dict[str, Any] | str | None]:
        if tool not in {spec.id for spec in self.tools_registry.list()}:
            raise ValueError(f"Tool is not registered: {tool}")
        return self.tools.execute(task_id=task_id, step_index=step_index, tool=tool, arguments=arguments, action=action, resource_type=resource_type, resource_id=resource_id, summary=summary, executor=executor, verifier=verifier, approval_available=approval_available, approval_id=approval_id)

    def request_human_takeover(self, *, task_id: str, boundary: str, resource_type: str = "owner_authorization", resource_id: str = "owner") -> ApprovalRequest:
        task = self.store.get_task(task_id)
        approval = self.store.create_approval(ApprovalRequest(action="HUMAN_TAKEOVER", resource_type=resource_type, resource_id=resource_id, summary=boundary, requested_by="career-os-harness"))
        task.status = TaskStatus.AWAITING_APPROVAL
        self.store.update_task(task)
        self.store.add_audit(AuditEvent(event_type="HUMAN_TAKEOVER_REQUIRED", actor_type="harness", actor_id="career-os-harness", source="agent-harness", task_id=task_id, output={"approval_id": approval.id, "boundary": boundary}, decision="OWNER_ACTION_REQUIRED", approval_status=ApprovalStatus.PENDING.value))
        return approval

    def recover(self) -> list[dict[str, Any]]:
        return self.recovery.inspect()


def _safe_planner(*, objective: str, context: dict[str, Any], tools: list[str]) -> dict[str, Any]:
    return {"objective": objective, "plan": ["understand objective", "select specialist", "execute", "verify"], "available_tools": tools, "context_keys": sorted(context)}


def _real_fit_executor(provider_runtime):
    async def execute(*, objective: str, context: dict[str, Any], tools: list[str]):
        return await provider_runtime.fit(context["profile"], context["job"], context.get("evidence_pack"), context.get("jd_analysis"))
    return execute


def _real_resume_executor(provider_runtime):
    async def execute(*, objective: str, context: dict[str, Any], tools: list[str]):
        return await provider_runtime.resume(context["profile"], context["job"], context["fit"], context.get("evidence_pack"), context.get("jd_analysis"))
    return execute


def _real_challenge_executor(provider_runtime):
    async def execute(*, objective: str, context: dict[str, Any], tools: list[str]):
        return await provider_runtime.challenge(context["profile"], context["job"], context["fit"], context["resume"], context.get("evidence_pack"))
    return execute


def default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for spec in (ToolSpec("search", "Search", ("research",), "MEDIUM"), ToolSpec("browser", "Browser", ("browser", "verification"), "HIGH"), ToolSpec("filesystem", "Filesystem", ("files",), "HIGH"), ToolSpec("github", "GitHub", ("coding", "testing"), "HIGH"), ToolSpec("notion", "Notion", ("review",), "MEDIUM")):
        registry.register(spec)
    return registry


def default_registry(provider_runtime: Any | None = None) -> AgentRegistry:
    registry = AgentRegistry()
    registry.register(AgentSpec("ceo", "Career OS Orchestrator", "orchestrator", ("plan", "delegate", "verify"), ("notion",)), _safe_planner)
    if provider_runtime is not None:
        registry.register(AgentSpec("career-analyst", "Career Fit Analyst", "strategy", ("reasoning", "matching", "evidence"), ("notion",)), _real_fit_executor(provider_runtime))
        registry.register(AgentSpec("resume-agent", "Resume Agent", "resume", ("resume", "ats", "truth-check"), ("filesystem",)), _real_resume_executor(provider_runtime))
        registry.register(AgentSpec("recruiter-challenger", "Independent Recruiter Challenger", "quality", ("adversarial-review", "verification"), ()), _real_challenge_executor(provider_runtime))
    else:
        registry.register(AgentSpec("job-research", "Job Research Agent", "job-research", ("research", "deduplicate"), ("search",)), lambda **kwargs: {"objective": kwargs["objective"], "mode": "research", "requires_external_execution": True})
        registry.register(AgentSpec("career-analyst", "Career Analyst", "strategy", ("reasoning", "matching", "gap-analysis"), ("notion",)), lambda **kwargs: {"objective": kwargs["objective"], "mode": "career-analysis"})
        registry.register(AgentSpec("resume-agent", "Resume Agent", "resume", ("resume", "ats", "truth-check"), ("filesystem",)), lambda **kwargs: {"objective": kwargs["objective"], "mode": "resume"})
        registry.register(AgentSpec("engineering-copilot", "Engineering Copilot", "engineering", ("coding", "testing", "github"), ("filesystem", "github"), risk_level="HIGH"), lambda **kwargs: {"objective": kwargs["objective"], "mode": "engineering", "requires_approval_for": ["merge", "deploy", "external_side_effect"]})
        registry.register(AgentSpec("application-agent", "Application Agent", "application", ("browser", "forms", "verification"), ("browser", "notion"), risk_level="CRITICAL"), lambda **kwargs: {"objective": kwargs["objective"], "mode": "application-preparation", "submit_requires_approval": True})
    return registry


__all__ = ["AgentSpec", "ToolSpec", "AgentRegistry", "ToolRegistry", "AgentResult", "MultiAgentRuntime", "default_registry", "default_tool_registry"]
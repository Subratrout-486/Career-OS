"""Local-first, policy-aware tool registry for AgentFlow.

The registry follows the plugin/tool separation used by modern workflow engines:
workflows declare tool names, while the registry owns execution, permissions,
timeouts and audit metadata. No network/API provider is required by the registry.
"""
from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


ToolHandler = Callable[..., Any]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    handler: ToolHandler
    capabilities: frozenset[str] = field(default_factory=frozenset)
    timeout_sec: int = 60
    requires_approval: bool = False


class ToolExecutionError(RuntimeError):
    pass


class ToolApprovalRequired(ToolExecutionError):
    pass


class ToolRegistry:
    """Register and execute tools through one auditable policy boundary."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self.audit_log: list[dict[str, Any]] = []

    def register(self, spec: ToolSpec) -> None:
        if not spec.name or not spec.name.strip():
            raise ValueError("tool name is required")
        if spec.name in self._tools:
            raise ValueError(f"tool already registered: {spec.name}")
        if spec.timeout_sec <= 0:
            raise ValueError("timeout_sec must be positive")
        self._tools[spec.name] = spec

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "name": spec.name,
                "description": spec.description,
                "capabilities": sorted(spec.capabilities),
                "timeout_sec": spec.timeout_sec,
                "requires_approval": spec.requires_approval,
            }
            for spec in self._tools.values()
        ]

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ToolExecutionError(f"unknown tool: {name}") from exc

    async def execute(
        self,
        name: str,
        *,
        approval_granted: bool = False,
        capabilities: set[str] | frozenset[str] | None = None,
        **kwargs: Any,
    ) -> Any:
        spec = self.get(name)
        granted = set(capabilities or ())
        if spec.capabilities - granted:
            missing = sorted(spec.capabilities - granted)
            raise ToolExecutionError(f"tool capability denied: {name}: missing={missing}")
        if spec.requires_approval and not approval_granted:
            raise ToolApprovalRequired(f"approval required for tool: {name}")

        started = time.time()
        record = {"tool": name, "status": "RUNNING", "started_at": started}
        self.audit_log.append(record)
        try:
            result = spec.handler(**kwargs)
            if inspect.isawaitable(result):
                result = await asyncio.wait_for(result, timeout=spec.timeout_sec)
            else:
                result = await asyncio.wait_for(asyncio.to_thread(lambda: result), timeout=spec.timeout_sec)
            record.update({"status": "COMPLETED", "finished_at": time.time()})
            return result
        except asyncio.TimeoutError as exc:
            record.update({"status": "TIMEOUT", "finished_at": time.time()})
            raise ToolExecutionError(f"tool timed out: {name}") from exc
        except Exception as exc:
            record.update({"status": "FAILED", "finished_at": time.time(), "error": str(exc)})
            raise


def build_default_tool_registry() -> ToolRegistry:
    """Return the safe core registry; integrations are injected explicitly."""
    return ToolRegistry()

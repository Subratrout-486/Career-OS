"""Configurable outbound bridge from Career OS to an external agent runtime.

The bridge is deliberately provider-agnostic. Career OS never guesses a
Conductor API path: the exact dispatch endpoint is supplied by deployment
configuration. When it is absent, tasks remain durably queued instead of
pretending execution occurred.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from .agent_hub import AgentDefinition
from .control_plane import AgentMessage, TaskRecord


class RuntimeBridgeError(RuntimeError):
    """Raised when a configured runtime cannot accept a dispatch."""


class RuntimeBridge:
    def __init__(self, *, url: str | None = None, token: str | None = None, timeout: float = 20.0):
        self.url = (url or os.getenv("CONDUCTOR_DISPATCH_URL") or "").strip()
        self.token = (token or os.getenv("CAREER_OS_CONDUCTOR_RUNTIME_TOKEN") or "").strip()
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.url and self.token)

    def dispatch(self, task: TaskRecord, message: AgentMessage, agent: AgentDefinition) -> dict[str, Any]:
        if not self.configured:
            return {
                "status": "WAITING_FOR_RUNTIME",
                "reason": "CONDUCTOR_DISPATCH_URL and CAREER_OS_CONDUCTOR_RUNTIME_TOKEN are not configured.",
            }

        payload = {
            "protocol": "career-os-agent-dispatch/v1",
            "task": task.model_dump(mode="json"),
            "message": message.model_dump(mode="json"),
            "agent": agent.model_dump(mode="json"),
        }
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "X-Career-OS-Task-ID": task.id,
        }
        try:
            response = httpx.post(self.url, json=payload, headers=headers, timeout=self.timeout)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeBridgeError("Configured agent runtime rejected or could not receive the dispatch") from exc

        try:
            body = response.json()
        except ValueError:
            body = {"raw_response": response.text[:1000]}
        return {
            "status": "SENT_TO_RUNTIME",
            "runtime_response": body,
        }

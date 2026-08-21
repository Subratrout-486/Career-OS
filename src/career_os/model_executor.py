"""Provider-neutral model execution seam for the Career OS harness.

The harness owns task/session/checkpoint/recovery state. This protocol owns only
model reasoning. No provider is selected here, and no API key is required to
construct the harness. A provider adapter, local model adapter, or another
execution bridge can be injected at runtime.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class ModelExecutor(Protocol):
    async def generate(
        self,
        *,
        system: str,
        user: str,
        json_mode: bool = False,
        max_tokens: int = 4000,
    ) -> str: ...


@dataclass(frozen=True)
class ModelExecutionResult:
    text: str
    executor: str
    model: str | None = None


class NoModelConfigured(RuntimeError):
    """Raised when an agent requires reasoning but no model executor exists."""


class UnconfiguredModelExecutor:
    """Explicit fail-closed executor used by the harness when no model exists."""

    async def generate(self, *, system: str, user: str, json_mode: bool = False, max_tokens: int = 4000) -> str:
        raise NoModelConfigured(
            "No model executor is configured. The Career OS harness is operational, "
            "but model reasoning requires an injected executor (local or provider-backed)."
        )


__all__ = ["ModelExecutor", "ModelExecutionResult", "NoModelConfigured", "UnconfiguredModelExecutor"]

"""Self-sufficient specialist-agent routing for Career OS.

Inspired by the current DeepSeek Harness headless model and multi-agent coding
patterns: each stage has a named specialist role, an explicit model order, a
bounded retry budget, and no dependency on Conductor for primary execution.

This module only defines routing policy. It does not contain credentials and
never performs external side effects by itself.
"""
from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class DepartmentAgent:
    id: str
    purpose: str
    providers: tuple[str, ...]
    max_attempts: int = 2


DEFAULT_PROVIDER_ORDER = ("deepseek", "gemini", "anthropic", "xai", "manus")

DEPARTMENT_AGENTS: dict[str, DepartmentAgent] = {
    "fit": DepartmentAgent(
        "fit-analyst",
        "JD fit, gaps, blockers and recommendation",
        ("deepseek", "gemini", "anthropic", "xai", "manus"),
    ),
    "resume": DepartmentAgent(
        "resume-specialist",
        "truthful JD-specific resume generation",
        ("anthropic", "deepseek", "gemini", "xai", "manus"),
    ),
    "challenge": DepartmentAgent(
        "recruiter-reviewer",
        "independent adversarial recruiter review",
        ("gemini", "deepseek", "anthropic", "xai", "manus"),
    ),
    "engineering": DepartmentAgent(
        "engineering-repair",
        "inspect, patch, test and verify Career OS code",
        ("deepseek", "anthropic", "gemini", "xai", "manus"),
    ),
}


def _configured(provider: str) -> bool:
    if provider == "deepseek":
        return bool(os.getenv("DEEPSEEK_API_KEY"))
    if provider == "gemini":
        return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
    if provider == "anthropic":
        return bool(os.getenv("ANTHROPIC_API_KEY"))
    if provider == "xai":
        return bool(os.getenv("XAI_API_KEY"))
    if provider == "manus":
        return bool(os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_API_BASE"))
    return False


def provider_order(role: str) -> tuple[str, ...]:
    """Return configured providers in role-specific priority order.

    CAREER_OS_PROVIDER_ORDER can override the default order for an emergency
    provider incident, while still filtering out providers with no credential.
    """
    configured_override = os.getenv("CAREER_OS_PROVIDER_ORDER", "").strip()
    if configured_override:
        requested = tuple(x.strip().lower() for x in configured_override.split(",") if x.strip())
    else:
        requested = DEPARTMENT_AGENTS.get(role, DepartmentAgent(role, role, DEFAULT_PROVIDER_ORDER)).providers
    return tuple(p for p in requested if _configured(p))


def describe_agents() -> list[dict[str, object]]:
    return [
        {
            "id": agent.id,
            "role": role,
            "purpose": agent.purpose,
            "providers": list(agent.providers),
            "max_attempts": agent.max_attempts,
        }
        for role, agent in DEPARTMENT_AGENTS.items()
    ]

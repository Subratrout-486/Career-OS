"""OpenHands-backed coding agent for Career OS.

OpenHands is used only for engineering/code-repair tasks. It is deliberately
isolated from the normal job-processing provider pool and from Conductor.

The adapter follows the official OpenHands SDK pattern: an LLM is passed to a
default agent, a Conversation is bound to a workspace, and the agent runs a
bounded coding task. The dependency is optional so the normal Career OS
runtime does not require OpenHands to start.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class OpenHandsConfig:
    """Configuration for the optional OpenHands engineering agent."""

    enabled: bool
    model: str
    api_key: str | None
    base_url: str | None
    max_steps: int

    @classmethod
    def from_env(cls) -> "OpenHandsConfig":
        return cls(
            enabled=os.getenv("OPENHANDS_ENABLED", "0").lower() in {"1", "true", "yes"},
            model=os.getenv("OPENHANDS_LLM_MODEL", "deepseek/deepseek-chat"),
            api_key=os.getenv("OPENHANDS_API_KEY") or os.getenv("DEEPSEEK_API_KEY"),
            base_url=os.getenv("OPENHANDS_LLM_BASE_URL") or "https://api.deepseek.com",
            max_steps=max(1, int(os.getenv("OPENHANDS_MAX_STEPS", "40"))),
        )


def is_available() -> bool:
    """Return whether OpenHands is explicitly enabled and configured.

    Importing OpenHands is intentionally lazy. Career OS can therefore run
    without the optional coding-agent extra installed.
    """
    config = OpenHandsConfig.from_env()
    if not config.enabled or not config.api_key:
        return False
    try:
        import openhands.sdk  # noqa: F401
        import openhands.tools.preset  # noqa: F401
    except ImportError:
        return False
    return True


def run_coding_task(task: str, workspace: str | Path) -> dict[str, Any]:
    """Run an OpenHands coding task inside ``workspace``.

    The task is intentionally explicit about verification. OpenHands is not
    allowed to silently declare success: it must run the requested checks and
    leave its workspace in the resulting state for Career OS to inspect.
    """
    config = OpenHandsConfig.from_env()
    if not config.enabled:
        raise RuntimeError("OpenHands coding agent is disabled (set OPENHANDS_ENABLED=1)")
    if not config.api_key:
        raise RuntimeError(
            "OpenHands coding agent requires OPENHANDS_API_KEY or DEEPSEEK_API_KEY"
        )

    workspace_path = Path(workspace).resolve()
    if not workspace_path.exists() or not workspace_path.is_dir():
        raise RuntimeError(f"OpenHands workspace does not exist: {workspace_path}")

    try:
        from pydantic import SecretStr
        from openhands.sdk import Conversation, LLM
        from openhands.tools.preset import get_default_agent
    except ImportError as exc:
        raise RuntimeError(
            "OpenHands coding agent dependencies are not installed. "
            "Install Career OS with: pip install -e '.[coding-agent]'"
        ) from exc

    llm_kwargs: dict[str, Any] = {
        "model": config.model,
        "api_key": SecretStr(config.api_key),
    }
    if config.base_url:
        llm_kwargs["base_url"] = config.base_url

    llm = LLM(**llm_kwargs)
    agent = get_default_agent(llm=llm, cli_mode=True)
    conversation = Conversation(agent=agent, workspace=str(workspace_path))

    guarded_task = f"""
You are the Career OS Engineering Repair Agent.

Work ONLY inside the provided workspace. Do not expose or print credentials,
API keys, cookies, tokens, or other secrets.

Task:
{task}

Execution requirements:
1. Inspect the existing implementation before editing it.
2. Make the smallest production-quality changes necessary.
3. Do not introduce Conductor or MCP as a dependency for the self-sufficient
   Career OS runtime.
4. Run the most relevant tests after editing.
5. Run a syntax/import check for every Python file you changed.
6. Inspect the final diff and remove unrelated changes.
7. If a test still fails, report the exact first actionable failure rather than
   claiming success.
8. Do not fabricate test results.
"""

    conversation.send_message(guarded_task)
    conversation.run()

    return {
        "status": "completed",
        "agent": "openhands",
        "model": config.model,
        "workspace": str(workspace_path),
        "max_steps": config.max_steps,
    }

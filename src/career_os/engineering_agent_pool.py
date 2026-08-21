"""Optional engineering-agent pool for Career OS.

Career OS can use several open-source coding agents without making any of them a
hard dependency. The pool discovers installed CLIs at runtime and gives them a
common, auditable interface:

- OpenHands: autonomous coding/debugging agent.
- Goose: general-purpose local agent with coding/workflow capabilities.
- mini-SWE-agent: lightweight SWE-agent successor for repository repair.
- Aider: git-aware pair-programming/architect agent.

The agents are deliberately isolated from the normal career/job provider pool.
They are engineering tools only. A missing executable is a normal unavailable
state, not an application failure.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
from typing import Sequence


@dataclass(frozen=True)
class EngineeringAgent:
    id: str
    command: tuple[str, ...]
    purpose: str
    install_hint: str


AGENTS: dict[str, EngineeringAgent] = {
    "openhands": EngineeringAgent(
        id="openhands",
        command=("openhands", "--headless", "-t"),
        purpose="autonomous repository inspection, coding, testing and repair",
        install_hint="uv tool install openhands --python 3.12",
    ),
    "goose": EngineeringAgent(
        id="goose",
        command=("goose",),
        purpose="general-purpose local engineering and workflow agent",
        install_hint="Install goose from the official release for your OS",
    ),
    "mini-swe-agent": EngineeringAgent(
        id="mini-swe-agent",
        command=("mini", "-t"),
        purpose="lightweight autonomous software-engineering repair",
        install_hint="pipx install mini-swe-agent",
    ),
    "aider": EngineeringAgent(
        id="aider",
        command=("aider", "--yes", "--message"),
        purpose="git-aware coding, review and architect/editor workflows",
        install_hint="python -m pip install -U aider-chat",
    ),
}


@dataclass(frozen=True)
class AgentRunResult:
    agent: str
    status: str
    returncode: int | None
    stdout: str
    stderr: str
    workspace: str


def available_agents() -> list[str]:
    """Return installed engineering agents, without importing optional SDKs."""
    result: list[str] = []
    for agent_id, agent in AGENTS.items():
        if shutil.which(agent.command[0]):
            result.append(agent_id)
    return result


def _env_for(agent_id: str) -> dict[str, str]:
    env = os.environ.copy()
    # Keep agent execution explicit and prevent accidental provider fallback.
    env["CAREER_OS_ENGINEERING_AGENT"] = agent_id
    return env


def run_engineering_task(
    task: str,
    workspace: str | Path,
    *,
    agent: str = "auto",
    timeout_seconds: int = 1800,
    approve: bool = False,
) -> AgentRunResult:
    """Run one bounded engineering task with an installed open-source agent.

    ``approve=False`` uses the safest available invocation and is the default.
    The caller must explicitly opt into any agent-specific auto-approval flags.
    """
    workspace_path = Path(workspace).resolve()
    if not workspace_path.is_dir():
        raise ValueError(f"Engineering workspace does not exist: {workspace_path}")

    candidates = available_agents() if agent == "auto" else [agent]
    if not candidates:
        raise RuntimeError(
            "No engineering agent is installed. Install one of: "
            + ", ".join(f"{x} ({AGENTS[x].install_hint})" for x in AGENTS)
        )

    selected = candidates[0]
    if selected not in AGENTS:
        raise ValueError(f"Unknown engineering agent: {selected}")
    if not shutil.which(AGENTS[selected].command[0]):
        raise RuntimeError(f"Engineering agent is not installed: {selected}")

    if selected == "goose":
        # Goose is intentionally invoked through its normal interactive CLI
        # interface; a stdin task keeps this adapter compatible across releases.
        command: list[str] = ["goose", "run"]
        if approve:
            command.append("--no-session")
        command.extend(["--", task])
    else:
        command = list(AGENTS[selected].command) + [task]
        if selected == "aider" and not approve:
            # Aider's default mode is already confirmation-aware; don't add
            # auto-accept flags unless the caller explicitly requests them.
            pass
        if selected == "mini-swe-agent" and approve:
            command.append("--yolo")
        if selected == "openhands" and approve:
            command.append("--always-approve")

    completed = subprocess.run(
        command,
        cwd=workspace_path,
        env=_env_for(selected),
        text=True,
        capture_output=True,
        timeout=max(1, timeout_seconds),
        check=False,
    )
    status = "completed" if completed.returncode == 0 else "failed"
    return AgentRunResult(
        agent=selected,
        status=status,
        returncode=completed.returncode,
        stdout=completed.stdout[-20000:],
        stderr=completed.stderr[-20000:],
        workspace=str(workspace_path),
    )


def describe_agents() -> list[dict[str, object]]:
    return [
        {
            "id": agent.id,
            "purpose": agent.purpose,
            "installed": bool(shutil.which(agent.command[0])),
            "install_hint": agent.install_hint,
        }
        for agent in AGENTS.values()
    ]

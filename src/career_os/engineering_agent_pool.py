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


@dataclass(frozen=True)
class EngineeringAgent:
    id: str
    purpose: str
    install_hint: str


AGENTS: dict[str, EngineeringAgent] = {
    "openhands": EngineeringAgent(
        id="openhands",
        purpose="autonomous repository inspection, coding, testing and repair",
        install_hint="uv tool install openhands --python 3.12",
    ),
    "goose": EngineeringAgent(
        id="goose",
        purpose="general-purpose local engineering and workflow agent",
        install_hint="Install goose from the official release for your OS",
    ),
    "mini-swe-agent": EngineeringAgent(
        id="mini-swe-agent",
        purpose="lightweight autonomous software-engineering repair",
        install_hint="pipx install mini-swe-agent",
    ),
    "aider": EngineeringAgent(
        id="aider",
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


def _executable(agent_id: str) -> str:
    return "mini" if agent_id == "mini-swe-agent" else agent_id


def available_agents() -> list[str]:
    """Return installed engineering agents, without importing optional SDKs."""
    return [agent_id for agent_id in AGENTS if shutil.which(_executable(agent_id))]


def _env_for(agent_id: str) -> dict[str, str]:
    env = os.environ.copy()
    env["CAREER_OS_ENGINEERING_AGENT"] = agent_id
    return env


def _command(agent_id: str, task: str, approve: bool) -> list[str]:
    if agent_id == "openhands":
        command = ["openhands", "--headless", "-t", task]
        if approve:
            command.append("--always-approve")
        return command
    if agent_id == "goose":
        return ["goose", "run", "--text", task]
    if agent_id == "mini-swe-agent":
        command = ["mini", "-t", task]
        if approve:
            command.append("--yolo")
        return command
    if agent_id == "aider":
        command = ["aider", "--message", task]
        if approve:
            command.append("--yes-always")
        return command
    raise ValueError(f"Unknown engineering agent: {agent_id}")


def run_engineering_task(
    task: str,
    workspace: str | Path,
    *,
    agent: str = "auto",
    timeout_seconds: int = 1800,
    approve: bool = False,
) -> AgentRunResult:
    """Run one bounded engineering task with an installed open-source agent.

    `approve=False` is intentionally conservative. The selected agent remains
    responsible for its own normal tool permissions and sandboxing.
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
    if not shutil.which(_executable(selected)):
        raise RuntimeError(f"Engineering agent is not installed: {selected}")

    completed = subprocess.run(
        _command(selected, task, approve),
        cwd=workspace_path,
        env=_env_for(selected),
        text=True,
        capture_output=True,
        timeout=max(1, timeout_seconds),
        check=False,
    )
    return AgentRunResult(
        agent=selected,
        status="completed" if completed.returncode == 0 else "failed",
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
            "installed": bool(shutil.which(_executable(agent.id))),
            "install_hint": agent.install_hint,
        }
        for agent in AGENTS.values()
    ]

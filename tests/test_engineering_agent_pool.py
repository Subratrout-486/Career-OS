from pathlib import Path

import pytest

from career_os.engineering_agent_pool import AGENTS, _command, available_agents


def test_all_engineering_agents_are_optional():
    assert set(AGENTS) == {"openhands", "goose", "mini-swe-agent", "aider"}


def test_documented_commands_are_built_without_optional_imports():
    assert _command("openhands", "fix tests", False) == ["openhands", "--headless", "-t", "fix tests"]
    assert _command("goose", "fix tests", False) == ["goose", "run", "--text", "fix tests"]
    assert _command("mini-swe-agent", "fix tests", False) == ["mini", "-t", "fix tests"]
    assert _command("aider", "fix tests", False) == ["aider", "--message", "fix tests"]


def test_approval_flags_are_opt_in():
    assert "--always-approve" in _command("openhands", "x", True)
    assert "--yolo" in _command("mini-swe-agent", "x", True)
    assert "--yes-always" in _command("aider", "x", True)
    assert "--always-approve" not in _command("openhands", "x", False)


def test_available_agents_returns_only_installed_executables(monkeypatch):
    monkeypatch.setattr("career_os.engineering_agent_pool.shutil.which", lambda name: "/bin/fake" if name == "aider" else None)
    assert available_agents() == ["aider"]


def test_invalid_agent_command_fails():
    with pytest.raises(ValueError):
        _command("not-an-agent", "x", False)

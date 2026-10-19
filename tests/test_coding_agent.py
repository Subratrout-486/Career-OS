from pathlib import Path

from career_os.coding_agent import CodingRepairAgent


def test_repair_agent_rejects_shell_syntax(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    try:
        CodingRepairAgent(tmp_path, propose_patch=lambda _prompt, _failure: "", test_command=("python", "-c", "x && y"))
    except ValueError as exc:
        assert "forbidden shell syntax" in str(exc)
    else:
        raise AssertionError("unsafe test command was accepted")


def test_repair_agent_requires_git_checkout(tmp_path: Path):
    agent = CodingRepairAgent(tmp_path, propose_patch=lambda _prompt, _failure: "")
    try:
        agent.repair("boom")
    except ValueError as exc:
        assert "Git checkout" in str(exc)
    else:
        raise AssertionError("non-git directory was accepted")

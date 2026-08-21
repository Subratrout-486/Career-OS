"""Bounded self-healing coding agent for Career OS.

This module is deliberately isolated from the live orchestration path. It can
run in a disposable checkout/worktree, inspect a failure, ask a configured
coding model for a unified diff, apply it only after ``git apply --check``, run
an allow-listed test command, and roll the patch back when verification fails.

A DeepSeek Harness, SWE-agent, or another model can be used as the model
backend through the small ``propose_patch`` callable; the repair loop itself
remains provider-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import subprocess
from typing import Callable, Sequence


@dataclass(frozen=True)
class RepairAttempt:
    attempt: int
    patch_applied: bool
    tests_passed: bool
    output: str
    patch: str | None = None


@dataclass(frozen=True)
class RepairResult:
    status: str
    attempts: tuple[RepairAttempt, ...] = ()
    final_output: str = ""


PatchProposer = Callable[[str, str], str]


class CodingRepairAgent:
    """Safely repair repository failures inside an isolated checkout.

    The agent never commits, pushes, deploys, changes secrets, or executes a
    model-provided shell command. The model may propose only a unified diff;
    the runtime applies that diff and executes one configured test command.
    """

    def __init__(
        self,
        repo: str | Path,
        *,
        propose_patch: PatchProposer,
        test_command: Sequence[str] = ("python", "-m", "pytest", "-q"),
        max_attempts: int = 3,
        timeout_seconds: int = 180,
    ) -> None:
        self.repo = Path(repo).resolve()
        self.propose_patch = propose_patch
        self.test_command = tuple(test_command)
        self.max_attempts = max(1, min(max_attempts, 5))
        self.timeout_seconds = max(10, timeout_seconds)
        self._validate_test_command()

    def _validate_test_command(self) -> None:
        """Reject shell metacharacters and arbitrary command strings."""
        if not self.test_command:
            raise ValueError("test_command cannot be empty")
        forbidden = {"&&", "||", ";", "|", ">", ">>", "<", "`", "$(", "\n"}
        if any(any(token in arg for token in forbidden) for arg in self.test_command):
            raise ValueError("test_command contains forbidden shell syntax")
        if self.test_command[0] not in {"python", "python3", "pytest", "npm", "pnpm", "yarn"}:
            raise ValueError("test_command executable is not allow-listed")

    def _run(self, args: Sequence[str]) -> tuple[int, str]:
        completed = subprocess.run(
            list(args),
            cwd=self.repo,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=self.timeout_seconds,
            check=False,
        )
        return completed.returncode, completed.stdout[-20000:]

    def _git_diff(self) -> str:
        _, diff = self._run(("git", "diff", "--", "."))
        return diff

    def _clean_worktree(self) -> None:
        code, output = self._run(("git", "diff", "--check"))
        if code != 0:
            raise RuntimeError(f"Existing worktree contains invalid changes:\n{output}")

    def repair(self, failure: str, *, context: str = "") -> RepairResult:
        if not self.repo.is_dir() or not (self.repo / ".git").exists():
            raise ValueError("repo must be a Git checkout")

        self._clean_worktree()
        attempts: list[RepairAttempt] = []
        initial_head = self._run(("git", "rev-parse", "HEAD"))[1].strip()

        try:
            for attempt_no in range(1, self.max_attempts + 1):
                diff = self._git_diff()
                prompt = (
                    "You are the Career OS coding-repair agent. Diagnose the failure and "
                    "return ONLY a unified git diff. Do not change secrets, deployment "
                    "configuration, authentication, or unrelated files. Preserve existing "
                    "behavior except where required to fix the failure.\n\n"
                    f"FAILURE:\n{failure}\n\nCONTEXT:\n{context}\n\nCURRENT DIFF:\n{diff}"
                )
                patch = self.propose_patch(prompt, failure)
                if not patch.strip():
                    attempts.append(RepairAttempt(attempt_no, False, False, "Model returned an empty patch."))
                    continue

                check_code, check_output = self._run(("git", "apply", "--check", "--whitespace=error-all", "-"))
                # The patch must be supplied through stdin; rerun using Popen so
                # the model output is never interpreted by a shell.
                check = subprocess.run(
                    ["git", "apply", "--check", "--whitespace=error-all", "-"],
                    cwd=self.repo,
                    input=patch,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    timeout=self.timeout_seconds,
                    check=False,
                )
                if check.returncode != 0:
                    attempts.append(RepairAttempt(attempt_no, False, False, f"Patch rejected: {check.stdout[-8000:]}", patch))
                    failure = f"Previous patch was rejected by git apply --check:\n{check.stdout[-8000:]}"
                    continue

                applied = subprocess.run(
                    ["git", "apply", "--whitespace=error-all", "-"],
                    cwd=self.repo,
                    input=patch,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    timeout=self.timeout_seconds,
                    check=False,
                )
                if applied.returncode != 0:
                    attempts.append(RepairAttempt(attempt_no, False, False, f"Patch application failed: {applied.stdout[-8000:]}", patch))
                    failure = applied.stdout[-8000:]
                    continue

                test_code, test_output = self._run(self.test_command)
                passed = test_code == 0
                attempts.append(RepairAttempt(attempt_no, True, passed, test_output, patch))
                if passed:
                    return RepairResult("REPAIRED", tuple(attempts), test_output)

                # Never leave a failed model patch behind. The next attempt sees
                # the original checkout plus the new failure evidence.
                self._run(("git", "reset", "--hard", initial_head))
                failure = f"Tests still fail after the proposed repair:\n{test_output}"

            self._run(("git", "reset", "--hard", initial_head))
            return RepairResult("UNREPAIRED", tuple(attempts), attempts[-1].output if attempts else failure)
        except subprocess.TimeoutExpired as exc:
            self._run(("git", "reset", "--hard", initial_head))
            return RepairResult("TIMEOUT", tuple(attempts), str(exc))
        except Exception:
            self._run(("git", "reset", "--hard", initial_head))
            raise

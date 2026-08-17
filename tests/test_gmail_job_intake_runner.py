from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_github_actions_gmail_runner_invocation_resolves_scripts_import():
    env = os.environ.copy()
    env["GITHUB_TOKEN"] = ""

    result = subprocess.run(
        ["python", "scripts/gmail_job_intake_runner.py"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "ModuleNotFoundError: No module named 'scripts'" not in result.stderr
    assert "GITHUB_TOKEN is required" in result.stderr
    assert "oauth2.googleapis.com/token" not in result.stderr

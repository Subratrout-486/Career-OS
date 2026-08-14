#!/usr/bin/env python3
"""Advance a self-contained Career OS Manus browser lifecycle workspace.

The command is used by the automatic GitHub Actions queue.  Its workspace is
persisted as one private action artifact between workflow runs and contains the
pipeline results, exact generated resumes, task state, manifests, and audit
summaries.  It never accepts an arbitrary resume path or a manually assembled
manifest.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from career_os.browser_lifecycle import BrowserLifecycleError, run_automatic_lifecycle
from career_os.manus_browser_runner import ManusApiError
from dispatch_manus_browser_tasks import dispatch_records
from reconcile_manus_browser_execution import reconcile_state
from run_manus_browser_preflight import poll as poll_preflight
from run_manus_browser_preflight import start as start_preflight


def _approved_questions(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, dict):
        value = value.get("questions") or value.get("results") or []
    if not isinstance(value, list):
        raise BrowserLifecycleError("Approved-question export must contain a questions list")
    return [dict(item) for item in value if isinstance(item, dict)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("browser_lifecycle"))
    parser.add_argument("--approved-questions", type=Path)
    parser.add_argument("--output", type=Path, default=Path("browser_lifecycle_result.json"))
    args = parser.parse_args()

    try:
        summary = run_automatic_lifecycle(
            args.workspace,
            approved_questions=_approved_questions(args.approved_questions),
            preflight_start=start_preflight,
            preflight_poll=poll_preflight,
            dispatch_records=dispatch_records,
            reconcile_state=reconcile_state,
        )
    except (BrowserLifecycleError, ManusApiError, ValueError, TypeError) as exc:
        summary = {"status": "BLOCKED", "reason": str(exc), "continuation_required": False}
    args.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    # A blocked candidate is a preserved human-review outcome; only an invalid
    # lifecycle workspace or unhandled error should fail the runner itself.
    return 0 if summary.get("status") != "BLOCKED" else 2


if __name__ == "__main__":
    raise SystemExit(main())

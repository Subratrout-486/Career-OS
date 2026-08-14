#!/usr/bin/env python3
"""Reconcile structured Career OS browser-executor outcomes into Notion.

The command intentionally does not submit applications, poll browsers, or infer
success from a task ID. It records an ``Applied`` state only when the supplied
browser outcome contains explicit submission and employer/ATS confirmation
evidence; every other outcome remains Review.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from career_os.applications import ApplicationsTracker


def _records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    records = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        raise ValueError("Outcome manifest must contain a results list.")
    return [item for item in records if isinstance(item, dict)]


async def reconcile(payload: dict[str, Any]) -> list[dict[str, Any]]:
    tracker = ApplicationsTracker()
    results: list[dict[str, Any]] = []
    for item in _records(payload):
        application_id = str(item.get("application_record_id") or item.get("application_id") or "").strip()
        if not application_id:
            results.append({"status": "BLOCKED", "reason": "application_record_id is required"})
            continue
        try:
            persisted = await tracker.record_browser_outcome(application_id, item)
            results.append({"application_record_id": application_id, "status": "RECORDED", **persisted})
        except Exception as exc:
            results.append({"application_record_id": application_id, "status": "ERROR", "reason": str(exc)})
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outcomes", required=True, type=Path, help="Structured outcome JSON returned by browser execution tasks.")
    parser.add_argument("--results", type=Path, default=Path("browser_outcome_reconciliation.json"))
    args = parser.parse_args()
    payload: dict[str, Any] = json.loads(args.outcomes.read_text(encoding="utf-8"))
    results = asyncio.run(reconcile(payload))
    args.results.write_text(json.dumps({"results": results}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"results": results}, indent=2))
    return 0 if all(item.get("status") == "RECORDED" for item in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())

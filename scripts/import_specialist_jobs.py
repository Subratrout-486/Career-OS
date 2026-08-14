#!/usr/bin/env python3
"""Import authorized Jobright/Simplify browser captures into Career OS intake.

This command never authenticates to, scrapes, or submits through either service.
Provide a JSON list exported or captured with the user's authorization; the
script normalizes and deduplicates records before persisting job JSON files for
the existing Career OS pipeline. When a GitHub token is available, it also uses
the existing Career OS issue registry for cross-run duplicate checks.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from career_os.source_intake import (
    SourceIntakeError,
    deduplicate_source_jobs,
    normalize_source_job,
    source_capability,
)


REPO = os.environ.get("GITHUB_REPOSITORY", "Subratrout-486/Career-OS")
TOKEN = os.environ.get("GITHUB_TOKEN", "")


def _records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    if isinstance(value, dict) and isinstance(value.get("jobs"), list):
        return [dict(item) for item in value["jobs"] if isinstance(item, dict)]
    raise SourceIntakeError("Input JSON must be a list of jobs or an object with a jobs list")


def _load_existing_keys(output_dir: Path) -> set[str]:
    keys: set[str] = set()
    for path in output_dir.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        value = str(payload.get("dedupe_key") or "").strip()
        if value:
            keys.add(value)
    return keys


def _github_issue_exists(url: str) -> bool:
    """Check the durable Career OS intake registry when credentials are present."""
    if not TOKEN:
        return False
    query = urllib.parse.quote(f'repo:{REPO} "{url}"')
    request = urllib.request.Request(
        f"https://api.github.com/search/issues?q={query}&per_page=1",
        headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return int(json.loads(response.read().decode("utf-8")).get("total_count", 0)) > 0
    except OSError as exc:
        raise SourceIntakeError(f"Central GitHub duplicate check failed: {exc}") from exc


def _create_intake_issue(job: dict[str, Any]) -> None:
    """Create the same durable intake marker consumed by existing Career OS flows."""
    marker = "<!-- CAREER_OS_JOB_V1 -->"
    payload = json.dumps(job, ensure_ascii=False, indent=2)
    body = (
        f"{marker}\n\n## Authorized specialist-source Career OS intake\n\n"
        "This job was normalized from a user-authorized browser capture or JSON export. "
        "Process it through the normal Career OS verification and safety pipeline; do not "
        "submit unless the existing AUTO_APPLY contract is satisfied and employer confirmation "
        "can later be verified.\n\n```json\n{payload}\n```\n"
    )
    title = f"Career OS Job Intake — {job['company']} — {job['title']}"
    subprocess.run(
        ["gh", "issue", "create", "--repo", REPO, "--title", title[:250], "--body", body],
        check=True,
        env={**os.environ, "GH_TOKEN": TOKEN},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, choices=("jobright", "simplify", "employer_ats"))
    parser.add_argument("--input", required=True, help="Authorized JSON export or browser-capture file")
    parser.add_argument("--intake-method", default="authorized_browser_capture", choices=("authorized_json_export", "authorized_browser_capture", "public_ats_feed"))
    parser.add_argument("--output-dir", default="jobs/discovery_runtime")
    parser.add_argument("--report", default="source_intake_report.json")
    parser.add_argument("--paths-output", default="source_intake_paths.txt", help="Write newly persisted job paths for downstream pipeline processing")
    issue_mode = parser.add_mutually_exclusive_group()
    issue_mode.add_argument("--create-intake-issues", dest="create_intake_issues", action="store_true", help="Create standard Career OS intake issues after central duplicate checks")
    issue_mode.add_argument("--no-create-intake-issues", dest="create_intake_issues", action="store_false", help="Keep the import local and do not create GitHub issues")
    parser.set_defaults(create_intake_issues=None)
    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    create_issues = bool(TOKEN) if args.create_intake_issues is None else bool(args.create_intake_issues)
    try:
        if create_issues and not TOKEN:
            raise SourceIntakeError("GitHub issue creation was requested but GITHUB_TOKEN is unavailable")
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        normalized = [normalize_source_job(item, source=args.source, intake_method=args.intake_method) for item in _records(payload)]
        unique, in_batch_duplicates = deduplicate_source_jobs(normalized)
        output_dir.mkdir(parents=True, exist_ok=True)
        existing_keys = _load_existing_keys(output_dir)
        persisted: list[str] = []
        existing_duplicates: list[dict[str, Any]] = []
        registry_duplicates: list[dict[str, Any]] = []
        created_issue_ids: list[str] = []
        for job in unique:
            if job["dedupe_key"] in existing_keys:
                existing_duplicates.append(job)
                continue
            if create_issues and _github_issue_exists(job["url"]):
                registry_duplicates.append(job)
                continue
            if create_issues:
                _create_intake_issue(job)
                created_issue_ids.append(job["source_job_id"])
            output_path = output_dir / f"job-{job['dedupe_key'][:16]}.json"
            output_path.write_text(json.dumps(job, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            persisted.append(str(output_path))
            existing_keys.add(job["dedupe_key"])
        report = {
            "source_capability": source_capability(args.source),
            "input": str(input_path),
            "central_registry": {
                "repository": REPO,
                "github_duplicate_check": "performed" if create_issues else "not_configured_or_disabled",
                "intake_issue_creation": create_issues,
                "created_source_job_ids": created_issue_ids,
            },
            "persisted": persisted,
            "in_batch_duplicates": in_batch_duplicates,
            "existing_duplicates": existing_duplicates,
            "registry_duplicates": registry_duplicates,
            "notes": [
                "No Jobright/Simplify API was called.",
                "No browser application was submitted.",
                "Each persisted record must still pass the existing Career OS verification, Truth Guard, review, and browser gates.",
            ],
        }
        Path(args.report).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        Path(args.paths_output).write_text("\n".join(persisted) + ("\n" if persisted else ""), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0
    except (OSError, json.JSONDecodeError, SourceIntakeError, subprocess.CalledProcessError) as exc:
        print(f"SOURCE_INTAKE_FAILED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

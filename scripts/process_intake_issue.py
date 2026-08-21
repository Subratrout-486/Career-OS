#!/usr/bin/env python3
"""Process one trusted Career OS intake issue through the real pipeline."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import urllib.request
from pathlib import Path

from career_os.control_plane import ControlPlaneStore
from career_os.evidence_vault_snapshot import VAULT_SNAPSHOT
from career_os.models import Job
from career_os.orchestrator import CareerOS
from career_os.pipeline_harness import PipelineHarness

MARKER = "<!-- CAREER_OS_JOB_V1 -->"


def github_json(path: str) -> dict:
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY", "Subratrout-486/Career-OS")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/{path.lstrip('/')}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def add_issue_comment(issue_number: int, body: str) -> None:
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY", "Subratrout-486/Career-OS")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments",
        data=json.dumps({"body": body}).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30):
        pass


def extract_job(body: str) -> Job:
    if MARKER not in body:
        raise ValueError("Issue is not a trusted Career OS intake issue")
    match = re.search(r"```json\s*(\{.*?\})\s*```", body, re.DOTALL)
    if not match:
        raise ValueError("Trusted intake issue does not contain a JSON job payload")
    return Job.model_validate(json.loads(match.group(1)))


async def run(issue_number: int, *, no_notion_write: bool, output_dir: Path) -> dict:
    issue = github_json(f"issues/{issue_number}")
    job = extract_job(str(issue.get("body") or ""))
    profile = Path("config/master_profile.md").read_text(encoding="utf-8")
    store_path = output_dir / f"issue-{issue_number}-control-plane.json"
    store = ControlPlaneStore(store_path)
    harness = PipelineHarness(store)

    # The harness smoke source is deliberately isolated from live Notion so it
    # can prove the full AI/JD/resume/ATS/challenge pipeline even when production
    # credentials are not available. Real intake records always use the live
    # Notion Career Evidence Vault and never silently fall back.
    is_harness_smoke = job.source == "harness-smoke"
    vault = VAULT_SNAPSHOT if is_harness_smoke else None
    write_to_notion = False if is_harness_smoke else not no_notion_write

    task, result = await harness.run(
        objective=f"Process intake issue #{issue_number}: {job.company} — {job.title}",
        context={"issue_number": issue_number, "job_id": job.job_id, "company": job.company, "title": job.title},
        operation=lambda: CareerOS(vault=vault, write_to_notion=write_to_notion).process(profile, job),
    )
    payload = result.model_dump()
    payload["harness"] = {
        "task_id": task.id,
        "status": task.status.value,
        "recovery_pending": harness.recover(),
        "evidence_source": "offline-test-snapshot" if is_harness_smoke else "live-notion",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"issue-{issue_number}-result.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue-number", type=int, required=True)
    parser.add_argument("--no-notion-write", action="store_true")
    parser.add_argument("--output-dir", default="jobs/pipeline_runtime")
    args = parser.parse_args()

    try:
        payload = asyncio.run(run(args.issue_number, no_notion_write=args.no_notion_write, output_dir=Path(args.output_dir)))
        summary = (
            f"### Career OS processing complete\n\n"
            f"- Harness task: `{payload['harness']['task_id']}`\n"
            f"- Harness status: **{payload['harness']['status']}**\n"
            f"- Evidence source: **{payload['harness']['evidence_source']}**\n"
            f"- Review status: **{payload.get('review_status')}**\n"
            f"- Application mode: **{payload.get('application_mode')}**\n"
            f"- Errors/warnings recorded: **{len(payload.get('errors') or [])}**\n"
            f"- Recovery pending: **{bool(payload['harness']['recovery_pending'])}**\n\n"
            "This result was produced by the durable Career OS harness. Browser submission remains subject to the existing Application Mode safety contract."
        )
        add_issue_comment(args.issue_number, summary)
        print(json.dumps({
            "issue_number": args.issue_number,
            "harness_status": payload["harness"]["status"],
            "review_status": payload.get("review_status"),
            "application_mode": payload.get("application_mode"),
            "error_count": len(payload.get("errors") or []),
        }, indent=2))
        return 0
    except Exception as exc:
        try:
            add_issue_comment(args.issue_number, f"### Career OS processing blocked\n\n`{type(exc).__name__}: {exc}`\n\nThe run failed closed; no application submission was attempted.")
        except Exception:
            pass
        raise


if __name__ == "__main__":
    raise SystemExit(main())

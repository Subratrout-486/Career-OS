#!/usr/bin/env python3
"""Robust Gmail discovery wrapper for Career OS.

Stage 1 only: ingest and validate job-alert candidates. No matching, resume,
Notion, or browser execution is performed here.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# When a Python file is executed directly (``python scripts/foo.py``), Python
# puts ``scripts/`` on sys.path rather than the repository root.  The previous
# runner therefore failed before importing anything with ``ModuleNotFoundError:
# No module named 'scripts'``.  Add the repo root explicitly so direct execution
# and module execution behave identically in GitHub Actions and local runs.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import gmail_job_intake as intake
from scripts.intake_contract import contract_record

MAX_NEW = int(os.environ.get("MAX_NEW_EMAIL_JOBS", "10"))
PAGE_SIZE = min(int(os.environ.get("GMAIL_PAGE_SIZE", "100")), 100)
MAX_PAGES = max(int(os.environ.get("GMAIL_MAX_PAGES", "10")), 1)

GITHUB_NOTIFICATION_RE = re.compile(
    r"(?i)(github\.com|notifications@github\.com|\[subratrout-486/career-os\]|"
    r"career os\s*[—-]\s*(run failed|self heal|validate career os|provider fallback|job intake))"
)


def is_repository_noise(subject: str, sender: str) -> bool:
    return bool(GITHUB_NOTIFICATION_RE.search(f"{sender}\n{subject}"))


def fetch_message_ids(token: str) -> list[str]:
    query = os.environ.get(
        "GMAIL_QUERY",
        "newer_than:7d (job OR jobs OR career OR opportunity OR hiring OR support)",
    )
    if "-from:" not in query.lower():
        query = f"({query}) -from:(github.com)"

    ids: list[str] = []
    page_token: str | None = None
    for _ in range(MAX_PAGES):
        params: dict[str, str] = {"q": query, "maxResults": str(PAGE_SIZE)}
        if page_token:
            params["pageToken"] = page_token
        result = intake.gmail_get("messages", token, params)
        for item in result.get("messages") or []:
            message_id = str(item.get("id") or "")
            if message_id:
                ids.append(message_id)
        page_token = result.get("nextPageToken")
        if not page_token or len(ids) >= MAX_NEW * 25:
            break
    return ids


def main() -> int:
    if not intake.TOKEN:
        raise RuntimeError("GITHUB_TOKEN is required")

    token = intake.access_token()
    message_ids = fetch_message_ids(token)
    created = 0
    paths: list[str] = []
    inspected = 0
    skipped_noise = 0
    rejected: list[dict[str, object]] = []

    for message_id in message_ids:
        if created >= MAX_NEW:
            break
        message = intake.gmail_get(f"messages/{message_id}", token, {"format": "full"})
        headers = intake.headers_map(message)
        subject = headers.get("subject", "")
        sender = headers.get("from", "")
        inspected += 1

        if is_repository_noise(subject, sender):
            skipped_noise += 1
            continue
        marker = f"CAREER_OS_GMAIL_V1:{message_id}"
        if intake.issue_exists(marker):
            print(f"GMAIL_DUPLICATE_SKIPPED: message={message_id}")
            continue
        if intake.NON_JOB_RE.search(subject):
            print(f"GMAIL_NON_JOB_SKIPPED: subject={subject}")
            continue

        html_parts: list[str] = []
        text_parts: list[str] = []
        intake.collect_bodies(message.get("payload") or {}, html_parts=html_parts, text_parts=text_parts)
        html_body = "\n".join(html_parts)
        text_body = "\n".join(text_parts)
        clean_html = intake.strip_html(html_body)
        blob = f"{subject}\n{sender}\n{text_body}\n{clean_html}"
        links = intake.candidate_links(html_body)
        is_job, score, signals = intake.classify_email(subject, sender, blob, links)

        if intake.NON_JOB_RE.search(blob[:5000]) and not intake.TITLE_RE.search(subject):
            print(f"GMAIL_NON_JOB_SKIPPED: sender={sender} subject={subject}")
            continue
        if not is_job:
            print(f"GMAIL_CLASSIFICATION_SKIPPED: score={score} signals={','.join(signals) or 'none'} subject={subject}")
            continue

        job = intake.make_job(message_id, subject, sender, html_body, text_body, str(message.get("internalDate") or ""))
        record = contract_record(job)
        if record["intake_errors"]:
            rejected.append({"message_id": message_id, "errors": record["intake_errors"], "subject": subject})
            print(f"GMAIL_INTAKE_REJECTED: message={message_id} errors={record['intake_errors']}", file=sys.stderr)
            continue
        if intake.NON_JOB_RE.search(record.get("title", "")):
            print(f"GMAIL_NON_JOB_SKIPPED: title={record['title']}")
            continue
        try:
            intake.create_issue(record)
            paths.append(intake.persist(record))
            created += 1
            print(
                f"GMAIL_DISCOVERED: {record['company']} — {record['title']} — "
                f"{record['url'] or 'NO_ROLE_URL'} score={score} signals={','.join(signals)}"
            )
        except Exception as exc:
            print(f"ERROR creating Gmail intake issue {message_id}: {exc}", file=sys.stderr)

    with open("gmail_discovered_paths.txt", "w", encoding="utf-8") as handle:
        handle.write("\n".join(paths) + ("\n" if paths else ""))
    with open("gmail_intake_rejected.json", "w", encoding="utf-8") as handle:
        import json
        json.dump(rejected, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(
        f"Gmail discovery complete: candidate_messages={len(message_ids)}, "
        f"inspected={inspected}, github_noise_skipped={skipped_noise}, new_intakes={created}, rejected={len(rejected)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

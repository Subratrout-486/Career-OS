#!/usr/bin/env python3
"""Robust Gmail discovery wrapper for Career OS.

Uses the existing extraction/classification primitives but fixes the discovery
boundary: Gmail results are paginated and repository notification mail is
excluded before it can consume the discovery window.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys

from scripts import gmail_job_intake as intake

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
    # Gmail supports negative sender filtering; keep the explicit code-level
    # filter too because notification formats vary.
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

        job = intake.make_job(
            message_id,
            subject,
            sender,
            html_body,
            text_body,
            str(message.get("internalDate") or ""),
        )
        if intake.NON_JOB_RE.search(job.get("title", "")):
            print(f"GMAIL_NON_JOB_SKIPPED: title={job['title']}")
            continue
        try:
            intake.create_issue(job)
            paths.append(intake.persist(job))
            created += 1
            print(
                f"GMAIL_DISCOVERED: {job['company']} — {job['title']} — "
                f"{job['url'] or 'NO_ROLE_URL'} score={score} signals={','.join(signals)}"
            )
        except Exception as exc:
            print(f"ERROR creating Gmail intake issue {message_id}: {exc}", file=sys.stderr)

    with open("gmail_discovered_paths.txt", "w", encoding="utf-8") as handle:
        handle.write("\n".join(paths) + ("\n" if paths else ""))
    print(
        f"Gmail discovery complete: candidate_messages={len(message_ids)}, "
        f"inspected={inspected}, github_noise_skipped={skipped_noise}, new_intakes={created}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Discover fresh support/analyst jobs from public ATS feeds.

Uses employer-hosted public job-board APIs. New relevant jobs become
CAREER_OS_JOB_V1 issues and are also persisted as runner-local JSON payloads
so the same workflow can immediately run the Career OS pipeline. This avoids
relying on a workflow event emitted by GITHUB_TOKEN.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

REPO = os.environ.get("GITHUB_REPOSITORY", "Subratrout-486/Career-OS")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
MAX_NEW = int(os.environ.get("MAX_NEW_JOBS", "5"))
DAYS = int(os.environ.get("DISCOVERY_DAYS", "45"))
OUT_DIR = os.environ.get("DISCOVERY_OUT_DIR", "jobs/discovery_runtime")

GREENHOUSE = [("Zenoti", "zenoti"), ("HighRadius", "highradius"), ("GHX", "globalhealthcareexchangeinc")]
LEVER = [("Yuno", "yuno"), ("Highspot", "highspot"), ("JumpCloud", "jumpcloud"), ("Dun & Bradstreet", "dnb")]
TITLE_RE = re.compile(r"(product support|technical support|customer support|application support|production support|support engineer|support analyst|technical account|customer success|service desk|it support|operations analyst|business analyst|data analyst|research analyst|deal desk analyst|implementation analyst)", re.I)
INDIA_RE = re.compile(r"(india|hyderabad|telangana|bangalore|bengaluru|karnataka)", re.I)
REMOTE_RE = re.compile(r"(remote|work from home|wfh)", re.I)
EXCLUDE_RE = re.compile(r"(intern|internship|director|vice president|vp |principal|staff engineer|senior software engineer|software engineer|developer|sales executive|account executive|sales development|recruiter)", re.I)


def fetch_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "Career-OS-job-discovery/1.2"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))


def clean(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def iso_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def location_is_eligible(location: str, description: str) -> bool:
    if INDIA_RE.search(location):
        return True
    return bool(REMOTE_RE.search(location) and INDIA_RE.search(description))


def issue_exists(url: str) -> bool:
    q = urllib.parse.quote(f'repo:{REPO} "{url}"')
    req = urllib.request.Request(f"https://api.github.com/search/issues?q={q}&per_page=1", headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return int(json.loads(r.read().decode("utf-8")).get("total_count", 0)) > 0
    except Exception as exc:
        print(f"WARN duplicate check failed for {url}: {exc}", file=sys.stderr)
        return False


def make_job(company: str, title: str, location: str, url: str, description: str, source: str, published: str = "") -> dict[str, Any]:
    return {"title": title.strip(), "company": company.strip(), "location": location.strip() or "India", "url": url.strip(), "source": source, "captured_at": datetime.now(timezone.utc).isoformat(), "description": description.strip(), "published_at": published}


def greenhouse_jobs() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for company, board in GREENHOUSE:
        try:
            data = fetch_json(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true")
            for j in data.get("jobs", []):
                title = str(j.get("title") or "")
                loc = str((j.get("location") or {}).get("name") or "")
                desc = clean(str(j.get("content") or ""))
                url = str(j.get("absolute_url") or "")
                updated = str(j.get("updated_at") or "")
                if not url or not TITLE_RE.search(title) or EXCLUDE_RE.search(title) or not location_is_eligible(loc, desc):
                    continue
                dt = iso_date(updated)
                if dt and dt < datetime.now(timezone.utc) - timedelta(days=DAYS):
                    continue
                out.append(make_job(company, title, loc, url, desc, "Employer ATS — Greenhouse", updated))
        except Exception as exc:
            print(f"WARN Greenhouse {company}: {exc}", file=sys.stderr)
    return out


def lever_jobs() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for company, site in LEVER:
        try:
            data = fetch_json(f"https://api.lever.co/v0/postings/{site}?mode=json")
            for j in data if isinstance(data, list) else []:
                title = str(j.get("text") or "")
                categories = j.get("categories") or {}
                loc = str(categories.get("location") or ", ".join(categories.get("allLocations") or []))
                desc = clean(str(j.get("descriptionPlain") or j.get("description") or ""))
                url = str(j.get("hostedUrl") or j.get("applyUrl") or "")
                if not url or not TITLE_RE.search(title) or EXCLUDE_RE.search(title) or not location_is_eligible(loc, desc):
                    continue
                created = str(j.get("createdAt") or "")
                dt = datetime.fromtimestamp(int(created) / 1000, tz=timezone.utc) if created.isdigit() else None
                if dt and dt < datetime.now(timezone.utc) - timedelta(days=DAYS):
                    continue
                out.append(make_job(company, title, loc, url, desc, "Employer ATS — Lever", dt.isoformat() if dt else ""))
        except Exception as exc:
            print(f"WARN Lever {company}: {exc}", file=sys.stderr)
    return out


def create_issue(job: dict[str, Any]) -> None:
    marker = "<!-- CAREER_OS_JOB_V1 -->"
    payload = json.dumps(job, ensure_ascii=False, indent=2)
    body = f"{marker}\n\n## Automated Career OS discovery\n\nFound from a public employer ATS feed. Process through the normal Career OS safety pipeline. Do not submit unless the existing AUTO_APPLY contract is satisfied and actual submission can be verified.\n\n```json\n{payload}\n```\n"
    title = f"Career OS Job Intake — {job['company']} — {job['title']}"
    subprocess.run(["gh", "issue", "create", "--repo", REPO, "--title", title[:250], "--body", body], check=True, env={**os.environ, "GH_TOKEN": TOKEN})


def persist(job: dict[str, Any]) -> str:
    os.makedirs(OUT_DIR, exist_ok=True)
    digest = hashlib.sha256(job["url"].encode()).hexdigest()[:16]
    path = os.path.join(OUT_DIR, f"job-{digest}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(job, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return path


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    jobs = greenhouse_jobs() + lever_jobs()
    jobs.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    created = 0
    paths: list[str] = []
    for job in jobs:
        if created >= MAX_NEW:
            break
        if issue_exists(job["url"]):
            continue
        try:
            create_issue(job)
            paths.append(persist(job))
            created += 1
            print(f"DISCOVERED: {job['company']} — {job['title']} — {job['url']}")
        except subprocess.CalledProcessError as exc:
            print(f"ERROR creating intake issue for {job['url']}: {exc}", file=sys.stderr)
    with open("discovered_paths.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(paths) + ("\n" if paths else ""))
    print(f"Discovery complete: candidates={len(jobs)}, new_intakes={created}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

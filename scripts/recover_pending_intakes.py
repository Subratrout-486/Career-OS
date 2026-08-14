#!/usr/bin/env python3
"""Run the Career OS pipeline for intake issues that missed issue-event triggers."""
from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path

REPO = os.environ["GITHUB_REPOSITORY"]
TOKEN = os.environ["GITHUB_TOKEN"]
OUT = Path("jobs/recovery_runtime")
MAX = int(os.environ.get("MAX_RECOVERY_JOBS", "5"))


def api(path: str):
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json", "User-Agent": "Career-OS-recovery"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def main() -> int:
    owner, repo = REPO.split("/", 1)
    issues = api(f"/repos/{owner}/{repo}/issues?state=open&per_page=50")
    OUT.mkdir(parents=True, exist_ok=True)
    paths = []
    for issue in issues:
        if len(paths) >= MAX or "pull_request" in issue:
            continue
        body = issue.get("body") or ""
        if "CAREER_OS_JOB_V1" not in body or "```json" not in body:
            continue
        comments = api(f"/repos/{owner}/{repo}/issues/{issue['number']}/comments?per_page=50")
        if any("Career OS processing complete" in (c.get("body") or "") for c in comments):
            continue
        match = re.search(r"```json\s*(.*?)\s*```", body, re.S)
        if not match:
            continue
        data = json.loads(match.group(1))
        path = OUT / f"issue-{issue['number']}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        paths.append(str(path))
    Path("recovery_paths.txt").write_text("\n".join(paths) + ("\n" if paths else ""), encoding="utf-8")
    print(f"Pending intake recovery: {len(paths)}")
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

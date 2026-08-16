#!/usr/bin/env python3
"""Bridge durable Gmail intake issues into the Career OS pipeline."""
from __future__ import annotations
import json, os, re, urllib.request
from pathlib import Path
REPO=os.environ.get("GITHUB_REPOSITORY","Subratrout-486/Career-OS"); TOKEN=os.environ.get("GITHUB_TOKEN",""); MAX_JOBS=int(os.environ.get("MAX_GMAIL_PIPELINE_JOBS","10")); MARKER="CAREER_OS_PIPELINE_PROCESSED_V1"
NON_JOB_SUBJECT_RE=re.compile(r"(?i)\b(invitation|invites? you|want to connect|connection request|accepted your invitation|new message|message from|profile view|people you may know|someone viewed your profile|post|posts|comment)\b")
def github_json(path):
    req=urllib.request.Request(f"https://api.github.com/repos/{REPO}/{path}",headers={"Authorization":f"Bearer {TOKEN}","Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28"})
    with urllib.request.urlopen(req,timeout=30) as response: return json.loads(response.read().decode("utf-8"))
def extract_job(body):
    match=re.search(r"```json\s*(\{.*?\})\s*```",body,flags=re.S)
    if not match: return None
    try: value=json.loads(match.group(1))
    except json.JSONDecodeError: return None
    return value if isinstance(value,dict) and "source_message_id" in value else None
def main():
    if not TOKEN: raise RuntimeError("GITHUB_TOKEN is required")
    Path("jobs/email_runtime").mkdir(parents=True,exist_ok=True); Path("pipeline_results").mkdir(parents=True,exist_ok=True)
    paths=[]; issue_numbers=[]
    issues=github_json("issues?state=open&per_page=100&page=1")
    for issue in issues if isinstance(issues,list) else []:
        if len(paths)>=MAX_JOBS or issue.get("pull_request"): continue
        body=str(issue.get("body") or "")
        if "CAREER_OS_GMAIL_V1:" not in body or "CAREER_OS_JOB_V1" not in body: continue
        job=extract_job(body)
        if not job: continue
        subject=str(job.get("source_subject") or ""); title=str(job.get("title") or "")
        if NON_JOB_SUBJECT_RE.search(subject) or NON_JOB_SUBJECT_RE.search(title):
            print(f"GMAIL_NON_JOB_SKIPPED: issue={issue['number']} subject={subject}"); continue
        number=int(issue["number"]); comments=github_json(f"issues/{number}/comments?per_page=100&page=1")
        if any(MARKER in str(comment.get("body") or "") for comment in (comments or [])): continue
        path=Path("jobs/email_runtime")/f"issue-{number}.json"; path.write_text(json.dumps(job,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        paths.append(str(path)); issue_numbers.append(str(number)); print(f"GMAIL_PIPELINE_CANDIDATE: issue={number} {job.get('company')} — {job.get('title')}")
    Path("gmail_discovered_paths.txt").write_text("\n".join(paths)+("\n" if paths else ""),encoding="utf-8")
    Path("gmail_discovered_issue_numbers.txt").write_text("\n".join(issue_numbers)+("\n" if issue_numbers else ""),encoding="utf-8")
    print(f"Gmail issue bridge complete: candidates={len(paths)}")
    return 0
if __name__=="__main__": raise SystemExit(main())

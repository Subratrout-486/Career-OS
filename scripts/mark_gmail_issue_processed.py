#!/usr/bin/env python3
"""Mark a Gmail intake issue after downstream pipeline processing."""
from __future__ import annotations
import json, os, sys, urllib.request
REPO=os.environ.get("GITHUB_REPOSITORY","Subratrout-486/Career-OS"); TOKEN=os.environ.get("GITHUB_TOKEN",""); MARKER="CAREER_OS_PIPELINE_PROCESSED_V1"
def main():
    if len(sys.argv)!=2 or not TOKEN: raise SystemExit("usage: mark_gmail_issue_processed.py ISSUE_NUMBER")
    number=sys.argv[1]; body=f"<!-- {MARKER} -->\nCareer OS downstream pipeline processed this Gmail intake record. Reprocessing is blocked by this marker to prevent duplicate Notion/Application records."
    req=urllib.request.Request(f"https://api.github.com/repos/{REPO}/issues/{number}/comments",data=json.dumps({"body":body}).encode(),method="POST",headers={"Authorization":f"Bearer {TOKEN}","Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28","Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=30) as response:
        if response.status not in (200,201): raise RuntimeError(f"GitHub comment failed: HTTP {response.status}")
    print(f"GMAIL_PIPELINE_MARKED: issue={number}"); return 0
if __name__=="__main__": raise SystemExit(main())

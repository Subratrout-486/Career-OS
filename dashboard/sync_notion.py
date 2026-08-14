"""Build the browser-safe Career OS dashboard snapshot from Notion.

Secrets stay server-side in GitHub Actions. The generated JSON contains only
career/application tracking data intended for the dashboard; no credentials.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx

NOTION_VERSION = os.getenv("NOTION_VERSION", "2026-03-11")
TOKEN = os.environ["NOTION_TOKEN"]
BASE = "https://api.notion.com/v1"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Notion-Version": NOTION_VERSION, "Content-Type": "application/json"}


def plain(p: dict) -> str:
    if not isinstance(p, dict): return ""
    typ = p.get("type")
    value = p.get(typ, {}) if typ else {}
    if typ in {"title", "rich_text"}:
        return "".join(x.get("plain_text", x.get("text", {}).get("content", "")) for x in value).strip()
    if typ == "select": return str((value or {}).get("name") or "").strip()
    if typ == "status": return str((value or {}).get("name") or "").strip()
    if typ == "url": return str(value or "").strip()
    if typ == "number": return str(value) if value is not None else ""
    if typ == "checkbox": return "Yes" if value else "No"
    if typ == "date": return str((value or {}).get("start") or "").strip()
    return ""


def prop(props: dict, *names: str) -> str:
    lowered = {str(k).strip().lower(): v for k, v in props.items()}
    for name in names:
        p = lowered.get(name.lower())
        if p is not None:
            value = plain(p)
            if value: return value
    for key, p in props.items():
        kl = str(key).lower()
        if any(name.lower() in kl for name in names):
            value = plain(p)
            if value: return value
    return ""


def num(props: dict, *names: str) -> int | None:
    raw = prop(props, *names)
    try: return int(float(raw))
    except (TypeError, ValueError): return None


def title_of(ds: dict) -> str:
    title = ds.get("title") or []
    return "".join(x.get("plain_text", "") for x in title).strip()


def find_data_sources(client: httpx.Client) -> dict[str, str]:
    r = client.post(f"{BASE}/search", headers=HEADERS, json={"filter":{"property":"object","value":"data_source"},"page_size":100})
    r.raise_for_status()
    found = {}
    for item in r.json().get("results", []):
        name = title_of(item).lower()
        if "resume" in name and "library" in name: found["resumes"] = item["id"]
        elif "application" in name: found["applications"] = item["id"]
        elif name.strip() == "jobs" or name.startswith("jobs"): found["jobs"] = item["id"]
    found.setdefault("applications", os.getenv("NOTION_APPLICATIONS_DATA_SOURCE_ID", "a6925702-0d2a-4d68-919b-3401e1d8ff75"))
    found.setdefault("resumes", os.getenv("NOTION_RESUME_LIBRARY_DATA_SOURCE_ID", "3ac8bc1d-ce0e-8051-a553-000bb5f58abe"))
    return found


def query(client: httpx.Client, dsid: str) -> list[dict]:
    if not dsid: return []
    r = client.post(f"{BASE}/data_sources/{dsid}/query", headers=HEADERS, json={"page_size":100})
    if r.is_error:
        # Some workspaces still expose the legacy database endpoint.
        r = client.post(f"{BASE}/databases/{dsid}/query", headers=HEADERS, json={"page_size":100})
    r.raise_for_status()
    return r.json().get("results", [])


def build() -> dict:
    with httpx.Client(timeout=45) as client:
        sources = find_data_sources(client)
        jobs_raw = query(client, sources.get("jobs", ""))
        apps_raw = query(client, sources.get("applications", ""))
        resumes_raw = query(client, sources.get("resumes", ""))

    jobs=[]
    for p in jobs_raw:
        ps=p.get("properties",{})
        jobs.append({"company":prop(ps,"Company","Employer"),"title":prop(ps,"Role","Job Title","Job"),"location":prop(ps,"location","Location"),"fit":num(ps,"Fit","Fit Score"),"ats":num(ps,"ATS Match","ATS Score"),"status":prop(ps,"Status","Application Status"),"reason":prop(ps,"Next Action","Blocker","Notes"),"source":prop(ps,"Source"),"url":prop(ps,"Job Link","Job URL","URL")})
    apps=[]
    for p in apps_raw:
        ps=p.get("properties",{})
        apps.append({"company":prop(ps,"Company"),"title":prop(ps,"Job Title","Role","Application"),"status":prop(ps,"Application Status","Status"),"fit":num(ps,"Fit","Fit Score"),"ats":num(ps,"ATS Score","ATS Match"),"reason":prop(ps,"Next Action","Notes","Blocker")})
    resumes=[]
    for p in resumes_raw:
        ps=p.get("properties",{})
        resumes.append({"company":prop(ps,"Company","Source Job"),"title":prop(ps,"Target Role","Resume Name","Role"),"ats":num(ps,"ATS Score","ATS Match"),"truth":("PASS" if "unsupported" not in prop(ps,"Notes").lower() else "REVIEW"),"files":"PDF / DOCX" if prop(ps,"Resume File","Files") else "Record"})
    reviews=[]
    for a in apps:
        if a.get("status","").lower() in {"review","review_required","blocked"}:
            reviews.append({"company":a.get("company"),"title":a.get("title"),"reason":a.get("reason") or "Application requires review."})
    stats={"new_jobs":len(jobs),"strong_matches":sum(1 for j in jobs if (j.get("fit") or 0)>=75),"resumes":len(resumes),"auto_applied":sum(1 for a in apps if "submit" in a.get("status","").lower()),"needs_review":len(reviews)}
    return {"meta":{"last_sync":datetime.now(timezone.utc).isoformat(),"source":"notion"},"stats":stats,"jobs":jobs,"applications":apps,"resumes":resumes,"reviews":reviews}


if __name__ == "__main__":
    out=Path(__file__).with_name("data.json")
    data=build()
    out.write_text(json.dumps(data,ensure_ascii=False,separators=(",",":"))+"\n",encoding="utf-8")
    print(f"dashboard sync: {len(data['jobs'])} jobs, {len(data['applications'])} applications, {len(data['resumes'])} resumes")

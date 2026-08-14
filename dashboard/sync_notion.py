"""Build the browser-safe Career OS dashboard snapshot from Notion.

Secrets remain server-side in GitHub Actions.  The snapshot deliberately reports
only explicit durable records: unknown values stay ``NOT_RECORDED`` rather than
being inferred from missing fields or from a successful workflow invocation.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

NOTION_VERSION = os.getenv("NOTION_VERSION", "2026-03-11")
BASE = "https://api.notion.com/v1"
REVIEW_STATUSES = {"review", "review_required", "under review", "blocked"}


def headers() -> dict[str, str]:
    token = os.getenv("NOTION_TOKEN", "").strip()
    if not token:
        raise RuntimeError("NOTION_SYNC_BLOCKED: NOTION_TOKEN is not configured")
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def plain(property_value: dict[str, Any]) -> str:
    if not isinstance(property_value, dict):
        return ""
    value_type = property_value.get("type")
    value = property_value.get(value_type, {}) if value_type else {}
    if value_type in {"title", "rich_text"}:
        return "".join(
            item.get("plain_text", item.get("text", {}).get("content", ""))
            for item in value
        ).strip()
    if value_type in {"select", "status"}:
        return str((value or {}).get("name") or "").strip()
    if value_type == "url":
        return str(value or "").strip()
    if value_type == "number":
        return str(value) if value is not None else ""
    if value_type == "checkbox":
        return "Yes" if value else "No"
    if value_type == "date":
        return str((value or {}).get("start") or "").strip()
    return ""


def prop(properties: dict[str, Any], *names: str) -> str:
    lowered = {str(key).strip().lower(): value for key, value in properties.items()}
    for name in names:
        property_value = lowered.get(name.lower())
        if property_value is not None:
            value = plain(property_value)
            if value:
                return value
    for key, property_value in properties.items():
        key_lower = str(key).lower()
        if any(name.lower() in key_lower for name in names):
            value = plain(property_value)
            if value:
                return value
    return ""


def number(properties: dict[str, Any], *names: str) -> int | None:
    raw = prop(properties, *names)
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None


def artifact_label(properties: dict[str, Any], *names: str) -> str:
    lowered = {str(key).strip().lower(): value for key, value in properties.items()}
    for name in names:
        property_value = lowered.get(name.lower())
        if property_value is None:
            continue
        value_type = property_value.get("type") if isinstance(property_value, dict) else None
        if value_type == "files" and property_value.get("files"):
            return "File attached"
        if value_type == "url" and property_value.get("url"):
            return "URL reference"
        if plain(property_value):
            return "Artifact reference"
    return "Not recorded"


def title_of(data_source: dict[str, Any]) -> str:
    title = data_source.get("title") or []
    return "".join(item.get("plain_text", "") for item in title).strip()


def find_data_sources(client: httpx.Client, request_headers: dict[str, str]) -> dict[str, str]:
    response = client.post(
        f"{BASE}/search",
        headers=request_headers,
        json={"filter": {"property": "object", "value": "data_source"}, "page_size": 100},
    )
    response.raise_for_status()
    found: dict[str, str] = {}
    for item in response.json().get("results", []):
        name = title_of(item).lower()
        if "resume" in name and "library" in name:
            found["resumes"] = item["id"]
        elif "application" in name:
            found["applications"] = item["id"]
        elif name.strip() == "jobs" or name.startswith("jobs"):
            found["jobs"] = item["id"]
    found.setdefault("applications", os.getenv("NOTION_APPLICATIONS_DATA_SOURCE_ID", "a6925702-0d2a-4d68-919b-3401e1d8ff75"))
    found.setdefault("resumes", os.getenv("NOTION_RESUME_LIBRARY_DATA_SOURCE_ID", "3ac8bc1d-ce0e-8051-a553-000bb5f58abe"))
    found.setdefault("jobs", os.getenv("NOTION_JOBS_DATA_SOURCE_ID", ""))
    return found


def query(client: httpx.Client, request_headers: dict[str, str], data_source_id: str) -> list[dict[str, Any]]:
    if not data_source_id:
        return []
    response = client.post(
        f"{BASE}/data_sources/{data_source_id}/query",
        headers=request_headers,
        json={"page_size": 100},
    )
    if response.is_error:
        response = client.post(
            f"{BASE}/databases/{data_source_id}/query",
            headers=request_headers,
            json={"page_size": 100},
        )
    response.raise_for_status()
    return response.json().get("results", [])


def status(value: str) -> str:
    return value.strip() or "NOT_RECORDED"


def has_identity(row: dict[str, Any]) -> bool:
    return bool(str(row.get("company") or "").strip() or str(row.get("title") or "").strip())


def as_job(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "company": prop(properties, "Company", "Employer"),
        "title": prop(properties, "Role", "Job Title", "Job"),
        "location": prop(properties, "Location"),
        "fit": number(properties, "Fit", "Fit Score"),
        "ats": number(properties, "ATS Match", "ATS Score"),
        "status": status(prop(properties, "Status", "Application Status")),
        "reason": prop(properties, "Next Action", "Blocker", "Notes"),
        "source": prop(properties, "Source"),
        "url": prop(properties, "Job Link", "Job URL", "URL"),
    }


def as_application(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "company": prop(properties, "Company"),
        "title": prop(properties, "Job Title", "Role", "Application"),
        "status": status(prop(properties, "Application Status", "Status")),
        "fit": number(properties, "Fit", "Fit Score"),
        "ats": number(properties, "ATS Score", "ATS Match"),
        "reason": prop(properties, "Next Action", "Notes", "Blocker"),
    }


def as_resume(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "company": prop(properties, "Company", "Source Job"),
        "title": prop(properties, "Target Role", "Resume Name", "Role"),
        "ats": number(properties, "ATS Score", "ATS Match"),
        "truth": status(prop(properties, "Truth Guard Status", "Truth Guard", "Truth Status")),
        "files": artifact_label(properties, "Resume File", "Files", "Artifact"),
    }


def build_health(timestamp: str) -> dict[str, dict[str, str]]:
    execution_enabled = os.getenv("CAREER_OS_EXECUTION_ENABLED", "").strip().lower() == "true"
    return {
        "notion": {
            "state": "SYNCED",
            "detail": f"Notion data sources were queried successfully at {timestamp}.",
        },
        "github": {
            "state": "DASHBOARD_SYNC_COMPLETED",
            "detail": "This snapshot was produced by the completed dashboard-sync workflow.",
        },
        "pipeline": {
            "state": "NOT_CHECKED",
            "detail": "This snapshot does not infer pipeline health; inspect workflow evidence for the latest run.",
        },
        "manus": {
            "state": "EXECUTION_ENABLED_NOT_VERIFIED" if execution_enabled else "EXECUTION_DISABLED",
            "detail": (
                "Repository execution policy is enabled; browser connection and submission confirmation remain verified per candidate."
                if execution_enabled
                else "Repository execution policy is disabled; no browser task can be created from this snapshot."
            ),
        },
    }


def build() -> dict[str, Any]:
    request_headers = headers()
    with httpx.Client(timeout=45) as client:
        sources = find_data_sources(client, request_headers)
        jobs_raw = query(client, request_headers, sources.get("jobs", ""))
        applications_raw = query(client, request_headers, sources.get("applications", ""))
        resumes_raw = query(client, request_headers, sources.get("resumes", ""))

    jobs = [as_job(page.get("properties", {})) for page in jobs_raw]
    applications = [as_application(page.get("properties", {})) for page in applications_raw]
    resumes = [as_resume(page.get("properties", {})) for page in resumes_raw]
    jobs = [row for row in jobs if has_identity(row)]
    applications = [row for row in applications if has_identity(row)]
    resumes = [row for row in resumes if has_identity(row)]

    reviews = [
        {
            "company": application.get("company"),
            "title": application.get("title"),
            "reason": application.get("reason") or "Application requires review.",
        }
        for application in applications
        if application["status"].strip().lower() in REVIEW_STATUSES
    ]
    timestamp = datetime.now(timezone.utc).isoformat()
    stats = {
        "new_jobs": len(jobs),
        "strong_matches": sum(1 for job in jobs if (job.get("fit") or 0) >= 75),
        "resumes": len(resumes),
        "auto_applied": sum(1 for application in applications if application["status"].strip().lower() == "applied"),
        "needs_review": len(reviews),
    }
    return {
        "meta": {"last_sync": timestamp, "source": "notion", "status": "SYNCED"},
        "stats": stats,
        "jobs": jobs,
        "applications": applications,
        "resumes": resumes,
        "reviews": reviews,
        "health": build_health(timestamp),
    }


if __name__ == "__main__":
    output = Path(__file__).with_name("data.json")
    snapshot = build()
    output.write_text(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(
        "dashboard sync: "
        f"{len(snapshot['jobs'])} jobs, {len(snapshot['applications'])} applications, {len(snapshot['resumes'])} resumes"
    )

#!/usr/bin/env python3
"""Write a Career OS pipeline result into the canonical Notion Jobs database."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

import httpx

from career_os.readiness import apply_readiness_to_job

NOTION_VERSION = os.getenv("NOTION_VERSION", "2026-03-11")
DATA_SOURCE_ID = os.getenv("NOTION_JOBS_DATA_SOURCE_ID", "3ab8bc1d-ce0e-808c-93c3-000b43141dec").replace("collection://", "")
TOKEN = os.getenv("NOTION_TOKEN", "")


def rich(value: Any, limit: int = 1900) -> dict[str, Any]:
    text = str(value or "").strip()[:limit] or "None identified."
    return {"rich_text": [{"type": "text", "text": {"content": text}}]}


def title(value: Any) -> dict[str, Any]:
    return {"title": [{"type": "text", "text": {"content": str(value or "Untitled")[:1900]}}]}


def heading(text: str) -> dict[str, Any]:
    return {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [{"type": "text", "text": {"content": text[:1900]}}]}}


def paragraph(text: Any) -> dict[str, Any]:
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": str(text or "")[:1900]}}]}}


def bullets(values: list[Any], limit: int = 20) -> list[dict[str, Any]]:
    items = [str(x).strip() for x in values if str(x).strip()][:limit] if values else []
    if not items:
        items = ["None identified."]
    return [{"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": item[:1900]}}]}} for item in items]


def source_option(source: str) -> str:
    value = (source or "").lower()
    if "linkedin" in value: return "Linkedin"
    if "naukri" in value: return "Naukri"
    if "indeed" in value: return "Indeed"
    if "referral" in value: return "Referral"
    if "recruiter" in value: return "Recruiter"
    if any(x in value for x in ("greenhouse", "lever", "company", "ats")): return "Company Website"
    return "Other"


def fit_decision(fit: dict[str, Any]) -> str:
    value = str(fit.get("recommendation") or "REVIEW").upper()
    return "Apply" if value == "APPLY" else "Do Not Apply" if value == "SKIP" else "Apply - Verify"


def ready_status(result: dict[str, Any]) -> str:
    job = dict(result.get("job") or {})
    state = str(apply_readiness_to_job(job, result).get("ready_state") or "ERROR")
    return "Ready to Apply" if state == "READY_TO_APPLY" else state.replace("_", " ").title()


def ghost_risk(result: dict[str, Any]) -> str:
    value = str(((result.get("job_verification") or {}).get("ghost_job_risk") or {}).get("level") or "Medium").title()
    return value if value in {"Low", "Medium", "High", "Very High", "Confirmed Closed"} else "Medium"


def blocks(result: dict[str, Any]) -> list[dict[str, Any]]:
    job = result.get("job") or {}
    fit = result.get("fit") or {}
    jd = result.get("jd_analysis") or {}
    verification = result.get("job_verification") or {}
    ats = result.get("ats") or {}
    independent = result.get("independent_ats") or {}
    recruiter = result.get("recruiter_review") or {}
    resume = result.get("resume") or {}
    salary = result.get("salary") or {}
    design = result.get("design_qa") or {}
    mode = result.get("application_mode", "REVIEW_REQUIRED")
    out: list[dict[str, Any]] = [
        heading("Career OS — Full JD-to-Profile Fit Audit"),
        paragraph(f"Company: {job.get('company')} | Exact title: {job.get('title')} | Location: {job.get('location') or 'Not specified'}"),
        paragraph(f"Job URL: {job.get('url') or 'Not supplied'} | Source: {job.get('source') or 'Unknown'}"),
        paragraph(f"Fit score: {fit.get('fit_score', 'n/a')}/100 | Recommendation: {fit.get('recommendation', 'REVIEW')} | Band: {fit.get('band', 'n/a')}"),
        heading("1. Open-status / verification"),
        paragraph(f"Status: {verification.get('status', 'UNKNOWN')} | HTTP: {verification.get('http_status', 'n/a')} | Verification source: {verification.get('verification_source', 'n/a')}"),
        *bullets(verification.get("notes") or []),
        heading("2. Must-have requirements"), *bullets(jd.get("mandatory") or []),
        heading("3. Technical requirements / tools"), *bullets((jd.get("technical_skills") or []) + (jd.get("tools") or [])),
        heading("4. Experience / degree / location / shift constraints"),
        paragraph(f"Experience: {jd.get('experience_requirement') or verification.get('experience_requirement') or 'Not specified'}"),
        paragraph(f"Education: {'; '.join(jd.get('education') or []) or verification.get('education_requirement') or 'Not specified'}"),
        paragraph(f"Location/work model: {jd.get('location_work_model') or job.get('location') or 'Not specified'}"),
        *bullets(jd.get("screening_requirements") or []),
        heading("5. Key matched evidence"), *bullets((fit.get("must_have_matches") or []) + (fit.get("evidence") or [])),
        heading("6. Trainable gaps"), *bullets(fit.get("gaps") or []),
        heading("7. Must-have blockers"), *bullets(fit.get("blockers") or []),
        heading("8. Risks / confirmation requests"), *bullets((fit.get("risks") or []) + (fit.get("confirmation_requests") or [])),
        paragraph(f"Fit rationale: {fit.get('rationale') or 'Not provided.'}"),
        heading("9. Resume / Truth Guard"),
        paragraph(f"Resume generated: {'Yes' if resume else 'No'}"),
        *bullets(resume.get("changes") or []),
        paragraph("Unsupported claims / DO NOT ADD"), *bullets(resume.get("unsupported_claims") or []),
        heading("10. ATS audit"),
        paragraph(f"Primary ATS: {ats.get('score', 'n/a')}/100 | passed={ats.get('passed', 'n/a')} | method={ats.get('method', '')}"),
        paragraph("Matched keywords"), *bullets(ats.get("matched") or []),
        paragraph("Partial / missing / unsupported"), *bullets((ats.get("partial") or []) + (ats.get("missing") or []) + (ats.get("unsupported_do_not_add") or [])),
        paragraph(f"Independent ATS: {independent.get('score', 'n/a')}/100 | passed={independent.get('passed', 'n/a')}"),
        heading("11. Challenger / recruiter review"),
        paragraph(result.get("challenger_notes") or "Not run."),
        paragraph(f"Recruiter review: {recruiter.get('status', 'NOT_RUN')} | {recruiter.get('notes', '')}"),
        heading("12. Salary / application constraints"),
        paragraph(f"Salary: {salary.get('market_low_lpa', 'n/a')}–{salary.get('market_high_lpa', 'n/a')} LPA | recommended ask={salary.get('recommended_ask_lpa', 'n/a')} | confidence={salary.get('confidence', 'Low')}"),
        paragraph(f"Application mode: {mode} | {result.get('application_mode_reason', '')} | blockers: {'; '.join(result.get('application_mode_blockers') or []) or 'None'}"),
        paragraph(f"Design QA: {design.get('passed', 'n/a')} | Human approval remains required before browser submission."),
        heading("13. Final decision"),
        paragraph(f"{ready_status(result).upper()} — {fit.get('recommendation', 'REVIEW')}. Applied is never inferred; it requires verified submission evidence."),
    ]
    return out


def notes(result: dict[str, Any]) -> str:
    fit = result.get("fit") or {}
    jd = result.get("jd_analysis") or {}
    verification = result.get("job_verification") or {}
    return "\n".join([
        f"Full audit written: {datetime.now(timezone.utc).isoformat()}",
        f"Fit {fit.get('fit_score', 'n/a')}/100 | {fit.get('recommendation', 'REVIEW')} | {fit.get('band', 'n/a')}",
        f"Verification {verification.get('status', 'UNKNOWN')} | HTTP {verification.get('http_status', 'n/a')}",
        f"Experience: {jd.get('experience_requirement') or verification.get('experience_requirement') or 'Not specified'}",
        f"Education: {'; '.join(jd.get('education') or []) or verification.get('education_requirement') or 'Not specified'}",
        f"Work model: {jd.get('location_work_model') or 'Not specified'}",
        f"Ready gate: {ready_status(result)}",
    ])


def headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}", "Notion-Version": NOTION_VERSION, "Content-Type": "application/json"}


ACTIONABLE_SCHEMA: dict[str, dict[str, Any]] = {
    "JD": {"rich_text": {}},
    "JD Status": {"select": {"options": [{"name": "Complete"}, {"name": "Unavailable"}, {"name": "Pending"}]}},
    "Apply URL": {"url": {}},
    "Match Score": {"number": {"format": "percent"}},
    "Match Explanation": {"rich_text": {}},
    "Ready State": {"select": {"options": [{"name": "READY_TO_APPLY"}, {"name": "JD_PENDING"}, {"name": "MATCH_PENDING"}, {"name": "RESUME_PENDING"}, {"name": "APPLY_URL_PENDING"}, {"name": "ERROR"}]}},
    "Ingestion Status": {"rich_text": {}},
    "Recommended Resume": {"rich_text": {}},
}


async def ensure_actionable_schema(client: httpx.AsyncClient) -> None:
    response = await client.get(f"https://api.notion.com/v1/data_sources/{DATA_SOURCE_ID}", headers=headers())
    if response.is_error:
        raise RuntimeError(f"NOTION_SCHEMA_READ_FAILED {response.status_code}: {response.text[:1200]}")
    existing = response.json().get("properties") or {}
    missing = {name: spec for name, spec in ACTIONABLE_SCHEMA.items() if name not in existing}
    if not missing:
        return
    update = await client.patch(f"https://api.notion.com/v1/data_sources/{DATA_SOURCE_ID}", headers=headers(), json={"properties": missing})
    if update.is_error:
        raise RuntimeError(f"NOTION_SCHEMA_UPDATE_FAILED {update.status_code}: {update.text[:1200]}")


async def find_existing(client: httpx.AsyncClient, url: str) -> str | None:
    if not url:
        return None
    response = await client.post(
        f"https://api.notion.com/v1/data_sources/{DATA_SOURCE_ID}/query",
        headers=headers(),
        json={"filter": {"property": "Job Link", "url": {"equals": url}}, "page_size": 1},
    )
    if response.is_error:
        return None
    rows = response.json().get("results") or []
    return rows[0].get("id") if rows else None


async def sync(result: dict[str, Any]) -> str:
    if not TOKEN:
        raise RuntimeError("NOTION_TOKEN is not configured")
    job = result.get("job") or {}
    fit = result.get("fit") or {}
    verification = result.get("job_verification") or {}
    ats = result.get("ats") or {}
    resume = result.get("resume") or {}
    persisted_job = apply_readiness_to_job(dict(job), result)
    url = str(job.get("url") or "").strip()
    status = ready_status(result)
    notion_status = "Ready to Apply" if str(persisted_job.get("ready_state")) == "READY_TO_APPLY" else "Researching"
    jd_analysis = result.get("jd_analysis") or {}
    jd_text = str(job.get("jd_text") or job.get("description") or "").strip()
    jd_status = str(job.get("jd_status") or ("complete" if jd_text else "unavailable")).title()
    apply_url = str(job.get("apply_url") or job.get("application_url") or url).strip()
    recommended_resume = str(persisted_job.get("recommended_resume") or resume.get("title") or resume.get("pdf") or resume.get("docx") or ("Generated — see Resume Library" if resume else "Not generated"))
    properties: dict[str, Any] = {
        "Name": title(f"{job.get('company', 'Unknown')} — {job.get('title', 'Untitled')}"),
        "Company": rich(job.get("company")), "Role": rich(job.get("title")), "location": rich(job.get("location") or "Not specified"),
        "Fit Score": {"number": fit.get("fit_score")}, "Fit Decision": {"select": {"name": fit_decision(fit)}},
        "status": {"status": {"name": notion_status}}, "Priority": {"select": {"name": "High" if int(fit.get("fit_score") or 0) >= 80 else "Medium"}},
        "ATS Match": {"number": ats.get("score") if isinstance(ats.get("score"), int) else None},
        "Application Strategy": rich(f"{fit.get('recommendation', 'REVIEW')} | {result.get('application_mode', 'REVIEW_REQUIRED')} | {result.get('application_mode_reason', '')}"),
        "Ghost Job Risk": {"select": {"name": str(((verification.get('ghost_job_risk') or {}).get('level') or 'Medium')).title()}},
        "Ghost Job Evidence": rich("; ".join((verification.get("notes") or [])[:5]) or "See full audit."),
        "Resume Version": rich(recommended_resume), "Recommended Resume": rich(recommended_resume),
        "JD": rich(jd_text or "JD unavailable; retry enrichment."), "JD Status": {"select": {"name": jd_status}},
        "Apply URL": {"url": apply_url} if apply_url else {"url": None},
        "Match Score": {"number": fit.get("fit_score")}, "Match Explanation": rich(persisted_job.get("match_explanation") or fit.get("rationale") or "Not available"),
        "Ready State": {"select": {"name": str(persisted_job.get("ready_state") or "ERROR")}},
        "Ingestion Status": rich(job.get("ingestion_status") or "PROCESSED"),
        "source": {"select": {"name": source_option(str(job.get("source") or ""))}}, "Notes": rich(notes(result)),
    }
    if url: properties["Job Link"] = {"url": url}
    async with httpx.AsyncClient(timeout=60) as client:
        await ensure_actionable_schema(client)
        existing = await find_existing(client, url)
        if existing:
            response = await client.patch(f"https://api.notion.com/v1/pages/{existing}", headers=headers(), json={"properties": properties})
            if response.is_error:
                raise RuntimeError(f"NOTION_UPDATE_FAILED {response.status_code}: {response.text[:1200]}")
            page_id = existing
        else:
            response = await client.post("https://api.notion.com/v1/pages", headers=headers(), json={"parent": {"data_source_id": DATA_SOURCE_ID}, "properties": properties, "children": blocks(result)[:100]})
            if response.is_error:
                raise RuntimeError(f"NOTION_CREATE_FAILED {response.status_code}: {response.text[:1200]}")
            page_id = response.json()["id"]
        if existing:
            # Keep historical attachments/child pages intact; append the newest audit snapshot.
            response = await client.patch(f"https://api.notion.com/v1/blocks/{page_id}/children", headers=headers(), json={"children": [heading(f"Audit refresh — {datetime.now(timezone.utc).isoformat()}")] + blocks(result)[:99]})
            if response.is_error:
                raise RuntimeError(f"NOTION_AUDIT_APPEND_FAILED {response.status_code}: {response.text[:1200]}")
    return page_id


async def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: sync_job_to_notion.py pipeline-result.json")
    with open(sys.argv[1], encoding="utf-8") as handle:
        result = json.load(handle)
    page_id = await sync(result)
    print(f"NOTION_JOB_PAGE_ID={page_id}")
    print(f"NOTION_JOB_STATUS={ready_status(result)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(__import__("asyncio").run(main()))

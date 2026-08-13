"""Notion Applications tracking helper.

Career OS never marks Applied automatically. Records start as Ready to Apply.
Each record is populated with job-specific fit, ATS, evidence, risk and review
information so the Applications table is a usable execution queue rather than
a thin placeholder row.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

# Live Applications data source (verified 2026-08-13).
DEFAULT_APPLICATIONS_DS = "a6925702-0d2a-4d68-919b-3401e1d8ff75"

# Exact select option name in the live Notion Applications database.
APPLICATION_STATUS_READY = "Ready to Apply"


class ApplicationsTracker:
    def __init__(self):
        self.token = os.getenv("NOTION_TOKEN")
        self.data_source_id = (
            os.getenv("NOTION_APPLICATIONS_DATA_SOURCE_ID") or DEFAULT_APPLICATIONS_DS
        ).replace("collection://", "")
        self.version = os.getenv("NOTION_VERSION", "2026-03-11")

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": self.version,
            "Content-Type": "application/json",
        }

    @staticmethod
    def _list_text(values: Any, limit: int = 12) -> str:
        if not values:
            return "None identified."
        items = [str(value).strip() for value in values if str(value).strip()]
        if not items:
            return "None identified."
        return "\n".join(f"• {item}" for item in items[:limit])

    @staticmethod
    def _resume_summary(result: dict[str, Any]) -> str:
        resume = result.get("resume") or {}
        experience = resume.get("experience") or []
        lines: list[str] = []
        for item in experience:
            if not isinstance(item, dict):
                continue
            heading = " — ".join(
                str(x).strip()
                for x in (item.get("title"), item.get("company"), item.get("dates"))
                if str(x or "").strip()
            )
            if heading:
                lines.append(heading)
        return "; ".join(lines[:6]) or "No resume experience returned."

    @classmethod
    def _build_notes(cls, result: dict[str, Any]) -> str:
        job = result.get("job") or {}
        fit = result.get("fit") or {}
        ats = result.get("ats") or {}
        verification = result.get("job_verification") or {}
        jd = result.get("jd_analysis") or {}
        resume = result.get("resume") or {}
        challenger = str(result.get("challenger_notes") or "Not run.").strip()
        errors = result.get("errors") or []
        confirmation = fit.get("confirmation_requests") or []

        sections = [
            f"JOB: {job.get('title') or 'Unknown role'} at {job.get('company') or 'Unknown company'}",
            f"LOCATION: {job.get('location') or 'Not specified'}",
            f"JOB VERIFICATION: {verification.get('status') or 'UNKNOWN'} | HTTP {verification.get('http_status') or 'n/a'}",
            f"FIT: {fit.get('fit_score', 'n/a')}/100 | {fit.get('recommendation', 'n/a')} | Band {fit.get('band', 'n/a')}",
            f"FIT RATIONALE: {fit.get('rationale') or 'No rationale returned.'}",
            f"ATS: {ats.get('score', 'n/a')}/100 | matched={len(ats.get('matched') or [])} | partial={len(ats.get('partial') or [])} | missing={len(ats.get('missing') or [])}",
            f"JD REQUIREMENTS: {cls._list_text((jd.get('mandatory') or []) + (jd.get('technical_skills') or []) + (jd.get('tools') or []), 18)}",
            f"MATCHES: {cls._list_text(fit.get('must_have_matches') or [], 12)}",
            f"GAPS: {cls._list_text(fit.get('gaps') or [], 12)}",
            f"BLOCKERS: {cls._list_text(fit.get('blockers') or [], 12)}",
            f"RISKS: {cls._list_text(fit.get('risks') or [], 12)}",
            f"CONFIRMATION REQUESTS: {cls._list_text(confirmation, 10)}",
            f"ATS MISSING: {cls._list_text(ats.get('missing') or [], 15)}",
            f"ATS DO NOT ADD: {cls._list_text(ats.get('unsupported_do_not_add') or [], 15)}",
            f"RESUME TITLE: {resume.get('title') or 'Not generated'}",
            f"RESUME EXPERIENCE: {cls._resume_summary(result)}",
            f"RESUME SKILLS: {cls._list_text(resume.get('skills') or [], 20)}",
            f"RESUME CHANGES: {cls._list_text(resume.get('changes') or [], 12)}",
            f"UNSUPPORTED CLAIMS: {cls._list_text(resume.get('unsupported_claims') or [], 12)}",
            f"EVIDENCE TRACE: {cls._list_text(resume.get('evidence_trace') or [], 12)}",
            f"INDEPENDENT CHALLENGE: {challenger[:5000]}",
            f"GENERATED FILES: {', '.join(str(path) for path in (result.get('resume_files') or {}).values()) or 'None'}",
            f"NOTION REVIEW PAGE ID: {result.get('review_page_id') or 'Not created'}",
            f"RESUME LIBRARY PAGE ID: {result.get('resume_library_page_id') or 'Not created'}",
            f"PIPELINE STATUS: {result.get('review_status') or 'UNKNOWN'}",
            f"PIPELINE ERRORS: {cls._list_text(errors, 10)}",
        ]
        return "\n\n".join(sections)[:2000]

    async def create_review_record(self, result: dict[str, Any]) -> str | None:
        if not self.token or not self.data_source_id:
            return None
        job = result.get("job") or {}
        fit = result.get("fit") or {}
        title = f"{job.get('company', 'Company')} — {job.get('title', 'Role')}"
        notes = self._build_notes(result)
        properties: dict[str, Any] = {
            "Application": {
                "title": [{"type": "text", "text": {"content": title[:2000]}}]
            },
            "Company": {
                "rich_text": [
                    {"type": "text", "text": {"content": str(job.get("company") or "")[:2000]}}
                ]
            },
            "Job Title": {
                "rich_text": [
                    {"type": "text", "text": {"content": str(job.get("title") or "")[:2000]}}
                ]
            },
            "Location": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {"content": str(job.get("location") or "")[:2000]},
                    }
                ]
            },
            "Application Status": {"select": {"name": APPLICATION_STATUS_READY}},
            "Next Action": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": "REVIEW → open the generated resume → use the application URL/autofill → personally submit → then mark Applied."
                        },
                    }
                ]
            },
            "Notes": {
                "rich_text": [{"type": "text", "text": {"content": notes}}]
            },
        }
        url = (job.get("url") or "").strip()
        if url:
            properties["Job URL"] = {"url": url}

        payload = {
            "parent": {
                "type": "data_source_id",
                "data_source_id": self.data_source_id,
            },
            "properties": properties,
        }
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                "https://api.notion.com/v1/pages", headers=self.headers, json=payload
            )
            if response.is_error:
                raise RuntimeError(
                    f"Applications create failed ({response.status_code}): "
                    f"{response.text[:1500]}"
                )
            return response.json().get("id")

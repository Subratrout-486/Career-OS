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
    # Obsolete DS ID that must never be used (was a broken fallback / misconfigured var).
    _OBSOLETE_APPLICATIONS_DS = "a7755702-0d2a-4d68-919b-3401e1d8ff75"

    def __init__(self):
        self.token = os.getenv("NOTION_TOKEN")
        configured = (
            os.getenv("NOTION_APPLICATIONS_DATA_SOURCE_ID") or DEFAULT_APPLICATIONS_DS
        ).replace("collection://", "").strip()
        # Guard against a misconfigured GitHub Actions variable that still points
        # at the obsolete Applications data source.
        if not configured or configured == self._OBSOLETE_APPLICATIONS_DS:
            configured = DEFAULT_APPLICATIONS_DS
        self.data_source_id = configured
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

        sections = [
            f"Company: {job.get('company') or 'n/a'}",
            f"Role: {job.get('title') or 'n/a'}",
            f"Location: {job.get('location') or 'n/a'}",
            f"Source: {job.get('source') or 'n/a'}",
            f"Job verification: {verification.get('status') or 'n/a'} (active={verification.get('active')})",
            f"Fit recommendation: {fit.get('recommendation') or 'n/a'} | score={fit.get('fit_score')} | band={fit.get('band')}",
            f"Must-have matches:\n{cls._list_text(fit.get('must_have_matches'))}",
            f"Gaps:\n{cls._list_text(fit.get('gaps'))}",
            f"Risks:\n{cls._list_text(fit.get('risks'))}",
            f"Confirmation requests:\n{cls._list_text(fit.get('confirmation_requests'))}",
            f"ATS score: {ats.get('score', ats.get('ats_score')) if ats else 'n/a'}",
            f"Resume summary: {cls._resume_summary(result)}",
            f"JD mandatory count: {len((jd or {}).get('mandatory') or [])}",
            "Workflow gate: REVIEW → autofill → personally submit → mark Applied. Career OS never auto-submits.",
        ]
        notes = "\n\n".join(sections)
        return notes[:1900]

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

        resume_files = result.get("resume_files") or {}
        resume_library_page_id = result.get("resume_library_page_id")
        resume_refs = []
        if resume_library_page_id:
            resume_refs.append(
                f"Resume Library: https://www.notion.so/{str(resume_library_page_id).replace('-', '')}"
            )
        for key in ("pdf", "docx"):
            if resume_files.get(key):
                resume_refs.append(f"{key.upper()}: {resume_files[key]}")
        if resume_refs:
            properties["Resume Used"] = {
                "rich_text": [{"type": "text", "text": {"content": " | ".join(resume_refs)[:2000]}}]
            }

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

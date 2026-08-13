"""Notion Applications tracking helper.

Career OS never marks Applied automatically. Records start as Ready to Apply.
Question review may temporarily gate the record until required answers are approved.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_APPLICATIONS_DS = "a6925702-0d2a-4d68-919b-3401e1d8ff75"
APPLICATION_STATUS_READY = "Ready to Apply"
APPLICATION_STATUS_REVIEW = "Review"
# Backward-compatible alias used by existing callers; Notion's live option is "Review".
APPLICATION_STATUS_QUESTIONS = APPLICATION_STATUS_REVIEW


class ApplicationsTracker:
    _OBSOLETE_APPLICATIONS_DS = "a7755702-0d2a-4d68-919b-3401e1d8ff75"

    def __init__(self):
        self.token = os.getenv("NOTION_TOKEN")
        configured = (os.getenv("NOTION_APPLICATIONS_DATA_SOURCE_ID") or DEFAULT_APPLICATIONS_DS).replace("collection://", "").strip()
        if not configured or configured == self._OBSOLETE_APPLICATIONS_DS:
            configured = DEFAULT_APPLICATIONS_DS
        self.data_source_id = configured
        self.version = os.getenv("NOTION_VERSION", "2026-03-11")

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Notion-Version": self.version, "Content-Type": "application/json"}

    @staticmethod
    def readiness_status(*, questions_ready: bool, resume_review_approved: bool) -> str:
        return APPLICATION_STATUS_READY if questions_ready and resume_review_approved else APPLICATION_STATUS_REVIEW

    async def update_readiness(self, page_id: str, *, questions_ready: bool, resume_review_approved: bool) -> str:
        status = self.readiness_status(
            questions_ready=questions_ready,
            resume_review_approved=resume_review_approved,
        )
        if not self.token or not page_id:
            return status
        next_action = (
            "Use generated resume/autofill → personally submit → then mark Applied."
            if status == APPLICATION_STATUS_READY
            else "Review resume and required application questions; approve both before using autofill."
        )
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.patch(
                f"https://api.notion.com/v1/pages/{page_id}",
                headers=self.headers,
                json={"properties": {
                    "Application Status": {"select": {"name": status}},
                    "Next Action": {"rich_text": [{"type": "text", "text": {"content": next_action}}]},
                }},
            )
            if response.is_error:
                raise RuntimeError(f"Applications readiness update failed ({response.status_code}): {response.text[:1200]}")
        return status

    async def update_status(self, page_id: str, status: str) -> None:
        if not self.token or not page_id:
            return
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.patch(
                f"https://api.notion.com/v1/pages/{page_id}",
                headers=self.headers,
                json={"properties": {"Application Status": {"select": {"name": status}}}},
            )
            if response.is_error:
                raise RuntimeError(f"Applications status update failed ({response.status_code}): {response.text[:1200]}")

    @staticmethod
    def _list_text(values: Any, limit: int = 12) -> str:
        if not values:
            return "None identified."
        items = [str(value).strip() for value in values if str(value).strip()]
        return "\n".join(f"• {item}" for item in items[:limit]) or "None identified."

    @staticmethod
    def _resume_summary(result: dict[str, Any]) -> str:
        resume = result.get("resume") or {}
        lines: list[str] = []
        for item in resume.get("experience") or []:
            if not isinstance(item, dict):
                continue
            heading = " — ".join(str(x).strip() for x in (item.get("title"), item.get("company"), item.get("dates")) if str(x or "").strip())
            if heading:
                lines.append(heading)
        return "; ".join(lines[:6]) or "No resume experience returned."

    @classmethod
    def _build_notes(cls, result: dict[str, Any]) -> str:
        job = result.get("job") or {}
        fit = result.get("fit") or {}
        ats = result.get("ats") or {}
        verification = result.get("job_verification") or {}
        salary = result.get("salary") or {}
        sections = [
            f"Company: {job.get('company') or 'n/a'}",
            f"Role: {job.get('title') or 'n/a'}",
            f"Location: {job.get('location') or 'n/a'}",
            f"Job verification: {verification.get('status') or 'n/a'} (active={verification.get('active')})",
            f"Fit recommendation: {fit.get('recommendation') or 'n/a'} | score={fit.get('fit_score')} | band={fit.get('band')}",
            f"Must-have matches:\n{cls._list_text(fit.get('must_have_matches'))}",
            f"Gaps:\n{cls._list_text(fit.get('gaps'))}",
            f"Risks:\n{cls._list_text(fit.get('risks'))}",
            f"Confirmation requests:\n{cls._list_text(fit.get('confirmation_requests'))}",
            f"ATS score: {ats.get('score', ats.get('ats_score')) if ats else 'n/a'}",
            f"Salary intelligence (advisory draft): market={salary.get('market_low_lpa')}–{salary.get('market_high_lpa')} LPA | ask={salary.get('recommended_ask_lpa')} | stretch={salary.get('stretch_target_lpa')} | confidence={salary.get('confidence', 'n/a')} | researched={salary.get('researched_at', 'n/a')} | sources: " + "; ".join(f"{source.get('source_name', 'source')} ({source.get('verified_on', 'undated')}): {source.get('source_url', '')}" for source in salary.get('sources', []) if source.get('source_url')),
            f"Resume summary: {cls._resume_summary(result)}",
            f"Application Mode: {result.get('application_mode', 'REVIEW_REQUIRED')} | Reason: {result.get('application_mode_reason') or 'Human review required.'} | Blockers: {cls._list_text(result.get('application_mode_blockers'))}",
            "Workflow gate: review resume → review questions → approve both → autofill → personally submit → mark Applied. Career OS never auto-submits. Salary/CTC answers remain user-controlled.",
        ]
        return "\n\n".join(sections)[:1900]

    async def create_review_record(self, result: dict[str, Any]) -> str | None:
        if not self.token or not self.data_source_id:
            return None
        job = result.get("job") or {}
        title = f"{job.get('company', 'Company')} — {job.get('title', 'Role')}"
        properties: dict[str, Any] = {
            "Application": {"title": [{"type": "text", "text": {"content": title[:2000]}}]},
            "Company": {"rich_text": [{"type": "text", "text": {"content": str(job.get("company") or "")[:2000]}}]},
            "Job Title": {"rich_text": [{"type": "text", "text": {"content": str(job.get("title") or "")[:2000]}}]},
            "Location": {"rich_text": [{"type": "text", "text": {"content": str(job.get("location") or "")[:2000]}}]},
            "Application Status": {"select": {"name": APPLICATION_STATUS_REVIEW}},
            "Next Action": {"rich_text": [{"type": "text", "text": {"content": "REVIEW resume → answer required application questions → approve both → use generated resume/autofill → personally submit → then mark Applied."}}]},
            "Notes": {"rich_text": [{"type": "text", "text": {"content": self._build_notes(result)}}]},
        }
        url = (job.get("url") or "").strip()
        if url:
            properties["Job URL"] = {"url": url}
        resume_files = result.get("resume_files") or {}
        resume_library_page_id = result.get("resume_library_page_id")
        resume_refs = []
        if resume_library_page_id:
            resume_refs.append(f"Resume Library: https://www.notion.so/{str(resume_library_page_id).replace('-', '')}")
        for key in ("pdf", "docx"):
            if resume_files.get(key):
                resume_refs.append(f"{key.upper()}: {resume_files[key]}")
        if resume_refs:
            properties["Resume Used"] = {"rich_text": [{"type": "text", "text": {"content": " | ".join(resume_refs)[:2000]}}]}
        payload = {"parent": {"type": "data_source_id", "data_source_id": self.data_source_id}, "properties": properties}
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post("https://api.notion.com/v1/pages", headers=self.headers, json=payload)
            if response.is_error:
                raise RuntimeError(f"Applications create failed ({response.status_code}): {response.text[:1500]}")
            return response.json().get("id")

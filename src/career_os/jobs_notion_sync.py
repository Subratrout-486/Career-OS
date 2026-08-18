from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import httpx

from .readiness import apply_readiness_to_job


JOBS_DATA_SOURCE_ID = os.getenv(
    "NOTION_JOBS_DATA_SOURCE_ID",
    "3ab8bc1d-ce0e-808c-93c3-000b43141dec",
).replace("collection://", "")


class NotionJobsSync:
    """Persist every qualified Career OS pipeline result in the canonical Jobs DB.

    The Jobs row is the compact control-plane record; the page body contains the
    complete JD/profile audit so Notion has the same evidence users see in the
    Career OS daily shortlist.
    """

    def __init__(self) -> None:
        self.token = os.getenv("NOTION_TOKEN")
        self.data_source_id = JOBS_DATA_SOURCE_ID
        self.version = os.getenv("NOTION_VERSION", "2026-03-11")

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": self.version,
            "Content-Type": "application/json",
        }

    @staticmethod
    def _text(value: Any, limit: int = 2000) -> str:
        return str(value or "").strip()[:limit]

    @classmethod
    def _rich(cls, value: Any, limit: int = 2000) -> dict[str, Any]:
        text = cls._text(value, limit)
        return {"rich_text": [{"type": "text", "text": {"content": text or "None identified."}}]}

    @classmethod
    def _title(cls, value: Any) -> dict[str, Any]:
        return {"title": [{"type": "text", "text": {"content": cls._text(value, 2000)}}]}

    @staticmethod
    def _bullets(values: list[Any], limit: int = 25) -> list[dict[str, Any]]:
        items = [str(v).strip() for v in (values or []) if str(v).strip()]
        if not items:
            items = ["None identified."]
        return [
            {
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": item[:2000]}}]
                },
            }
            for item in items[:limit]
        ]

    @staticmethod
    def _heading(text: str) -> dict[str, Any]:
        return {
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": text[:2000]}}]
            },
        }

    @staticmethod
    def _paragraph(text: str) -> dict[str, Any]:
        return {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": str(text or "")[:2000]}}]
            },
        }

    @staticmethod
    def _source_option(source: str) -> str:
        source = (source or "").lower()
        if "linkedin" in source:
            return "Linkedin"
        if "naukri" in source:
            return "Naukri"
        if "indeed" in source:
            return "Indeed"
        if "referral" in source:
            return "Referral"
        if "recruiter" in source:
            return "Recruiter"
        if "company" in source or "greenhouse" in source or "lever" in source or "ats" in source:
            return "Company Website"
        return "Other"

    @staticmethod
    def _fit_decision(fit: dict[str, Any]) -> str:
        recommendation = str(fit.get("recommendation") or "REVIEW").upper()
        if recommendation == "APPLY":
            return "Apply"
        if recommendation == "SKIP":
            return "Do Not Apply"
        return "Apply - Verify"

    @staticmethod
    def _ready_status(result: dict[str, Any]) -> str:
        job = dict(result.get("job") or {})
        state = str(apply_readiness_to_job(job, result).get("ready_state") or "ERROR")
        return "Ready to Apply" if state == "READY_TO_APPLY" else state.replace("_", " ").title()

    @staticmethod
    def _ghost_risk(result: dict[str, Any]) -> str:
        risk = (result.get("job_verification") or {}).get("ghost_job_risk") or {}
        value = str(risk.get("level") or risk.get("risk") or "").title()
        return value if value in {"Low", "Medium", "High", "Very High", "Confirmed Closed"} else "Medium"

    @classmethod
    def _notes(cls, result: dict[str, Any]) -> str:
        job = result.get("job") or {}
        fit = result.get("fit") or {}
        jd = result.get("jd_analysis") or {}
        verification = result.get("job_verification") or {}
        ats = result.get("ats") or {}
        independent = result.get("independent_ats") or {}
        recruiter = result.get("recruiter_review") or {}
        design = result.get("design_qa") or {}
        salary = result.get("salary") or {}
        lines = [
            f"Career OS full audit | verified {datetime.now(timezone.utc).isoformat()}",
            f"Fit: {fit.get('fit_score', 'n/a')}/100 | Decision: {fit.get('recommendation', 'n/a')} | Band: {fit.get('band', 'n/a')}",
            f"Verification: {verification.get('status', 'UNKNOWN')} | HTTP: {verification.get('http_status', 'n/a')} | Source: {verification.get('verification_source', 'n/a')}",
            f"Work model/location: {jd.get('location_work_model') or job.get('location') or 'Not specified'}",
            f"Experience requirement: {jd.get('experience_requirement') or verification.get('experience_requirement') or 'Not specified'}",
            f"Education requirement: {'; '.join(jd.get('education') or []) or verification.get('education_requirement') or 'Not specified'}",
            f"Shift/screening constraints: {'; '.join(jd.get('screening_requirements') or []) or 'Not identified'}",
            f"Application mode: {result.get('application_mode', 'REVIEW_REQUIRED')} | {result.get('application_mode_reason', '')}",
            f"ATS: {ats.get('score', 'n/a')}/100 | passed={ats.get('passed', 'n/a')}",
            f"Independent ATS: {independent.get('score', 'n/a')}/100 | passed={independent.get('passed', 'n/a')}",
            f"Recruiter review: {recruiter.get('status', 'NOT_RUN')} | {recruiter.get('notes', '')}",
            f"Design QA: {design.get('passed', 'n/a')}",
            f"Salary intelligence: {salary.get('market_low_lpa', 'n/a')}–{salary.get('market_high_lpa', 'n/a')} LPA | ask={salary.get('recommended_ask_lpa', 'n/a')} | confidence={salary.get('confidence', 'Low')}",
            f"Pipeline status: {result.get('review_status', 'UNKNOWN')}",
        ]
        return "\n".join(lines)

    @classmethod
    def _audit_blocks(cls, result: dict[str, Any]) -> list[dict[str, Any]]:
        job = result.get("job") or {}
        fit = result.get("fit") or {}
        jd = result.get("jd_analysis") or {}
        verification = result.get("job_verification") or {}
        ats = result.get("ats") or {}
        independent = result.get("independent_ats") or {}
        recruiter = result.get("recruiter_review") or {}
        design = result.get("design_qa") or {}
        resume = result.get("resume") or {}
        salary = result.get("salary") or {}
        blocks: list[dict[str, Any]] = [
            cls._heading("Career OS — Full JD-to-Profile Fit Audit"),
            cls._paragraph(f"Company: {job.get('company')} | Exact title: {job.get('title')} | Location: {job.get('location') or 'Not specified'}"),
            cls._paragraph(f"Job link: {job.get('url') or 'Not supplied'} | Source: {job.get('source') or 'Unknown'}"),
            cls._paragraph(f"Fit score: {fit.get('fit_score', 'n/a')}/100 | Recommendation: {fit.get('recommendation', 'n/a')} | Band: {fit.get('band', 'n/a')}"),
            cls._heading("1. Job verification / open-status evidence"),
            cls._paragraph(f"Status: {verification.get('status', 'UNKNOWN')} | HTTP: {verification.get('http_status', 'n/a')} | Verification source: {verification.get('verification_source', 'n/a')}"),
            *cls._bullets(verification.get("notes") or []),
            cls._heading("2. Must-have requirements"),
            *cls._bullets(jd.get("mandatory") or []),
            cls._heading("3. Technical requirements / tools"),
            *cls._bullets((jd.get("technical_skills") or []) + (jd.get("tools") or [])),
            cls._heading("4. Experience / degree / location / shift constraints"),
            cls._paragraph(f"Experience: {jd.get('experience_requirement') or verification.get('experience_requirement') or 'Not specified'}"),
            cls._paragraph(f"Education: {'; '.join(jd.get('education') or []) or verification.get('education_requirement') or 'Not specified'}"),
            cls._paragraph(f"Location/work model: {jd.get('location_work_model') or job.get('location') or 'Not specified'}"),
            *cls._bullets(jd.get("screening_requirements") or []),
            cls._heading("5. Matched evidence"),
            *cls._bullets((fit.get("must_have_matches") or []) + (fit.get("evidence") or [])),
            cls._heading("6. Trainable gaps"),
            *cls._bullets(fit.get("gaps") or []),
            cls._heading("7. Must-have blockers"),
            *cls._bullets(fit.get("blockers") or []),
            cls._heading("8. Risks / confirmation requests"),
            *cls._bullets((fit.get("risks") or []) + (fit.get("confirmation_requests") or [])),
            cls._paragraph(f"Rationale: {fit.get('rationale') or 'Not provided.'}"),
            cls._heading("9. Resume / Truth Guard"),
            cls._paragraph(f"Resume: {'Generated' if resume else 'Not generated'}"),
            *cls._bullets(resume.get("changes") or []),
            cls._paragraph("Unsupported claims / DO NOT ADD"),
            *cls._bullets(resume.get("unsupported_claims") or []),
            cls._heading("10. ATS audit"),
            cls._paragraph(f"Primary ATS: {ats.get('score', 'n/a')}/100 | passed={ats.get('passed', 'n/a')} | {ats.get('method', '')}"),
            *cls._bullets(ats.get("matched") or []),
            cls._paragraph("Partial / missing / unsupported"),
            *cls._bullets((ats.get("partial") or []) + (ats.get("missing") or []) + (ats.get("unsupported_do_not_add") or [])),
            cls._paragraph(f"Independent ATS: {independent.get('score', 'n/a')}/100 | passed={independent.get('passed', 'n/a')}"),
            cls._heading("11. Challenger / recruiter review"),
            cls._paragraph(result.get("challenger_notes") or "Not run."),
            cls._paragraph(f"Recruiter review: {recruiter.get('status', 'NOT_RUN')} | {recruiter.get('notes', '')}"),
            cls._heading("12. Salary / application constraints"),
            cls._paragraph(f"Salary: {salary.get('market_low_lpa', 'n/a')}–{salary.get('market_high_lpa', 'n/a')} LPA | ask={salary.get('recommended_ask_lpa', 'n/a')} | confidence={salary.get('confidence', 'Low')}"),
            cls._paragraph(f"Application mode: {result.get('application_mode', 'REVIEW_REQUIRED')} | Blockers: {'; '.join(result.get('application_mode_blockers') or []) or 'None reported.'}"),
            cls._paragraph(f"Design QA: {design.get('passed', 'n/a')} | Human approval remains required before any browser submission."),
            cls._heading("13. Final Career OS decision"),
            cls._paragraph(f"{cls._ready_status(result).upper()} — {fit.get('recommendation', 'REVIEW')}. Applied status is never inferred; it requires verified submission evidence."),
        ]
        return blocks

    async def _find_existing(self, job_url: str) -> str | None:
        if not self.token or not job_url:
            return None
        payload = {
            "filter": {"property": "Job Link", "url": {"equals": job_url}},
            "page_size": 1,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"https://api.notion.com/v1/data_sources/{self.data_source_id}/query",
                headers=self.headers,
                json=payload,
            )
            if response.is_error:
                return None
            results = response.json().get("results") or []
            return results[0].get("id") if results else None

    async def sync(self, result: dict[str, Any]) -> str | None:
        if not self.token or not self.data_source_id:
            return None
        job = result.get("job") or {}
        fit = result.get("fit") or {}
        verification = result.get("job_verification") or {}
        resume = result.get("resume") or {}
        ats = result.get("ats") or {}
        persisted_job = apply_readiness_to_job(dict(job), result)
        existing_id = await self._find_existing(str(job.get("url") or job.get("source_url") or ""))
        status = self._ready_status(result)
        properties: dict[str, Any] = {
            "Name": self._title(f"{job.get('company', 'Unknown')} — {job.get('title', 'Untitled')}"),
            "Company": self._rich(job.get("company")),
            "Role": self._rich(job.get("title")),
            "location": self._rich(job.get("location") or "Not specified"),
            "Fit Score": {"number": fit.get("fit_score")},
            "Fit Decision": {"select": {"name": self._fit_decision(fit)}},
            "status": {"status": {"name": status}},
            "Priority": {"select": {"name": "High" if int(fit.get("fit_score") or 0) >= 80 else "Medium"}},
            "ATS Match": {"number": ats.get("score") if isinstance(ats.get("score"), int) else None},
            "Application Strategy": self._rich(
                f"{fit.get('recommendation', 'REVIEW')} | {result.get('application_mode', 'REVIEW_REQUIRED')} | {result.get('application_mode_reason', '')}"
            ),
            "Ghost Job Risk": {"select": {"name": self._ghost_risk(result)}},
            "Ghost Job Evidence": self._rich("; ".join((verification.get("notes") or [])[:5]) or "Verification evidence stored in full audit below."),
            "Resume Version": self._rich(persisted_job.get("recommended_resume") or ("Generated — see Resume Library" if resume else "Not generated")),
            "JD": self._rich(job.get("jd_text") or job.get("description") or "JD unavailable; retry enrichment."),
            "JD Status": {"select": {"name": str(job.get("jd_status") or "unavailable").title()}},
            "Apply URL": {"url": str(job.get("apply_url") or job.get("url") or "")} if str(job.get("apply_url") or job.get("url") or "") else {"url": None},
            "Match Explanation": self._rich(persisted_job.get("match_explanation") or fit.get("rationale") or "Not available"),
            "Ready State": {"select": {"name": str(persisted_job.get("ready_state") or "ERROR")}},
            "Ingestion Status": self._rich(job.get("ingestion_status") or "PROCESSED"),
            "Salary": self._rich(str((result.get("salary") or {}).get("recommended_ask_lpa") or "Not sourced")),
            "source": {"select": {"name": self._source_option(str(job.get("source") or ""))}},
            "Notes": self._rich(cls_notes := self._notes(result), 1900),
        }
        url = str(job.get("url") or "").strip()
        if url:
            properties["Job Link"] = {"url": url}
        if verification.get("status") in {"ACTIVE", "INACTIVE"}:
            properties["date:Last Job Verification:start"] = verification.get("resolved_at") or datetime.now(timezone.utc).isoformat()
            properties["date:Last Job Verification:is_datetime"] = 1
        payload = {"parent": {"data_source_id": self.data_source_id}, "properties": properties}
        blocks = self._audit_blocks(result)
        async with httpx.AsyncClient(timeout=60) as client:
            if existing_id:
                response = await client.patch(
                    f"https://api.notion.com/v1/pages/{existing_id}",
                    headers=self.headers,
                    json={"properties": properties},
                )
                response.raise_for_status()
                page_id = existing_id
                # Replace is deliberately avoided: existing child pages/attachments are preserved.
                response = await client.patch(
                    f"https://api.notion.com/v1/blocks/{page_id}/children",
                    headers=self.headers,
                    json={"children": blocks[:100]},
                )
                if response.is_error:
                    # A stale audit is safer than failing the entire job pipeline.
                    return page_id
            else:
                response = await client.post(
                    "https://api.notion.com/v1/pages",
                    headers=self.headers,
                    json={**payload, "children": blocks[:100]},
                )
                response.raise_for_status()
                page_id = response.json().get("id")
        if page_id and len(blocks) > 100:
            async with httpx.AsyncClient(timeout=60) as client:
                for start in range(100, len(blocks), 100):
                    response = await client.patch(
                        f"https://api.notion.com/v1/blocks/{page_id}/children",
                        headers=self.headers,
                        json={"children": blocks[start:start + 100]},
                    )
                    response.raise_for_status()
        return page_id

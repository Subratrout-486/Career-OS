import mimetypes
import os
from pathlib import Path

import httpx


# Order matters: specific role families must be checked before generic substrings.
TARGET_ROLE_MAP = {
    "product support": "Product Support Engineer",
    "application support": "Application Support Engineer",
    "production support": "Production Support Engineer",
    "technical support": "Technical Support Analyst",
    "support analyst": "Support Analyst (IT)",
    "support engineer": "Technical Support Engineer",
    "cloud": "Cloud Support Engineer",
    "operations": "Operations Support Analyst",
    "incident": "Incident Management Analyst",
    "data analyst": "Data Analyst",
    "research analyst": "Research Analyst",
    "business analyst": "Business Analyst",
}


class NotionReviewQueue:
    """Create the human-review page and persist the generated resume files in Notion."""

    def __init__(self):
        self.token = os.getenv("NOTION_TOKEN")
        self.parent_page_id = os.getenv("NOTION_REVIEW_QUEUE_PAGE_ID")
        self.resume_library_data_source_id = os.getenv(
            "NOTION_RESUME_LIBRARY_DATA_SOURCE_ID",
            "3ac8bc1d-ce0e-8051-a553-000bb5f58abe",
        ).replace("collection://", "")
        self.version = os.getenv("NOTION_VERSION", "2026-03-11")

    @property
    def headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": self.version,
            "Content-Type": "application/json",
        }

    async def _upload_file(self, path: str) -> str:
        file_path = Path(path)
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        async with httpx.AsyncClient(timeout=60) as client:
            create = await client.post(
                "https://api.notion.com/v1/file_uploads",
                headers=self.headers,
                json={
                    "mode": "single_part",
                    "filename": file_path.name,
                    "content_type": content_type,
                },
            )
            create.raise_for_status()
            upload_id = create.json()["id"]
            with file_path.open("rb") as handle:
                response = await client.post(
                    f"https://api.notion.com/v1/file_uploads/{upload_id}/send",
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Notion-Version": self.version,
                    },
                    files={"file": (file_path.name, handle, content_type)},
                )
            response.raise_for_status()
            result = response.json()
            if result.get("status") not in {None, "uploaded"}:
                raise RuntimeError(f"Notion file upload did not complete: {result}")
            return upload_id

    @staticmethod
    def _target_role(job_title: str) -> str:
        title = job_title.lower()
        for key, value in TARGET_ROLE_MAP.items():
            if key in title:
                return value
        return "Other"

    @staticmethod
    def _ats_score(fit: dict, resume: dict) -> int:
        keywords = [str(x).lower() for x in fit.get("keywords", []) if str(x).strip()]
        if not keywords:
            return int(fit.get("fit_score", 0))
        resume_text = " ".join(
            [
                str(resume.get("summary", "")),
                " ".join(str(x) for x in resume.get("skills", [])),
                str(resume.get("experience", [])),
                str(resume.get("education", [])),
            ]
        ).lower()
        return round(
            (sum(1 for keyword in keywords if keyword in resume_text) / len(keywords)) * 100
        )

    async def _create_resume_library_page(self, result: dict, upload_ids: list[tuple[str, str]]) -> str | None:
        if not self.resume_library_data_source_id:
            return None
        job = result["job"]
        fit = result["fit"]
        resume = result["resume"]
        files = [
            {"type": "file_upload", "file_upload": {"id": upload_id}, "name": filename}
            for filename, upload_id in upload_ids
        ]
        version = "CareerOS-" + __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).strftime("%Y%m%d-%H%M%S")
        notes = (
            f"Source job: {job.get('title')} at {job.get('company')}. "
            f"Generated after fit analysis and independent challenge. "
            f"Unsupported claims flagged by agent: {len(resume.get('unsupported_claims', []))}."
        )
        properties = {
            "Resume Name": {"title": [{"type": "text", "text": {"content": f"{job['company']} — {job['title']} — JD Tailored Resume"}}]},
            "Target Role": {"multi_select": [{"name": self._target_role(job["title"])}]},
            "Status ": {"select": {"name": "Active"}},
            "Version": {"rich_text": [{"type": "text", "text": {"content": version}}]},
            "ATS Score": {"number": self._ats_score(fit, resume)},
            "Resume File": {"files": files},
            "Notes": {"rich_text": [{"type": "text", "text": {"content": notes[:2000]}}]},
        }
        source_url = (job.get("url") or "").strip()
        if source_url:
            properties["Source Job"] = {"url": source_url}
        payload = {"parent": {"type": "data_source_id", "data_source_id": self.resume_library_data_source_id}, "properties": properties}
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post("https://api.notion.com/v1/pages", headers=self.headers, json=payload)
            if response.is_error:
                raise RuntimeError(f"Notion Resume Library create failed ({response.status_code}): {response.text[:2000]}")
            return response.json().get("id")

    async def create_review_page(self, result: dict) -> tuple[str | None, str | None]:
        if not self.token or not self.parent_page_id:
            return None, None
        job = result["job"]
        fit = result["fit"]
        resume = result.get("resume")
        title = f"{job['company']} — {job['title']} — REVIEW"
        upload_ids = []
        for _, path in (result.get("resume_files") or {}).items():
            if Path(path).exists():
                upload_ids.append((Path(path).name, await self._upload_file(path)))
        library_page_id = None
        if resume and upload_ids:
            library_page_id = await self._create_resume_library_page(result, upload_ids)

        confirmation_requests = fit.get("confirmation_requests", [])
        blocks = [
            self._heading("1. Job"),
            self._paragraph(f"Source: {job.get('source') or 'Unknown'} | Location: {job.get('location') or 'Not specified'}"),
            self._paragraph(job.get("url") or "No URL supplied"),
            self._heading("2. Fit decision"),
            self._paragraph(f"Score: {fit['fit_score']} | Recommendation: {fit['recommendation']}"),
            self._paragraph(f"Rationale: {fit['rationale']}"),
            self._heading("3. Evidence / matches"),
            *self._bullets(fit.get("must_have_matches", []) + fit.get("evidence", [])),
            self._heading("4. Gaps / blockers / risks"),
            *self._bullets(fit.get("gaps", []) + fit.get("blockers", []) + fit.get("risks", [])),
        ]
        if confirmation_requests:
            blocks += [
                self._heading("USER CONFIRMATION REQUIRED — PROFESSIONAL TOOL USE"),
                self._paragraph("Answer these before the unconfirmed tool/skill is added to a resume. Confirmed answers become reusable evidence."),
                *self._bullets(confirmation_requests),
            ]
        if resume:
            blocks += [
                self._heading("5. JD-specific resume"),
                self._paragraph(f"Resume title: {resume['title']}"),
                self._paragraph(f"Files generated: {', '.join(Path(p).name for p in (result.get('resume_files') or {}).values()) or 'None'}"),
                self._heading("Professional summary"), self._paragraph(resume["summary"]),
                self._heading("Skills"), *self._bullets(resume.get("skills", [])),
                self._heading("Experience"), *self._experience_blocks(resume.get("experience", [])),
                self._heading("Education"), *self._bullets(resume.get("education", [])),
                self._heading("What changed for this JD"), *self._bullets(resume.get("changes", [])),
                self._heading("Evidence trace"), *self._bullets(resume.get("evidence_trace", [])),
                self._heading("Unsupported claims"), *self._bullets(resume.get("unsupported_claims", [])),
            ]
        blocks += [
            self._heading("6. Independent challenge — Grok"), self._paragraph(result.get("challenger_notes") or "No challenge output."),
            self._heading("7. Human approval gate"), self._paragraph("STATUS: READY_FOR_REVIEW — Review the JD, fit, challenger notes and resume before applying. Career OS never submits the application automatically."),
        ]
        for filename, upload_id in upload_ids:
            blocks.append({"object":"block","type":"file","file":{"type":"file_upload","file_upload":{"id":upload_id},"caption":[{"type":"text","text":{"content":filename}}]}})
        payload = {"parent":{"type":"page_id","page_id":self.parent_page_id},"properties":{"title":{"title":[{"type":"text","text":{"content":title}}]}},"children":blocks[:100]}
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post("https://api.notion.com/v1/pages", headers=self.headers, json=payload)
            if response.is_error:
                raise RuntimeError(f"Notion review page create failed ({response.status_code}): {response.text[:2000]}")
            page_id = response.json().get("id")
        if page_id and len(blocks) > 100:
            for start in range(100, len(blocks), 100):
                async with httpx.AsyncClient(timeout=60) as client:
                    response = await client.patch(f"https://api.notion.com/v1/blocks/{page_id}/children", headers=self.headers, json={"children":blocks[start:start+100]})
                    response.raise_for_status()
        return page_id, library_page_id

    @staticmethod
    def _heading(text: str) -> dict:
        return {"object":"block","type":"heading_2","heading_2":{"rich_text":[{"type":"text","text":{"content":text[:2000]}}]}}

    @staticmethod
    def _paragraph(text: str) -> dict:
        return {"object":"block","type":"paragraph","paragraph":{"rich_text":[{"type":"text","text":{"content":str(text)[:2000]}}]}}

    @staticmethod
    def _bullets(items: list) -> list[dict]:
        items=[str(x) for x in items if str(x).strip()]
        return [{"object":"block","type":"bulleted_list_item","bulleted_list_item":{"rich_text":[{"type":"text","text":{"content":x[:2000]}}]}} for x in items] or [NotionReviewQueue._paragraph("None identified.")]

    @staticmethod
    def _experience_blocks(experience: list[dict]) -> list[dict]:
        blocks=[]
        for item in experience:
            if isinstance(item,dict):
                title=item.get("title") or item.get("role") or "Experience"
                company=item.get("company") or ""
                dates=item.get("dates") or item.get("date") or ""
                blocks.append(NotionReviewQueue._paragraph(" — ".join(x for x in [title,company,dates] if x)))
                blocks.extend(NotionReviewQueue._bullets(item.get("bullets") or item.get("responsibilities") or []))
            else:
                blocks.append(NotionReviewQueue._paragraph(str(item)))
        return blocks or [NotionReviewQueue._paragraph("No experience returned.")]

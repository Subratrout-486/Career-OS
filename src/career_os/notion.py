import os
import httpx

class NotionReviewQueue:
    """Creates a human-review page under a configured Notion parent page.

    This intentionally uses a parent page instead of assuming the user's database
    property schema. Once the exact Review Queue database/data-source ID and schema
    are supplied, this can be upgraded to database records without changing the agents.
    """
    def __init__(self):
        self.token = os.getenv("NOTION_TOKEN")
        self.parent_page_id = os.getenv("NOTION_REVIEW_QUEUE_PAGE_ID")
        self.version = os.getenv("NOTION_VERSION", "2022-06-28")

    async def create_review_page(self, result: dict) -> str | None:
        if not self.token or not self.parent_page_id:
            return None
        job = result["job"]
        fit = result["fit"]
        resume = result.get("resume")
        title = f"{job['company']} — {job['title']} — REVIEW"
        blocks = [
            self._heading("1. Job"),
            self._paragraph(f"Source: {job.get('source') or 'Unknown'} | Location: {job.get('location') or 'Not specified'}"),
            self._paragraph(job.get("url") or "No URL supplied"),
            self._heading("2. Fit decision"),
            self._paragraph(f"Score: {fit['fit_score']} | Recommendation: {fit['recommendation']}"),
            self._paragraph(f"Rationale: {fit['rationale']}"),
            self._heading("3. Risks / blockers"),
            self._bullets(fit.get("blockers", []) + fit.get("risks", [])),
        ]
        if resume:
            blocks += [self._heading("4. Tailored resume"), self._paragraph(resume["summary"]), self._bullets(resume.get("changes", []))]
        blocks += [self._heading("5. Human approval"), self._paragraph("STATUS: READY_FOR_REVIEW — Do not submit until the user approves the job and resume.")]
        payload = {"parent": {"page_id": self.parent_page_id}, "properties": {"title": {"title": [{"text": {"content": title}}]}}, "children": blocks}
        headers = {"Authorization": f"Bearer {self.token}", "Notion-Version": self.version, "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post("https://api.notion.com/v1/pages", headers=headers, json=payload)
            r.raise_for_status()
            return r.json().get("id")

    @staticmethod
    def _heading(text):
        return {"object":"block","type":"heading_2","heading_2":{"rich_text":[{"type":"text","text":{"content":text}}]}}
    @staticmethod
    def _paragraph(text):
        return {"object":"block","type":"paragraph","paragraph":{"rich_text":[{"type":"text","text":{"content":text[:2000]}}]}}
    @staticmethod
    def _bullets(items):
        return [{"object":"block","type":"bulleted_list_item","bulleted_list_item":{"rich_text":[{"type":"text","text":{"content":str(x)[:2000]}}]}} for x in items] or [NotionReviewQueue._paragraph("None identified.")]

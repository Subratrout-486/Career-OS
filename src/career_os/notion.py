import os
import httpx


class NotionReviewQueue:
    """Create a human-review page under the configured Notion parent page."""

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
            self._paragraph(
                f"Source: {job.get('source') or 'Unknown'} | "
                f"Location: {job.get('location') or 'Not specified'}"
            ),
            self._paragraph(job.get("url") or "No URL supplied"),
            self._heading("2. Fit decision"),
            self._paragraph(
                f"Score: {fit['fit_score']} | Recommendation: {fit['recommendation']}"
            ),
            self._paragraph(f"Rationale: {fit['rationale']}"),
            self._heading("3. Evidence / matches"),
            *self._bullets(fit.get("must_have_matches", []) + fit.get("evidence", [])),
            self._heading("4. Gaps / blockers / risks"),
            *self._bullets(
                fit.get("gaps", []) + fit.get("blockers", []) + fit.get("risks", [])
            ),
        ]

        if resume:
            blocks += [
                self._heading("5. JD-specific resume"),
                self._paragraph(f"Resume title: {resume['title']}"),
                self._heading("Professional summary"),
                self._paragraph(resume["summary"]),
                self._heading("Skills"),
                *self._bullets(resume.get("skills", [])),
                self._heading("Experience"),
                *self._experience_blocks(resume.get("experience", [])),
                self._heading("Education"),
                *self._bullets(resume.get("education", [])),
                self._heading("What changed for this JD"),
                *self._bullets(resume.get("changes", [])),
                self._heading("Unsupported claims"),
                *self._bullets(resume.get("unsupported_claims", [])),
            ]

        blocks += [
            self._heading("6. Independent challenge — Grok"),
            self._paragraph(result.get("challenger_notes") or "No challenge output."),
            self._heading("7. Human approval gate"),
            self._paragraph(
                "STATUS: READY_FOR_REVIEW — Review the JD, fit, challenger notes and "
                "resume before applying. Career OS never submits the application automatically."
            ),
        ]

        payload = {
            "parent": {"page_id": self.parent_page_id},
            "properties": {
                "title": {"title": [{"text": {"content": title}}]}
            },
            "children": blocks[:100],
        }
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": self.version,
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.notion.com/v1/pages", headers=headers, json=payload
            )
            response.raise_for_status()
            page_id = response.json().get("id")

        # Notion's create-page endpoint limits initial children; append remaining
        # blocks when the generated resume is long.
        if page_id and len(blocks) > 100:
            for start in range(100, len(blocks), 100):
                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.patch(
                        f"https://api.notion.com/v1/blocks/{page_id}/children",
                        headers=headers,
                        json={"children": blocks[start : start + 100]},
                    )
                    response.raise_for_status()
        return page_id

    @staticmethod
    def _heading(text: str) -> dict:
        return {
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": text[:2000]}}]
            },
        }

    @staticmethod
    def _paragraph(text: str) -> dict:
        return {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": str(text)[:2000]}}]
            },
        }

    @staticmethod
    def _bullets(items: list) -> list[dict]:
        items = [str(x) for x in items if str(x).strip()]
        return [
            {
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": x[:2000]}}]
                },
            }
            for x in items
        ] or [NotionReviewQueue._paragraph("None identified.")]

    @staticmethod
    def _experience_blocks(experience: list[dict]) -> list[dict]:
        blocks = []
        for item in experience:
            if isinstance(item, dict):
                title = item.get("title") or item.get("role") or "Experience"
                company = item.get("company") or ""
                dates = item.get("dates") or item.get("date") or ""
                header = " — ".join(x for x in [title, company, dates] if x)
                blocks.append(NotionReviewQueue._paragraph(header))
                bullets = item.get("bullets") or item.get("responsibilities") or []
                blocks.extend(NotionReviewQueue._bullets(bullets))
            else:
                blocks.append(NotionReviewQueue._paragraph(str(item)))
        return blocks or [NotionReviewQueue._paragraph("No experience returned.")]

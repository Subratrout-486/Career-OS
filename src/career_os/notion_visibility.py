"""Make Resume Library records visibly self-describing."""

import httpx


def _patch():
    from .notion import NotionReviewQueue
    original = NotionReviewQueue.create_review_page

    async def create_review_page(self, result):
        review_id, library_id = await original(self, result)
        if library_id and self.token:
            job = result["job"]
            files = [str(path).split("/")[-1] for path in (result.get("resume_files") or {}).values()]
            text = "Generated resume files: " + (", ".join(files) or "none") + ". Open the Resume File property on this record to review the attached PDF/DOCX."
            payload = {"children": [{"object":"block","type":"heading_2","heading_2":{"rich_text":[{"type":"text","text":{"content":"Generated resume files"}}]}},{"object":"block","type":"paragraph","paragraph":{"rich_text":[{"type":"text","text":{"content":text}}]}},{"object":"block","type":"paragraph","paragraph":{"rich_text":[{"type":"text","text":{"content":f"Source: {job.get('company')} — {job.get('title')} | Human review required before applying."}}]}}]}
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.patch(f"https://api.notion.com/v1/blocks/{library_id}/children", headers=self.headers, json=payload)
                response.raise_for_status()
        return review_id, library_id

    NotionReviewQueue.create_review_page = create_review_page

_patch()

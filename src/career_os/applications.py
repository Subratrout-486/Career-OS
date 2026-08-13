"""Minimal Notion Applications tracking helper.

Career OS never marks Applied automatically. Records start as READY TO APPLY.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_APPLICATIONS_DS = "a7755702-0d2a-4d68-919b-3401e1d8ff75"


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

    async def create_review_record(self, result: dict[str, Any]) -> str | None:
        if not self.token or not self.data_source_id:
            return None
        job = result.get("job") or {}
        fit = result.get("fit") or {}
        title = f"{job.get('company', 'Company')} — {job.get('title', 'Role')}"
        notes = (
            f"Fit: {fit.get('fit_score')} | {fit.get('recommendation')} | "
            f"Band: {fit.get('band')}. Review in Career OS before applying. "
            "Do not mark Applied until you personally submit."
        )
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
            "Application Status": {"select": {"name": "READY TO APPLY"}},
            "Next Action": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": "Review Notion package, open application URL, submit yourself, then mark APPLIED."
                        },
                    }
                ]
            },
            "Notes": {
                "rich_text": [{"type": "text", "text": {"content": notes[:2000]}}]
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

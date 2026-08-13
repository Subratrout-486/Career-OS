"""Application-question capture, draft answers, and Notion persistence.

The browser extension sends a structured question payload through GitHub. Questions are
stored in a dedicated Notion data source and can be edited by the user. AI drafts are
never treated as approved answers, and user edits are never overwritten.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_PARENT_PAGE = "3ab8bc1d-ce0e-80bc-8e55-f1c80ae06393"
DEFAULT_DB_TITLE = "Career OS — Application Questions"


class ApplicationQuestionStore:
    def __init__(self):
        self.token = os.getenv("NOTION_TOKEN")
        self.version = os.getenv("NOTION_VERSION", "2026-03-11")
        self.parent_page_id = os.getenv("NOTION_REVIEW_QUEUE_PAGE_ID", DEFAULT_PARENT_PAGE).replace("-", "")
        self.data_source_id = (os.getenv("NOTION_APPLICATION_QUESTIONS_DATA_SOURCE_ID") or "").replace("collection://", "").strip()

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": self.version,
            "Content-Type": "application/json",
        }

    async def _search_data_source(self, client: httpx.AsyncClient) -> str | None:
        response = await client.post(
            "https://api.notion.com/v1/search",
            headers=self.headers,
            json={"query": DEFAULT_DB_TITLE, "page_size": 25},
        )
        response.raise_for_status()
        for item in response.json().get("results", []):
            if item.get("object") == "data_source" and item.get("id"):
                title = "".join(x.get("plain_text", "") for x in item.get("title", []))
                if title == DEFAULT_DB_TITLE:
                    return item["id"].replace("-", "")
        return None

    async def ensure_data_source(self) -> str:
        if not self.token:
            raise RuntimeError("NOTION_TOKEN is required for application questions")
        if self.data_source_id:
            return self.data_source_id
        async with httpx.AsyncClient(timeout=60) as client:
            found = await self._search_data_source(client)
            if found:
                self.data_source_id = found
                return found
            response = await client.post(
                "https://api.notion.com/v1/databases",
                headers=self.headers,
                json={
                    "parent": {"type": "page_id", "page_id": self.parent_page_id},
                    "title": [{"type": "text", "text": {"content": DEFAULT_DB_TITLE}}],
                    "is_inline": False,
                    "initial_data_source": {
                        "properties": {
                            "Question": {"title": {}},
                            "Application ID": {"rich_text": {}},
                            "Company": {"rich_text": {}},
                            "Job Title": {"rich_text": {}},
                            "Question Type": {"select": {"options": [
                                {"name": "Yes/No"}, {"name": "Text"}, {"name": "Number"},
                                {"name": "Select"}, {"name": "Sensitive"}, {"name": "Other"}
                            ]}},
                            "Required": {"checkbox": {}},
                            "AI Draft": {"rich_text": {}},
                            "User Answer": {"rich_text": {}},
                            "Status": {"select": {"options": [
                                {"name": "NEEDS_REVIEW"}, {"name": "USER_APPROVED"},
                                {"name": "BLOCKED"}, {"name": "NOT_APPLICABLE"}
                            ]}},
                            "Evidence": {"rich_text": {}},
                            "Source URL": {"url": {}},
                            "Notes": {"rich_text": {}},
                        }
                    },
                },
            )
            if response.is_error:
                raise RuntimeError(f"Application Questions database creation failed ({response.status_code}): {response.text[:1500]}")
            data = response.json()
            sources = data.get("data_sources") or []
            if not sources:
                raise RuntimeError("Notion created Application Questions database but returned no data source ID")
            self.data_source_id = sources[0]["id"].replace("-", "")
            return self.data_source_id

    @staticmethod
    def _text(value: Any) -> list[dict[str, Any]]:
        value = str(value or "")
        return [{"type": "text", "text": {"content": value[:2000]}}] if value else []

    @staticmethod
    def _property_text(prop: dict[str, Any] | None) -> str:
        prop = prop or {}
        kind = prop.get("type")
        values = prop.get(kind, []) if kind else []
        if isinstance(values, list):
            return "".join(v.get("plain_text", v.get("text", {}).get("content", "")) for v in values)
        if kind == "select":
            return str((values or {}).get("name", ""))
        if kind == "checkbox":
            return "true" if values else "false"
        return str(values or "")

    async def create_questions(self, payload: dict[str, Any]) -> list[str]:
        ds = await self.ensure_data_source()
        application_id = str(payload.get("application_id") or payload.get("application_page_id") or "")
        company = str(payload.get("company") or "")
        title = str(payload.get("job_title") or payload.get("title") or "")
        url = str(payload.get("application_url") or payload.get("url") or "")
        created: list[str] = []
        async with httpx.AsyncClient(timeout=60) as client:
            for question in payload.get("questions") or []:
                text = str(question.get("text") or "").strip()
                if not text:
                    continue
                qtype = str(question.get("type") or "Other")
                if qtype not in {"Yes/No", "Text", "Number", "Select", "Sensitive", "Other"}:
                    qtype = "Other"
                required = bool(question.get("required", False))
                draft = str(question.get("ai_draft") or "").strip()
                evidence = str(question.get("evidence") or "").strip()
                status = "BLOCKED" if question.get("needs_confirmation") else "NEEDS_REVIEW"
                props = {
                    "Question": {"title": self._text(text)},
                    "Application ID": {"rich_text": self._text(application_id)},
                    "Company": {"rich_text": self._text(company)},
                    "Job Title": {"rich_text": self._text(title)},
                    "Question Type": {"select": {"name": qtype}},
                    "Required": {"checkbox": required},
                    "AI Draft": {"rich_text": self._text(draft)},
                    "User Answer": {"rich_text": []},
                    "Status": {"select": {"name": status}},
                    "Evidence": {"rich_text": self._text(evidence)},
                    "Notes": {"rich_text": self._text("User answer is authoritative. Career OS must not overwrite it.")},
                }
                if url:
                    props["Source URL"] = {"url": url}
                response = await client.post(
                    "https://api.notion.com/v1/pages",
                    headers=self.headers,
                    json={"parent": {"type": "data_source_id", "data_source_id": ds}, "properties": props},
                )
                if response.is_error:
                    raise RuntimeError(f"Application question create failed ({response.status_code}): {response.text[:1500]}")
                created.append(response.json()["id"])
        return created

    async def query(self, application_id: str | None = None) -> list[dict[str, Any]]:
        ds = await self.ensure_data_source()
        body: dict[str, Any] = {"page_size": 100}
        if application_id:
            body["filter"] = {"property": "Application ID", "rich_text": {"equals": application_id}}
        results: list[dict[str, Any]] = []
        cursor = None
        async with httpx.AsyncClient(timeout=60) as client:
            while True:
                if cursor:
                    body["start_cursor"] = cursor
                response = await client.post(f"https://api.notion.com/v1/data_sources/{ds}/query", headers=self.headers, json=body)
                response.raise_for_status()
                data = response.json()
                results.extend(data.get("results", []))
                if not data.get("has_more"):
                    break
                cursor = data.get("next_cursor")
        return results

    @classmethod
    def normalize_question(cls, page: dict[str, Any]) -> dict[str, Any]:
        p = page.get("properties", {})
        return {
            "id": page.get("id"),
            "question": cls._property_text(p.get("Question")),
            "application_id": cls._property_text(p.get("Application ID")),
            "company": cls._property_text(p.get("Company")),
            "job_title": cls._property_text(p.get("Job Title")),
            "required": cls._property_text(p.get("Required")) == "true",
            "ai_draft": cls._property_text(p.get("AI Draft")),
            "user_answer": cls._property_text(p.get("User Answer")),
            "status": cls._property_text(p.get("Status")),
            "evidence": cls._property_text(p.get("Evidence")),
            "last_edited_time": page.get("last_edited_time"),
        }

    async def readiness(self, application_id: str) -> dict[str, Any]:
        pages = await self.query(application_id)
        questions = [self.normalize_question(p) for p in pages]
        unresolved = [q for q in questions if q["required"] and (not q["user_answer"].strip() or q["status"] not in {"USER_APPROVED", "NOT_APPLICABLE"})]
        return {"application_id": application_id, "total": len(questions), "unresolved_required": unresolved, "ready": not unresolved, "questions": questions}

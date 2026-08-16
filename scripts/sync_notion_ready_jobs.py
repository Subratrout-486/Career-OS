#!/usr/bin/env python3
"""Bridge already-qualified Notion Jobs into the durable application pipeline.

This worker does not invent a JD, ATS score, fit decision, or resume.  It uses
only Jobs rows that already have an exact Job Link and a Resume Library relation,
then recovers the exact PDF/DOCX attachment from that Resume Library page into
the current lifecycle workspace.  The existing deterministic browser gates still
control execution.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import httpx

from career_os.applications import ApplicationsTracker

JOBS_DS = "3ab8bc1d-ce0e-808c-93c3-000b43141dec"
ATS_THRESHOLD = int(os.getenv("ATS_PASS_THRESHOLD", "60"))


def _id_from_url(value: str) -> str:
    path = urlparse(value).path.rstrip("/")
    candidate = path.rsplit("/", 1)[-1]
    candidate = re.sub(r"[^0-9a-fA-F-]", "", candidate)
    if len(candidate) >= 32:
        return candidate[-36:]
    return candidate


class NotionClient:
    def __init__(self) -> None:
        self.token = os.environ["NOTION_TOKEN"]
        self.version = os.getenv("NOTION_VERSION", "2026-03-11")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": self.version,
            "Content-Type": "application/json",
        }
        self.client = httpx.Client(timeout=60, follow_redirects=True)

    def close(self) -> None:
        self.client.close()

    def query_jobs(self) -> list[dict]:
        payload = {
            "filter": {
                "or": [
                    {"property": "Fit Decision", "select": {"equals": "Apply"}},
                    {"property": "Fit Decision", "select": {"equals": "Apply - Verify"}},
                ]
            },
            "page_size": 100,
        }
        response = self.client.post(
            f"https://api.notion.com/v1/data_sources/{JOBS_DS}/query",
            headers=self.headers,
            json=payload,
        )
        response.raise_for_status()
        return response.json().get("results", [])

    def page(self, page_id: str) -> dict:
        response = self.client.get(f"https://api.notion.com/v1/pages/{page_id}", headers=self.headers)
        response.raise_for_status()
        return response.json()

    def blocks(self, page_id: str) -> list[dict]:
        response = self.client.get(
            f"https://api.notion.com/v1/blocks/{page_id}/children?page_size=100",
            headers=self.headers,
        )
        response.raise_for_status()
        return response.json().get("results", [])

    def download_file(self, url: str, destination: Path) -> None:
        with self.client.stream("GET", url) as response:
            response.raise_for_status()
            with destination.open("wb") as handle:
                for chunk in response.iter_bytes(1024 * 1024):
                    handle.write(chunk)


def _plain(prop: dict) -> str:
    kind = prop.get("type")
    value = prop.get(kind) if kind else None
    if kind == "title" or kind == "rich_text":
        return "".join(item.get("plain_text", "") for item in (value or []))
    if kind == "url":
        return str(value or "")
    if kind == "number":
        return "" if value is None else str(value)
    if kind == "select":
        return str((value or {}).get("name") or "")
    return ""


def _resume_relation(prop: dict) -> list[str]:
    return [str(item.get("id")) for item in (prop.get("relation") or []) if item.get("id")]


def _attachment(client: NotionClient, resume_page_id: str) -> tuple[str, str] | None:
    for block in client.blocks(resume_page_id):
        block_type = block.get("type")
        if block_type not in {"file", "pdf"}:
            continue
        data = block.get(block_type) or {}
        if data.get("type") == "external":
            url = (data.get("external") or {}).get("url")
        else:
            url = (data.get("file") or {}).get("url")
        if url:
            filename = str(data.get("name") or "resume.pdf")
            if not filename.lower().endswith((".pdf", ".docx")):
                filename += ".pdf"
            return filename, url
    return None


def sync(workspace: Path) -> dict:
    workspace.mkdir(parents=True, exist_ok=True)
    results_dir = workspace / "pipeline_results"
    resumes_dir = workspace / "generated_resumes"
    results_dir.mkdir(parents=True, exist_ok=True)
    resumes_dir.mkdir(parents=True, exist_ok=True)
    client = NotionClient()
    tracker = ApplicationsTracker()
    summary = {"status": "OK", "prepared": [], "blocked": [], "skipped": []}
    try:
        for job_page in client.query_jobs():
            props = job_page.get("properties") or {}
            title = _plain(props.get("Name") or {})
            company = _plain(props.get("Company") or {})
            role = _plain(props.get("Role") or {}) or title
            job_url = _plain(props.get("Job Link") or {})
            fit_decision = _plain(props.get("Fit Decision") or {})
            fit_score_raw = _plain(props.get("Fit Score") or {})
            ats_raw = _plain(props.get("ATS Match") or {})
            resume_ids = _resume_relation(props.get("Resume Library") or {})
            if not job_url or not resume_ids:
                summary["blocked"].append({"job": title, "reason": "exact Job Link and Resume Library relation are required"})
                continue
            resume_page_id = resume_ids[0]
            resume_page = client.page(resume_page_id)
            resume_props = resume_page.get("properties") or {}
            resume_status = _plain(resume_props.get("Status") or {})
            resume_ats_raw = _plain(resume_props.get("ATS Score") or {})
            ats_raw = ats_raw or resume_ats_raw
            try:
                ats_score = int(float(ats_raw))
            except (ValueError, TypeError):
                ats_score = 0
            if ats_score < ATS_THRESHOLD:
                summary["blocked"].append({"job": title, "reason": f"ATS score {ats_score} is below threshold {ATS_THRESHOLD}"})
                continue
            attachment = _attachment(client, resume_page_id)
            if not attachment:
                summary["blocked"].append({"job": title, "reason": "Resume Library page has no downloadable PDF/DOCX attachment"})
                continue
            filename, signed_url = attachment
            safe = re.sub(r"[^A-Za-z0-9._-]+", "_", f"{company}_{role}_{filename}")
            destination = resumes_dir / safe
            if not destination.is_file() or destination.stat().st_size == 0:
                client.download_file(signed_url, destination)
            if destination.stat().st_size == 0:
                summary["blocked"].append({"job": title, "reason": "downloaded resume is empty"})
                continue

            fit_score = None
            try:
                fit_score = int(float(fit_score_raw))
            except (ValueError, TypeError):
                pass
            recommendation = "APPLY" if fit_decision == "Apply" else "APPLY-STRETCH"
            application_mode = "REVIEW_REQUIRED"
            result = {
                "application_page_id": "",
                "job": {"company": company, "title": role, "url": job_url, "location": _plain(props.get("location") or {})},
                "job_verification": {"application_url": job_url, "status": "ACTIVE", "active": True},
                "fit": {"fit_score": fit_score, "recommendation": recommendation, "band": "A" if (fit_score or 0) >= 80 else "B"},
                "ats": {"score": ats_score, "passed": ats_score >= ATS_THRESHOLD, "method": "existing_notion_resume_library"},
                "resume_files": {"pdf": str(destination) if destination.suffix.lower() == ".pdf" else "", "docx": str(destination) if destination.suffix.lower() == ".docx" else ""},
                "resume_library_page_id": resume_page_id,
                "review_status": "READY_FOR_REVIEW",
                "application_mode": application_mode,
                "application_mode_reason": "Existing Notion Jobs + Resume Library package recovered; live browser verification is still required.",
                "primary_recommendation": "APPLY",
                "primary_recommendation_provider": "notion-existing-package",
                "recruiter_review": {"status": "NOT_RUN", "provider": ""},
                "design_qa": {"passed": False},
                "errors": [],
                "notion_job_page_id": job_page.get("id"),
            }
            page_id = tracker.find_existing_record(result["job"])
            import asyncio
            page_id = asyncio.run(page_id) if hasattr(page_id, "__await__") else page_id
            if not page_id:
                page_id = asyncio.run(tracker.create_review_record(result))
            if not page_id:
                summary["blocked"].append({"job": title, "reason": "could not create/recover Applications record"})
                continue
            result["application_page_id"] = str(page_id)
            candidate_path = results_dir / (re.sub(r"[^A-Za-z0-9._-]+", "_", str(page_id)) + ".json")
            candidate_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            summary["prepared"].append({"job": title, "application_id": str(page_id), "ats": ats_score, "resume": destination.name})
    finally:
        client.close()
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path("browser_lifecycle"))
    parser.add_argument("--output", type=Path, default=Path("notion_ready_jobs_result.json"))
    args = parser.parse_args()
    result = sync(args.workspace)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Stage 2: enrich only validated INTAKED jobs with a usable job description.

This worker never performs matching, resume generation, Notion sync, or browser
execution. A job is advanced only when canonical JD evidence is present and
validated. Failed/blocked enrichment remains JD_PENDING for a later retry.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

MAX_JOBS = max(int(os.environ.get("MAX_JD_JOBS", "5")), 1)
ROOT = Path("jobs")
RUNTIME = ROOT / "jd_runtime"

JD_HEADERS = re.compile(r"(?i)\b(job summary|about the role|responsibilities|what you.?ll do|requirements|qualifications|preferred qualifications|what you.?ll need|skills|experience)\b")
JOB_CUES = re.compile(r"(?i)\b(application support|product support|technical support|responsibilities|requirements|qualifications|experience|skills|job summary|about the role|what you.?ll do)\b")
NON_JD_CUES = re.compile(r"(?i)\b(unsubscribe|privacy policy|terms of use|cookie policy|sign in|log in|create account)\b")


class TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self.skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"} and self.skip:
            self.skip -= 1

    def handle_data(self, data: str) -> None:
        if not self.skip and data.strip():
            self.parts.append(data)


def clean_html(value: str) -> str:
    parser = TextParser()
    parser.feed(value)
    text = html.unescape(" ".join(parser.parts))
    return re.sub(r"\s+", " ", text).strip()


def fetch_url(url: str) -> tuple[str | None, str | None]:
    if not url or not re.match(r"^https?://", url):
        return None, "no_usable_url"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Career-OS/2.0 JD-enrichment",
            "Accept": "text/html,application/xhtml+xml,application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read(1_500_000).decode("utf-8", errors="replace")
            content_type = str(response.headers.get("Content-Type") or "")
            if "json" in content_type or raw.lstrip().startswith(("{", "[")):
                try:
                    payload = json.loads(raw)
                    return clean_html(json.dumps(payload, ensure_ascii=False)), None
                except json.JSONDecodeError:
                    pass
            return clean_html(raw), None
    except urllib.error.HTTPError as exc:
        return None, f"http_{exc.code}"
    except Exception as exc:
        return None, f"fetch_error:{type(exc).__name__}"


def greenhouse_fallback_url(record: dict[str, Any]) -> str | None:
    source_url = str(record.get("source_url") or "").strip()
    source_job_id = str(record.get("source_job_id") or "").strip()
    if not source_url or not source_job_id or "boards-api.greenhouse.io/v1/boards/" not in source_url:
        return None
    base = source_url.split("?", 1)[0].rstrip("/")
    if not base.endswith("/jobs"):
        return None
    return f"{base}/{source_job_id}?content=true"


def extract_greenhouse_description(text: str) -> str:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text
    if not isinstance(payload, dict):
        return text
    for key in ("content", "description", "job_description"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return clean_html(value)
    return clean_html(json.dumps(payload, ensure_ascii=False))


def looks_like_jd(text: str) -> bool:
    if len(text) < 500:
        return False
    cues = len(JOB_CUES.findall(text))
    headers = len(JD_HEADERS.findall(text))
    non_jd = len(NON_JD_CUES.findall(text[:5000]))
    return (cues >= 4 or headers >= 2) and non_jd < 8


def canonical_job_id(record: dict[str, Any], path: Path) -> str:
    value = str(record.get("job_id") or "").strip()
    if value:
        return value
    raw = "|".join(str(record.get(k) or "").strip().lower() for k in ("company", "title", "location", "url"))
    if not raw:
        raw = str(path)
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def enrich(record: dict[str, Any], path: Path) -> tuple[dict[str, Any], str]:
    job = dict(record)
    job_id = canonical_job_id(job, path)
    job["job_id"] = job_id
    job["pipeline_stage"] = "JD_ENRICHMENT"
    description = str(job.get("description") or "").strip()

    candidates: list[tuple[str, str]] = []
    existing = str(job.get("jd_text") or "").strip()
    if existing:
        candidates.append((existing, "existing_jd_text"))
    if description:
        candidates.append((description, "intake_description"))

    fetch_error = None
    url = str(job.get("url") or job.get("apply_url") or "").strip()
    if url:
        fetched, fetch_error = fetch_url(url)
        if fetched:
            candidates.insert(0, (fetched, "role_url"))

    # Official employer pages can block automated clients even when their
    # public ATS feed is available. Prefer the canonical Greenhouse record
    # rather than treating an employer-page 403 as a terminal JD failure.
    if not any(looks_like_jd(text) for text, _ in candidates):
        greenhouse_url = greenhouse_fallback_url(job)
        if greenhouse_url:
            fetched, greenhouse_error = fetch_url(greenhouse_url)
            if fetched:
                candidates.insert(0, (extract_greenhouse_description(fetched), "greenhouse_api"))
                fetch_error = None
            elif greenhouse_error:
                fetch_error = greenhouse_error

    usable = next(((text, source) for text, source in candidates if looks_like_jd(text)), None)
    if usable:
        text, source = usable
        job["jd_text"] = text[:30000]
        job["description"] = text[:30000]
        job["jd_status"] = "complete"
        job["jd_error"] = None
        job["ready_state"] = "JD_AVAILABLE"
        job["status"] = "JD_READY"
        job["jd_evidence_source"] = source
        job["jd_enriched_at"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        return job, "JD_READY"

    job["status"] = "JD_PENDING"
    job["ready_state"] = "JD_PENDING"
    job["jd_status"] = "blocked" if fetch_error and fetch_error.startswith("http_403") else "unavailable"
    job["jd_error"] = fetch_error or "no_usable_job_description"
    job["jd_last_attempt_at"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    return job, "JD_PENDING"


def discover_inputs() -> list[Path]:
    paths: list[Path] = []
    # Stage 1 has two durable intake stores: Gmail and employer discovery.
    # Both are canonical inputs to Stage 2. Older inbox/root paths remain
    # supported for backward compatibility.
    for base in (
        ROOT / "email_runtime",
        ROOT / "discovery_runtime",
        ROOT / "inbox",
        ROOT,
    ):
        if not base.exists():
            continue
        for path in base.glob("*.json"):
            if "jd_runtime" in path.parts:
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(data, dict) and str(data.get("status") or "").upper() == "INTAKED":
                paths.append(path)
    return sorted(set(paths), key=lambda p: p.as_posix())[:MAX_JOBS]


def main() -> int:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    inputs = discover_inputs()
    report: dict[str, Any] = {
        "stage": "JD_ENRICHMENT",
        "input_count": len(inputs),
        "ready": 0,
        "pending": 0,
        "records": [],
    }
    for path in inputs:
        record = json.loads(path.read_text(encoding="utf-8"))
        updated, outcome = enrich(record, path)
        out = RUNTIME / f"{updated['job_id']}.json"
        out.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if outcome == "JD_READY":
            path.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            report["ready"] += 1
        else:
            report["pending"] += 1
        report["records"].append({
            "path": str(path),
            "job_id": updated["job_id"],
            "outcome": outcome,
            "jd_error": updated.get("jd_error"),
            "jd_evidence_source": updated.get("jd_evidence_source"),
        })
    (RUNTIME / "latest_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

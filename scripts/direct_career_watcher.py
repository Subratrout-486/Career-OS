"""Public official-career-site watcher for the existing Career OS intake path.

The watcher is intentionally upstream-only: it discovers public JobPosting JSON-LD
records or configured public ATS JSON feeds, normalizes them into the existing
Job payload, and never logs into or bypasses a protected site.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
WATCHLIST_PATH = Path(os.environ.get("CAREER_WATCHLIST", ROOT / "config" / "company_watchlist.json"))
OUT_DIR = Path(os.environ.get("DISCOVERY_OUT_DIR", ROOT / "jobs" / "discovery_runtime"))
TIMEOUT = float(os.environ.get("CAREER_SOURCE_TIMEOUT", "20"))
RETRIES = max(0, int(os.environ.get("CAREER_SOURCE_RETRIES", "2")))
MAX_WORKERS = max(1, int(os.environ.get("CAREER_SOURCE_BATCH_SIZE", "6")))
DAYS = int(os.environ.get("DISCOVERY_DAYS", "45"))
USER_AGENT = "Career-OS-direct-career-watcher/1.0 (+public-job-discovery)"
TITLE_RE = re.compile(r"(support|analyst|customer success|implementation|incident|service management|operations|technical account|product|program)", re.I)
EXCLUDE_RE = re.compile(r"(intern|director|vice president|vp |chief|principal|staff engineer)", re.I)
INDIA_RE = re.compile(r"(india|hyderabad|telangana|bangalore|bengaluru|karnataka|pune|chennai|gurugram|noida|mumbai|delhi)", re.I)
REMOTE_RE = re.compile(r"(remote|work from home|wfh)", re.I)

# URLs are stored in config/company_watchlist.json. Blank URLs are intentionally
# treated as UNCONFIGURED until an official source has been verified.


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def canonical_url(value: Any) -> str:
    raw = clean(value)
    if not raw:
        return ""
    parts = urllib.parse.urlsplit(raw)
    query = urllib.parse.urlencode(
        [(k, v) for k, v in urllib.parse.parse_qsl(parts.query) if not k.lower().startswith("utm_") and k.lower() not in {"ref", "source", "trk"}]
    )
    return urllib.parse.urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), query, ""))


def fetch(url: str) -> tuple[int, str, str]:
    last: Exception | None = None
    for attempt in range(RETRIES + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/json"})
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                body = response.read(3_000_000).decode("utf-8", errors="replace")
                return int(response.status), response.geturl(), body
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
            if attempt < RETRIES:
                time.sleep(2**attempt)
    raise RuntimeError(str(last or "source request failed"))


def iso_date(value: Any) -> str:
    text = clean(value)
    if not text:
        return ""
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except ValueError:
        return text


def eligible(title: str, location: str, description: str) -> bool:
    if not TITLE_RE.search(title) or EXCLUDE_RE.search(title):
        return False
    return bool(INDIA_RE.search(location) or (REMOTE_RE.search(location) and INDIA_RE.search(description)))


def iter_json_ld(body: str):
    for raw in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', body, flags=re.I | re.S):
        try:
            value = json.loads(html.unescape(raw.strip()))
        except json.JSONDecodeError:
            continue
        values = value if isinstance(value, list) else [value]
        for item in values:
            if isinstance(item, dict) and isinstance(item.get("@graph"), list):
                yield from (entry for entry in item["@graph"] if isinstance(entry, dict))
            elif isinstance(item, dict):
                yield item


def normalize(company: str, item: dict[str, Any], source_url: str, captured_at: str) -> dict[str, Any] | None:
    item_type = item.get("@type")
    if isinstance(item_type, list):
        is_job = "JobPosting" in item_type
    else:
        is_job = item_type == "JobPosting"
    if not is_job:
        return None
    title = clean(item.get("title"))
    description = clean(item.get("description"))
    url = canonical_url(item.get("url") or source_url)
    org = item.get("hiringOrganization") or {}
    location_data = item.get("jobLocation") or {}
    if isinstance(location_data, list):
        location_data = location_data[0] if location_data else {}
    address = location_data.get("address") if isinstance(location_data, dict) else {}
    if isinstance(address, list):
        address = address[0] if address else {}
    location = clean(" ".join(str(address.get(k, "")) for k in ("addressLocality", "addressRegion", "addressCountry"))) if isinstance(address, dict) else clean(location_data)
    if not location:
        location = "Remote" if item.get("jobLocationType") else "Not specified"
    if not title or not description or not url or not eligible(title, location, description):
        return None
    job_id = clean(item.get("identifier"))
    if isinstance(item.get("identifier"), dict):
        job_id = clean(item["identifier"].get("value") or item["identifier"].get("name"))
    identity = job_id or hashlib.sha256(f"{company}|{title}|{url}".encode()).hexdigest()
    return {
        "title": title,
        "company": company,
        "company_normalized": re.sub(r"[^a-z0-9]+", "-", company.lower()).strip("-"),
        "location": location,
        "url": url,
        "official_job_url": url,
        "source": "Employer Website — official public careers page",
        "source_type": "official_html_jsonld",
        "source_url": canonical_url(source_url),
        "source_job_id": identity,
        "job_id": identity,
        "description": description,
        "captured_at": captured_at,
        "first_seen_at": captured_at,
        "last_seen_at": captured_at,
        "last_checked_at": captured_at,
        "published_at": iso_date(item.get("datePosted")),
        "job_status": "ACTIVE",
        "application_status": "NOT_APPLIED",
        "work_mode": "REMOTE" if item.get("jobLocationType") else "ONSITE_OR_HYBRID",
        "content_hash": hashlib.sha256(description.encode()).hexdigest(),
        "source_hash": hashlib.sha256(canonical_url(source_url).encode()).hexdigest(),
        "dedupe_key": f"{re.sub(r'[^a-z0-9]+', '-', company.lower()).strip('-')}|{identity}",
    }


def greenhouse_items(data: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for raw in data.get("jobs", []) if isinstance(data, dict) else []:
        location = clean((raw.get("location") or {}).get("name"))
        content = clean(raw.get("content"))
        title = clean(raw.get("title"))
        if not title or not content or not eligible(title, location, content):
            continue
        items.append({
            "@type": "JobPosting",
            "title": title,
            "description": content,
            "url": raw.get("absolute_url"),
            "datePosted": raw.get("updated_at"),
            "identifier": {"value": raw.get("id")},
            "jobLocation": {"address": {"addressLocality": location}},
        })
    return items


def check_company(entry: dict[str, Any]) -> dict[str, Any]:
    company = str(entry["company"])
    source = dict(entry)
    now = utc_now()
    url = canonical_url(source.get("careers_url"))
    result: dict[str, Any] = {"company": company, "careers_url": url, "source_status": "UNAVAILABLE", "checked_at": now, "jobs": [], "error": ""}
    if not url:
        result["source_status"] = "UNCONFIGURED"
        result["error"] = "No verified public official careers URL is configured."
        return result
    try:
        status, resolved, body = fetch(url)
        result["http_status"] = status
        result["resolved_url"] = canonical_url(resolved)
        result["source_status"] = "AVAILABLE"
        if entry.get("source_type") == "official_greenhouse_json":
            items = greenhouse_items(json.loads(body))
        else:
            items = list(iter_json_ld(body))
        result["jobs"] = [job for item in items if (job := normalize(company, item, resolved, now))]
        if not result["jobs"]:
            result["source_status"] = "AVAILABLE_NO_PUBLIC_JOBPOSTING_DATA"
    except Exception as exc:
        result["error"] = str(exc)
    return result


def run(registry: list[dict[str, Any]] | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    registry = registry or load_registry()
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(check_company, entry): entry for entry in registry if entry.get("enabled", True)}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                entry = futures[future]
                results.append({"company": entry["company"], "source_status": "UNAVAILABLE", "checked_at": utc_now(), "jobs": [], "error": str(exc)})
    results.sort(key=lambda item: item["company"])
    jobs = [job for result in results for job in result.get("jobs", [])]
    digest = {
        "run_at": utc_now(),
        "total_companies_checked": len(results),
        "companies_successfully_checked": sum(r["source_status"] in {"AVAILABLE", "AVAILABLE_NO_PUBLIC_JOBPOSTING_DATA"} for r in results),
        "companies_unavailable": sum(r["source_status"] in {"UNAVAILABLE", "UNCONFIGURED"} for r in results),
        "total_jobs_discovered": len(jobs),
        "new_jobs": len(jobs),
        "updated_jobs": 0,
        "closed_jobs": 0,
        "hyderabad_jobs": sum("hyderabad" in str(j.get("location", "")).lower() for j in jobs),
        "source_failures": [{"company": r["company"], "status": r["source_status"], "error": r.get("error", "")} for r in results if r["source_status"] in {"UNAVAILABLE", "UNCONFIGURED"}],
        "companies": results,
    }
    (OUT_DIR / "direct_career_digest.json").write_text(json.dumps(digest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return jobs, digest


def load_registry() -> list[dict[str, Any]]:
    data = json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))
    entries = data if isinstance(data, list) else data.get("companies", [])
    out = []
    for item in entries:
        item = dict(item)
        out.append(item)
    return out


def main() -> int:
    jobs, digest = run()
    for job in jobs:
        print(f"DIRECT_DISCOVERED: {job['company']} — {job['title']} — {job['official_job_url']}")
    print(json.dumps({k: v for k, v in digest.items() if k != "companies"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

__all__ = ["check_company", "eligible", "load_registry", "normalize", "run"]

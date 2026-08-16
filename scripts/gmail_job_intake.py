#!/usr/bin/env python3
"""Ingest job-alert emails from Gmail into the Career OS intake queue."""
from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any

REPO = os.environ.get("GITHUB_REPOSITORY", "Subratrout-486/Career-OS")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
CLIENT_ID = os.environ.get("GMAIL_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("GMAIL_CLIENT_SECRET", "")
REFRESH_TOKEN = os.environ.get("GMAIL_REFRESH_TOKEN", "")
QUERY = os.environ.get("GMAIL_QUERY", 'newer_than:7d (job OR jobs OR career OR opportunity OR hiring OR support)')
MAX_NEW = int(os.environ.get("MAX_NEW_EMAIL_JOBS", "10"))

# Keep the strong role vocabulary, but do not require one of a tiny hard-coded
# list of titles/companies. Job-alert providers use many legitimate titles.
TITLE_RE = re.compile(
    r"(?i)\b(product support|technical support|customer support|application support|"
    r"production support|support engineer|support analyst|technical account|"
    r"customer success|service delivery|service desk|it support|operations analyst|"
    r"business analyst|data analyst|research analyst|implementation analyst|"
    r"software support|application analyst|systems analyst)\b"
)
GENERIC_ROLE_RE = re.compile(
    r"(?i)\b(engineer|developer|designer|analyst|specialist|associate|consultant|"
    r"administrator|architect|manager|coordinator|executive|recruiter|accountant|"
    r"scientist|technician|intern|trainee|lead|director|product manager|project manager)\b"
)
COMPANY_RE = re.compile(r"(?i)\b(oracle|tcs|infosys|amazon|microsoft|google|deloitte|accenture|ibm|infor)\b")
INDIA_RE = re.compile(r"(?i)\b(india|hyderabad|telangana|bangalore|bengaluru|gurugram|delhi|pune|chennai|noida|remote)\b")
JOB_URL_RE = re.compile(
    r"(?i)(oracle\.com/(?:.*?/)?jobs|oraclecloud\.com|greenhouse\.io|lever\.co|"
    r"myworkdayjobs\.com|jobs\.ashbyhq\.com|linkedin\.com/jobs|amazon\.jobs|"
    r"smartrecruiters\.com|icims\.com|successfactors\.|workable\.com|indeed\.com)"
)
JOB_SIGNAL_RE = re.compile(
    r"(?i)\b(job alert|job alerts|jobs? for you|recommended jobs?|new job|new jobs|"
    r"job match|job matches|career opportunity|career opportunities|open position|"
    r"open positions|vacanc(?:y|ies)|we(?:'|’)re hiring|now hiring|hiring now|"
    r"apply now|view job|view jobs|job details|see job|learn more|search jobs|"
    r"employment opportunity|role available|position available)\b"
)
NON_JOB_RE = re.compile(
    r"(?i)\b(invitation|invites? you|want to connect|connection request|accepted your invitation|"
    r"new message|message from|profile view|people you may know|someone viewed your profile|"
    r"post|posts|comment)\b"
)


def http_json(url: str, *, method: str = "GET", data: bytes | None = None, headers: dict[str, str] | None = None) -> dict[str, Any]:
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def access_token() -> str:
    missing = [name for name, value in {
        "GMAIL_CLIENT_ID": CLIENT_ID,
        "GMAIL_CLIENT_SECRET": CLIENT_SECRET,
        "GMAIL_REFRESH_TOKEN": REFRESH_TOKEN,
    }.items() if not value]
    if missing:
        raise RuntimeError("Gmail intake is not configured; missing: " + ", ".join(missing))
    body = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
        "grant_type": "refresh_token",
    }).encode()
    result = http_json(
        "https://oauth2.googleapis.com/token",
        method="POST",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    token = result.get("access_token")
    if not token:
        raise RuntimeError("Gmail OAuth refresh failed: access_token missing")
    return str(token)


def gmail_get(path: str, token: str, params: dict[str, str] | None = None) -> dict[str, Any]:
    query = ("?" + urllib.parse.urlencode(params)) if params else ""
    return http_json(
        f"https://gmail.googleapis.com/gmail/v1/users/me/{path}{query}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href = ""
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            self._href = dict(attrs).get("href") or ""
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href:
            self.links.append((" ".join(self._text).strip(), html.unescape(self._href)))
            self._href = ""
            self._text = []


def decode_part(data: str | None) -> str:
    if not data:
        return ""
    raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
    return raw.decode("utf-8", errors="replace")


def collect_bodies(part: dict[str, Any], *, html_parts: list[str], text_parts: list[str]) -> None:
    mime = str(part.get("mimeType") or "")
    body = part.get("body") or {}
    if body.get("data"):
        text = decode_part(str(body["data"]))
        if mime == "text/html":
            html_parts.append(text)
        elif mime == "text/plain":
            text_parts.append(text)
    for child in part.get("parts") or []:
        collect_bodies(child, html_parts=html_parts, text_parts=text_parts)


def strip_html(value: str) -> str:
    value = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", value)
    value = re.sub(r"(?is)<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def headers_map(message: dict[str, Any]) -> dict[str, str]:
    return {
        str(item.get("name", "")).lower(): str(item.get("value", ""))
        for item in (message.get("payload", {}).get("headers") or [])
    }


def candidate_links(html_body: str) -> list[tuple[str, str]]:
    parser = LinkParser()
    try:
        parser.feed(html_body)
    except Exception:
        pass
    ranked: list[tuple[int, str, str]] = []
    for anchor, href in parser.links:
        href = href.strip()
        if not href.startswith(("http://", "https://")):
            continue
        score = 0
        blob = f"{anchor} {href}".lower()
        if JOB_URL_RE.search(href):
            score += 5
        if re.search(r"\b(apply|view job|job details|learn more|see job|apply now)\b", anchor, re.I):
            score += 4
        if "unsubscribe" in blob or "preference" in blob or "privacy" in blob:
            score -= 10
        ranked.append((score, anchor, href))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [(anchor, href) for score, anchor, href in ranked if score > 0]


def infer_title(subject: str, text: str) -> str:
    cleaned_subject = re.sub(r"(?i)\b(oracle|jobs?|career|opportunities?|job alert|latest)\b[:\-–—| ]*", " ", subject)
    cleaned_subject = re.sub(r"\s+", " ", cleaned_subject).strip(" -|:")
    if cleaned_subject and len(cleaned_subject) <= 180 and (TITLE_RE.search(cleaned_subject) or GENERIC_ROLE_RE.search(cleaned_subject)):
        return cleaned_subject
    for line in re.split(r"[\n\r]|(?<=[.!?])\s+", text):
        line = re.sub(r"\s+", " ", line).strip(" -•")
        if 8 <= len(line) <= 180 and (TITLE_RE.search(line) or GENERIC_ROLE_RE.search(line)):
            return line
    return cleaned_subject[:180] if cleaned_subject else "Job alert requiring enrichment"


def infer_company(sender: str, subject: str, text: str) -> str:
    match = COMPANY_RE.search(sender) or COMPANY_RE.search(subject) or COMPANY_RE.search(text)
    if match:
        return match.group(1).title()
    sender_name = sender.split("<", 1)[0].strip()
    sender_name = re.sub(r"[\"']", "", sender_name)
    return sender_name[:120] or "Unknown company"


def issue_exists(marker: str) -> bool:
    for page in range(1, 6):
        result = http_json(
            f"https://api.github.com/repos/{REPO}/issues?state=all&per_page=100&page={page}",
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        issues = result if isinstance(result, list) else []
        if not issues:
            return False
        for issue in issues:
            if issue.get("pull_request"):
                continue
            body = str(issue.get("body") or "")
            if marker in body:
                return True
        if len(issues) < 100:
            return False
    return False


def create_issue(job: dict[str, Any]) -> None:
    marker = f"<!-- CAREER_OS_GMAIL_V1:{job['source_message_id']} -->"
    payload = json.dumps(job, ensure_ascii=False, indent=2)
    body = (
        f"{marker}\n<!-- CAREER_OS_JOB_V1 -->\n\n"
        "## Gmail job-alert intake\n\n"
        "This job was automatically extracted from Gmail. Process it through the normal Career OS safety pipeline. "
        "Do not submit unless the existing AUTO_APPLY contract is satisfied and actual submission can be verified.\n\n"
        f"```json\n{payload}\n```\n"
    )
    title = f"Career OS Gmail Intake — {job['company']} — {job['title']}"
    subprocess.run(
        ["gh", "issue", "create", "--repo", REPO, "--title", title[:250], "--body", body],
        check=True,
        env={**os.environ, "GH_TOKEN": TOKEN},
    )


def persist(job: dict[str, Any]) -> str:
    os.makedirs("jobs/email_runtime", exist_ok=True)
    digest = hashlib.sha256(job["source_message_id"].encode()).hexdigest()[:16]
    path = f"jobs/email_runtime/gmail-{digest}.json"
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(job, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return path


def classify_email(subject: str, sender: str, blob: str, links: list[tuple[str, str]]) -> tuple[bool, int, list[str]]:
    """Classify using multiple independent job signals instead of hard-coded companies."""
    signals: list[str] = []
    score = 0
    if TITLE_RE.search(subject) or TITLE_RE.search(blob):
        score += 2
        signals.append("specific-role")
    elif GENERIC_ROLE_RE.search(subject) or GENERIC_ROLE_RE.search(blob):
        score += 1
        signals.append("generic-role")
    if JOB_SIGNAL_RE.search(subject) or JOB_SIGNAL_RE.search(blob[:12000]):
        score += 2
        signals.append("job-language")
    if links:
        score += 2
        signals.append("job-link")
    if COMPANY_RE.search(sender) or COMPANY_RE.search(subject):
        score += 1
        signals.append("known-employer")
    # A recognizable sender domain/name is useful even when the employer is not
    # in the legacy hard-coded company list.
    if re.search(r"(?i)(linkedin|indeed|glassdoor|naukri|foundit|wellfound|greenhouse|lever|workday|smartrecruiters)", sender):
        score += 1
        signals.append("job-provider")
    return score >= 3, score, signals


def main() -> int:
    if not TOKEN:
        raise RuntimeError("GITHUB_TOKEN is required")
    token = access_token()
    listed = gmail_get("messages", token, {"q": QUERY, "maxResults": "50"})
    messages = listed.get("messages") or []
    created = 0
    paths: list[str] = []
    for item in messages:
        if created >= MAX_NEW:
            break
        message_id = str(item.get("id") or "")
        if not message_id:
            continue
        marker = f"CAREER_OS_GMAIL_V1:{message_id}"
        if issue_exists(marker):
            print(f"GMAIL_DUPLICATE_SKIPPED: message={message_id}")
            continue
        message = gmail_get(f"messages/{message_id}", token, {"format": "full"})
        headers = headers_map(message)
        subject = headers.get("subject", "")
        sender = headers.get("from", "")
        if NON_JOB_RE.search(subject):
            print(f"GMAIL_NON_JOB_SKIPPED: subject={subject}")
            continue
        html_parts: list[str] = []
        text_parts: list[str] = []
        collect_bodies(message.get("payload") or {}, html_parts=html_parts, text_parts=text_parts)
        html_body = "\n".join(html_parts)
        text_body = "\n".join(text_parts)
        clean_html = strip_html(html_body)
        blob = f"{subject}\n{sender}\n{text_body}\n{clean_html}"
        links = candidate_links(html_body)
        is_job, score, signals = classify_email(subject, sender, blob, links)
        if NON_JOB_RE.search(blob[:5000]) and not TITLE_RE.search(subject):
            print(f"GMAIL_NON_JOB_SKIPPED: sender={sender} subject={subject}")
            continue
        if not is_job:
            print(f"GMAIL_CLASSIFICATION_SKIPPED: score={score} signals={','.join(signals) or 'none'} subject={subject}")
            continue
        job = make_job(message_id, subject, sender, html_body, text_body, str(message.get("internalDate") or ""))
        if NON_JOB_RE.search(job.get("title", "")):
            print(f"GMAIL_NON_JOB_SKIPPED: title={job['title']}")
            continue
        try:
            create_issue(job)
            paths.append(persist(job))
            created += 1
            print(f"GMAIL_DISCOVERED: {job['company']} — {job['title']} — {job['url'] or 'NO_ROLE_URL'} score={score} signals={','.join(signals)}")
        except subprocess.CalledProcessError as exc:
            print(f"ERROR creating Gmail intake issue {message_id}: {exc}", file=sys.stderr)
    with open("gmail_discovered_paths.txt", "w", encoding="utf-8") as handle:
        handle.write("\n".join(paths) + ("\n" if paths else ""))
    print(f"Gmail intake complete: messages={len(messages)}, new_intakes={created}")
    return 0


def make_job(message_id: str, subject: str, sender: str, html_body: str, text_body: str, internal_date: str) -> dict[str, Any]:
    text = strip_html(html_body) if html_body else text_body
    links = candidate_links(html_body)
    title = infer_title(subject, text)
    company = infer_company(sender, subject, text)
    location_match = INDIA_RE.search(text)
    location = location_match.group(0) if location_match else "India / location to verify"
    job_url = links[0][1] if links else ""
    return {
        "title": title,
        "company": company,
        "location": location,
        "url": job_url,
        "source": "Gmail job alert",
        "source_message_id": message_id,
        "source_sender": sender,
        "source_subject": subject,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "published_at": datetime.fromtimestamp(int(internal_date) / 1000, tz=timezone.utc).isoformat() if str(internal_date).isdigit() else "",
        "description": text[:30000],
        "discovery_notes": "URL may require enrichment if the email did not expose a role-specific application link.",
    }


if __name__ == "__main__":
    raise SystemExit(main())

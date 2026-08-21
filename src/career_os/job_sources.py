"""Deterministic job-source adapters for AgentFlow.

This module deliberately handles discovery/transport separately from AI
reasoning. Company career pages can be supplied as public URLs; parsing and
normalization produce candidate records that later workflow nodes can inspect.
Authenticated sources such as Gmail/LinkedIn are injected as tools rather than
silently scraping credentials here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape
from typing import Any, Iterable
from urllib.parse import urljoin

import httpx


@dataclass(frozen=True)
class JobCandidate:
    title: str
    company: str
    url: str
    location: str | None = None
    description: str | None = None
    source: str = "company_careers"


class CompanyCareerSource:
    def __init__(self, *, timeout_sec: int = 20, user_agent: str = "CareerOS/0.1") -> None:
        self.timeout_sec = timeout_sec
        self.user_agent = user_agent

    async def fetch(self, url: str) -> str:
        if not url.startswith(("https://", "http://")):
            raise ValueError("career source URL must be http(s)")
        async with httpx.AsyncClient(timeout=self.timeout_sec, follow_redirects=True, headers={"User-Agent": self.user_agent}) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text

    def extract_candidates(self, html: str, *, base_url: str, company: str) -> list[JobCandidate]:
        """Extract conservative link candidates without inventing job facts."""
        candidates: list[JobCandidate] = []
        # Intentionally simple and deterministic. Site-specific selectors should
        # be registered as source plugins rather than guessed by the AI layer.
        for match in re.finditer(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.I | re.S):
            href, raw_text = match.groups()
            title = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", raw_text))).strip()
            if not title or len(title) < 4:
                continue
            absolute = urljoin(base_url, href)
            haystack = f"{title} {absolute}".lower()
            if not any(token in haystack for token in ("job", "career", "position", "role", "opening", "apply")):
                continue
            candidates.append(JobCandidate(title=title, company=company, url=absolute))
        unique: dict[str, JobCandidate] = {item.url: item for item in candidates}
        return list(unique.values())

    async def discover(self, *, url: str, company: str) -> list[JobCandidate]:
        html = await self.fetch(url)
        return self.extract_candidates(html, base_url=url, company=company)


def deduplicate_candidates(candidates: Iterable[JobCandidate]) -> list[JobCandidate]:
    seen: set[str] = set()
    result: list[JobCandidate] = []
    for candidate in candidates:
        key = candidate.url.rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result

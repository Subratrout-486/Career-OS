"""Structured JD analysis for Career OS.

Produces requirement lists that feed evidence retrieval.
Deterministic extraction is primary; optional AI enrichment can refine.
"""

from __future__ import annotations

import re
from typing import Iterable

from .models import Job, JDAnalysis

KNOWN_TOOLS = [
    "servicenow", "salesforce", "jira", "confluence", "control-m", "controlm",
    "oracle", "pl/sql", "plsql", "sql", "mysql", "postgres", "postgresql",
    "python", "java", "javascript", "rest api", "rest apis", "json", "postman",
    "aws", "azure", "gcp", "linux", "unix", "excel", "power bi", "powerbi",
    "power query", "tableau", "git", "bitbucket", "jenkins", "docker",
    "kubernetes", "tcp/ip", "dns", "dhcp", "vpn", "crm",
]

KNOWN_RESPONSIBILITY_CUES = [
    "troubleshoot", "troubleshooting", "incident", "ticket", "triage",
    "escalat", "sla", "rca", "root cause", "uat", "release", "runbook",
    "sop", "customer support", "technical support", "application support",
    "product support", "l1", "l2", "on-call", "monitor",
]

DOMAIN_CUES = [
    "corporate governance", "sec", "shareholder", "proxy", "10-k", "10-q",
    "workforce", "time and attendance", "reservation", "hospitality",
]


def _lines(text: str) -> list[str]:
    return [ln.strip(" -\t•*") for ln in text.splitlines() if ln.strip()]


def _section_bullets(description: str, headers: Iterable[str]) -> list[str]:
    lines = description.splitlines()
    header_re = re.compile(
        r"^(" + "|".join(re.escape(h) for h in headers) + r")\s*:?\s*$",
        re.I,
    )
    out: list[str] = []
    capturing = False
    for raw in lines:
        line = raw.strip()
        if header_re.match(line):
            capturing = True
            continue
        if capturing:
            if re.match(r"^[A-Z][A-Za-z ].{0,40}:?\s*$", line) and not line.startswith(("-", "•", "*")):
                if len(line) < 60 and not line.startswith(("•", "-", "*")):
                    capturing = False
                    continue
            cleaned = line.lstrip("-•* ").strip()
            if cleaned:
                out.append(cleaned)
    return out


def _find_tools(text: str) -> list[str]:
    lower = text.lower()
    found: list[str] = []
    for tool in KNOWN_TOOLS:
        if tool in lower:
            if tool in {"pl/sql", "plsql"}:
                label = "PL/SQL"
            elif tool in {"rest api", "rest apis"}:
                label = "REST APIs"
            elif tool in {"power bi", "powerbi"}:
                label = "Power BI"
            elif tool == "power query":
                label = "Power Query"
            elif tool == "servicenow":
                label = "ServiceNow"
            elif tool == "salesforce":
                label = "Salesforce"
            elif tool in {"sql", "aws", "uat", "sla", "crm", "json"}:
                label = tool.upper()
            else:
                label = tool.title() if tool.islower() else tool
            if label not in found:
                found.append(label)
    return found


def _find_cues(text: str, cues: list[str]) -> list[str]:
    lower = text.lower()
    return [c for c in cues if c in lower]


def _experience_requirement(text: str) -> str | None:
    patterns = [
        r"(\d+\+?\s*(?:to|-)\s*\d+\s*years?[^\n.]{0,40})",
        r"(\d+\+?\s*years?[^\n.]{0,40}experience[^\n.]{0,40})",
        r"(minimum\s+of\s+\d+\s*years?[^\n.]{0,40})",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            return m.group(1).strip()
    return None


def analyze_jd(job: Job) -> JDAnalysis:
    """Deterministic structured JD analysis."""
    desc = job.description or ""
    full = f"{job.title}\n{job.company}\n{job.location or ''}\n{desc}"

    mandatory = _section_bullets(
        desc,
        [
            "Requirements",
            "Required Qualifications",
            "Mandatory",
            "Must Have",
            "Minimum Qualifications",
            "What you'll need",
            "Qualifications",
        ],
    )
    preferred = _section_bullets(
        desc,
        ["Preferred", "Nice to Have", "Good to Have", "Preferred Qualifications"],
    )
    responsibilities = _section_bullets(
        desc,
        [
            "Responsibilities",
            "What you'll do",
            "Role",
            "Key Responsibilities",
            "About the role",
        ],
    )

    tools = _find_tools(full)
    tech = list(tools)
    for cue in _find_cues(full, KNOWN_RESPONSIBILITY_CUES):
        label = cue.replace("escalat", "escalation").title()
        if label not in tech and label not in mandatory:
            tech.append(label)

    domain = []
    for cue in _find_cues(full, DOMAIN_CUES):
        domain.append(cue.title() if cue.islower() else cue)

    education = []
    if re.search(r"\b(b\.?tech|b\.?e\.?|computer science|engineering degree|bachelor)\b", full, re.I):
        education.append("Bachelor's degree (see JD for field)")
    if re.search(r"\b(master'?s|m\.?tech|mba)\b", full, re.I):
        education.append("Master's degree preferred or required (see JD)")

    location = job.location
    if re.search(r"\bremote\b", full, re.I):
        location = (location or "") + (" | Remote" if location else "Remote")
    if re.search(r"\bhybrid\b", full, re.I):
        location = (location or "") + (" | Hybrid" if location else "Hybrid")

    if not mandatory and not responsibilities:
        for ln in _lines(desc)[:30]:
            if len(ln) > 20:
                responsibilities.append(ln)

    raw_keywords = []
    for item in tools + tech + domain:
        if item.lower() not in {k.lower() for k in raw_keywords}:
            raw_keywords.append(item)

    return JDAnalysis(
        mandatory=mandatory[:40],
        preferred=preferred[:20],
        responsibilities=responsibilities[:40],
        technical_skills=tech[:30],
        tools=tools[:30],
        domain_knowledge=domain[:20],
        soft_skills=[],
        education=education,
        experience_requirement=_experience_requirement(full),
        location_work_model=location,
        screening_requirements=[],
        raw_keywords=raw_keywords,
    )


def requirements_for_retrieval(analysis: JDAnalysis) -> list[str]:
    """Flatten analysis into retrieval queries (one requirement string each)."""
    reqs = analysis.all_requirements()
    for tool in analysis.tools:
        if tool not in reqs:
            reqs.append(tool)
    return reqs[:50]

"""Deterministic guardrail for tailored-resume factual integrity.

The canonical resume in config/master_profile.md is the primary source of truth.
Career Evidence Vault records may add separately confirmed evidence, but stale or
conflicting employer/tool deny-lists must never override the canonical resume.
"""

from __future__ import annotations

import re
from typing import Sequence

from .evidence import EvidenceItem
from .models import FitReport, TailoredResume

TOOL_ALIASES = {
    "aws": ("aws", "amazon web services"),
    "serviceNow": ("servicenow",),
    "sql": ("sql",),
    "oracle": ("oracle",),
    "pl/sql": ("pl/sql", "plsql"),
    "unix": ("unix",),
    "linux": ("linux",),
    "control-m": ("control-m", "control m"),
    "rest api": ("rest api", "rest apis"),
    "json": ("json",),
    "postman": ("postman",),
    "python": ("python",),
    "power bi": ("power bi",),
    "power query": ("power query",),
    "salesforce": ("salesforce",),
    "excel": ("excel", "microsoft excel"),
    "crm": ("crm",),
    "tableau": ("tableau",),
}

# IMPORTANT: There is intentionally no employer/tool deny-list here.
# The uploaded canonical resume explicitly associates Python, SQL, Power Query,
# Power BI, REST API testing and UAT with IGT Solutions. A stale deny-list must
# not override the user's designated source of truth.

EMPLOYER_ALIASES = {
    "factset systems": "factset systems",
    "factset systems india": "factset systems",
    "factset systems india pvt. ltd.": "factset systems",
    "igt solutions": "igt solutions",
    "concentrix": "concentrix (comcast)",
    "concentrix (comcast process)": "concentrix (comcast)",
    "concentrix (comcast/xfinity process)": "concentrix (comcast)",
}


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").lower()).strip()


def _norm_date(value: str) -> str:
    return _norm(re.sub(r"[\u2010-\u2015\u2212]", "-", value or ""))


def _canonical_employer(value: str) -> str:
    normalized = _norm(value)
    return EMPLOYER_ALIASES.get(normalized, normalized)


def _employer_in_profile(company: str, profile_blob: str) -> bool:
    normalized = _norm(company)
    canonical = _canonical_employer(company)
    if normalized in profile_blob or canonical in profile_blob:
        return True
    return any(
        alias in profile_blob
        for alias, canonical_name in EMPLOYER_ALIASES.items()
        if canonical_name == canonical
    )


def _contains(text: str, aliases: tuple[str, ...]) -> bool:
    blob = _norm(text)
    return any(alias in blob for alias in aliases)


def _experience_dict(exp: object) -> dict | None:
    if isinstance(exp, dict):
        return exp
    model_dump = getattr(exp, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        return dumped if isinstance(dumped, dict) else None
    return None


def _experience_blob(exp: object) -> str:
    data = _experience_dict(exp) or {}
    bullets = data.get("bullets") or data.get("responsibilities") or []
    return " ".join(
        [str(data.get("title", "")), str(data.get("company", "")), str(data.get("dates", ""))]
        + [str(item) for item in bullets]
    )


def _canonical_experience_section(company: str, profile: str) -> str:
    """Return the canonical resume section for one employer.

    master_profile.md stores the authoritative experience under markdown headings.
    We intentionally scope tool checks to the matching employer section so a tool
    confirmed for FactSet cannot accidentally be attributed to IGT or Concentrix.
    """
    canonical = _canonical_employer(company)
    lines = profile.splitlines()
    start = None
    collected: list[str] = []

    for index, line in enumerate(lines):
        if not re.match(r"^#{3,6}\s+", line):
            continue
        heading = _norm(re.sub(r"^#{3,6}\s+", "", line))
        if canonical and canonical in heading:
            start = index
            break

    if start is None:
        return ""

    collected.append(lines[start])
    for line in lines[start + 1 :]:
        if re.match(r"^#{3,6}\s+", line):
            break
        collected.append(line)
    return "\n".join(collected)


def _canonical_has_tool(company: str, tool_aliases: tuple[str, ...], profile: str) -> bool:
    section = _canonical_experience_section(company, profile)
    if not section or not _contains(section, tool_aliases):
        return False
    # The canonical Concentrix entry explicitly labels Python/Linux as a
    # personal home-lab, not professional experience. Preserve that boundary
    # even though the same employer section contains the tool words.
    canonical = _canonical_employer(company)
    if canonical == "concentrix (comcast)" and any(alias in {"python", "linux"} for alias in tool_aliases):
        return False
    return True


def _canonical_has_title(company: str, title: str, profile: str) -> bool:
    section = _canonical_experience_section(company, profile)
    if not section or not title:
        return False
    return _norm(title) in _norm(section)


def validate_resume_truth(
    *,
    resume: TailoredResume,
    profile: str,
    fit: FitReport,
    evidence_pack: Sequence[EvidenceItem],
) -> list[str]:
    issues: list[str] = []
    profile_blob = _norm(profile)
    usable = [item for item in evidence_pack if item.is_usable_professional]

    for exp in resume.experience:
        data = _experience_dict(exp)
        if data is None:
            issues.append("Experience entry is not a structured object.")
            continue

        company = str(data.get("company", "")).strip()
        title = str(data.get("title", "")).strip()
        dates = str(data.get("dates", "")).strip()
        canonical_company = _canonical_employer(company)

        if company and not _employer_in_profile(company, profile_blob):
            issues.append(f"Experience company is not present in MASTER_PROFILE: {company}")
        if title and not _canonical_has_title(company, title, profile):
            issues.append(f"Experience title is not present in canonical resume for {company}: {title}")
        if dates and _norm_date(dates) not in _norm_date(profile_blob):
            issues.append(f"Experience dates are not present in MASTER_PROFILE: {dates}")

        exp_text = _experience_blob(data)
        if not company:
            issues.append("Experience entry is missing employer.")
            continue

        employer_evidence = [
            item for item in usable
            if _canonical_employer(item.employer) == canonical_company
        ]
        employer_blob = " ".join(item.searchable_text() for item in employer_evidence)

        for tool, aliases in TOOL_ALIASES.items():
            if not _contains(exp_text, aliases):
                continue

            # Canonical resume evidence takes precedence over the Evidence Vault.
            # This is what prevents stale rows from rejecting claims explicitly
            # present in the user's authoritative resume.
            if _canonical_has_tool(company, aliases, profile):
                continue

            if not employer_evidence:
                issues.append(
                    f"Tool '{tool}' appears under {company}, but it is not supported by the canonical resume or approved professional evidence."
                )
            elif not _contains(employer_blob, aliases):
                issues.append(
                    f"Tool '{tool}' appears under {company}, but approved evidence does not map it to that employer."
                )

    overall_text = " ".join(
        [resume.title, resume.summary, " ".join(resume.skills)]
        + [_experience_blob(e) for e in resume.experience if _experience_dict(e) is not None]
    )
    overall_evidence = " ".join(item.searchable_text() for item in usable)

    # A claim is supported if it exists in the canonical resume or in separately
    # confirmed professional evidence. This avoids rejecting canonical resume skills
    # merely because an older evidence-vault row was incomplete.
    canonical_text = profile_blob
    for tool, aliases in TOOL_ALIASES.items():
        if not _contains(overall_text, aliases):
            continue
        if _contains(canonical_text, aliases) or _contains(overall_evidence, aliases):
            continue
        issues.append(
            f"Tool '{tool}' appears in the resume but is not supported by the canonical resume or approved professional evidence."
        )

    for request in fit.confirmation_requests:
        match = re.search(r"requires\s+([^.?]+)", request, re.I)
        if match:
            requested = _norm(match.group(1))
            if requested and requested in _norm(overall_text):
                issues.append(f"Unconfirmed requirement appears in resume: {requested}")

    for item in usable:
        unsafe = _norm(item.unsafe_wording)
        if unsafe and unsafe in _norm(overall_text):
            issues.append(f"Resume contains evidence-marked unsafe wording for {item.employer}.")

    return list(dict.fromkeys(issues))

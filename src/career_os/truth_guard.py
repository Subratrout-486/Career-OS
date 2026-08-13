"""Deterministic guardrail for tailored-resume factual integrity."""

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

# Resume company labels may be shortened compared with the canonical Notion
# employer option. These are display-name aliases, not new employers.
EMPLOYER_ALIASES = {
    "factset systems": "factset systems india pvt. ltd.",
    "factset systems india": "factset systems india pvt. ltd.",
    "concentrix": "concentrix (comcast process)",
    "concentrix (comcast)": "concentrix (comcast process)",
    "concentrix (comcast/xfinity process)": "concentrix (comcast process)",
}


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").lower()).strip()


def _norm_date(value: str) -> str:
    """Normalize dash glyphs without changing the date tokens themselves."""
    return _norm(re.sub(r"[\u2010-\u2015\u2212]", "-", value or ""))


def _canonical_employer(value: str) -> str:
    normalized = _norm(value)
    return EMPLOYER_ALIASES.get(normalized, normalized)


def _employer_in_profile(company: str, profile_blob: str) -> bool:
    """Accept a known display alias when the canonical employer is in the profile."""
    normalized = _norm(company)
    canonical = _canonical_employer(company)
    if normalized in profile_blob or canonical in profile_blob:
        return True
    for alias, canonical in EMPLOYER_ALIASES.items():
        if canonical == _canonical_employer(company) and alias in profile_blob:
            return True
    return False


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

    # unsupported_claims is an audit trail for claims deliberately omitted or
    # rejected by the resume agent. It is not itself evidence that the claim
    # leaked into the resume, so it must not fail the truth gate.

    for exp in resume.experience:
        data = _experience_dict(exp)
        if data is None:
            issues.append("Experience entry is not a structured object.")
            continue
        company = str(data.get("company", "")).strip()
        dates = str(data.get("dates", "")).strip()
        if company and not _employer_in_profile(company, profile_blob):
            issues.append(f"Experience company is not present in MASTER_PROFILE: {company}")
        if dates and _norm_date(dates) not in _norm_date(profile_blob):
            issues.append(f"Experience dates are not present verbatim in MASTER_PROFILE: {dates}")

        exp_text = _experience_blob(data)
        if not company:
            issues.append("Experience entry is missing employer.")
            continue
        employer_evidence = [
            item for item in usable
            if _canonical_employer(item.employer) == _canonical_employer(company)
        ]
        employer_blob = " ".join(item.searchable_text() for item in employer_evidence)

        for tool, aliases in TOOL_ALIASES.items():
            if not _contains(exp_text, aliases):
                continue
            if not employer_evidence:
                issues.append(
                    f"Tool '{tool}' appears under {company}, but no usable professional evidence exists for that employer."
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
    for tool, aliases in TOOL_ALIASES.items():
        if _contains(overall_text, aliases) and not _contains(overall_evidence, aliases):
            issues.append(
                f"Tool '{tool}' appears in the resume but is not supported by approved professional evidence."
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

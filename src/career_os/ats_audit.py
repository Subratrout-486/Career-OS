"""Transparent ATS coverage audit.

Score = percentage of relevant JD keywords found in the tailored resume text.
Unsupported keywords must never be recommended for addition without evidence.
"""

from __future__ import annotations

import re
from typing import Sequence

from .evidence import EvidenceItem
from .models import ATSAudit, JDAnalysis, TailoredResume


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _resume_blob(resume: TailoredResume) -> str:
    parts = [resume.title, resume.summary, " ".join(resume.skills)]
    for exp in resume.experience:
        if isinstance(exp, dict):
            parts.append(str(exp.get("title", "")))
            parts.append(str(exp.get("company", "")))
            parts.append(str(exp.get("dates", "")))
            bullets = exp.get("bullets") or exp.get("responsibilities") or []
            parts.extend(str(b) for b in bullets)
        else:
            parts.append(str(exp))
    parts.extend(resume.education)
    return _normalize(" ".join(parts))


def _evidence_supported_keywords(vault: Sequence[EvidenceItem]) -> set[str]:
    supported: set[str] = set()
    for item in vault:
        if not item.is_usable_professional:
            continue
        for field in (item.claim, item.safe_wording, item.context):
            for token in re.findall(r"[a-z0-9][a-z0-9+./#-]{1,}", field.lower()):
                if len(token) >= 3:
                    supported.add(token)
    return supported


def audit_resume(
    *,
    jd: JDAnalysis,
    resume: TailoredResume,
    vault: Sequence[EvidenceItem],
) -> ATSAudit:
    blob = _resume_blob(resume)
    keywords = list(dict.fromkeys(
        [k for k in (jd.raw_keywords + jd.tools + jd.technical_skills) if k and len(k.strip()) >= 2]
    ))
    if not keywords:
        keywords = list(dict.fromkeys(jd.mandatory[:15] + jd.responsibilities[:10]))

    supported = _evidence_supported_keywords(vault)
    matched: list[str] = []
    partial: list[str] = []
    missing: list[str] = []
    unsupported: list[str] = []

    for kw in keywords:
        norm = _normalize(kw)
        tokens = [t for t in re.findall(r"[a-z0-9][a-z0-9+./#-]{1,}", norm) if len(t) >= 3]
        if not tokens:
            continue
        if norm in blob or all(t in blob for t in tokens):
            matched.append(kw)
        elif any(t in blob for t in tokens):
            partial.append(kw)
        else:
            if any(t in supported for t in tokens):
                missing.append(kw)
            else:
                unsupported.append(kw)
                missing.append(kw)

    relevant = len(matched) + len(partial) + len([m for m in missing if m not in unsupported])
    covered = len(matched) + 0.5 * len(partial)
    score = int(round((covered / relevant) * 100)) if relevant else 0
    score = max(0, min(100, score))

    notes = (
        f"Transparent coverage of {len(keywords)} JD-derived keywords. "
        f"Matched={len(matched)}, partial={len(partial)}, missing={len(missing)}, "
        f"unsupported/do-not-add={len(unsupported)}. "
        "Missing keywords are only recommended for addition when backed by confirmed evidence."
    )
    return ATSAudit(
        score=score,
        method="relevant_jd_keyword_coverage",
        matched=matched,
        partial=partial,
        missing=missing,
        unsupported_do_not_add=unsupported,
        notes=notes,
    )

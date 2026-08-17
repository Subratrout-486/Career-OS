"""Independent, provider-free ATS-style validation.

This checker intentionally uses a different scoring model from ``ats_audit``.
It treats ATS readiness as a weighted combination of lexical coverage,
section completeness, and plain-text parseability. It never recommends adding
unsupported claims; it only reports what is present or absent in the generated
resume model.
"""

from __future__ import annotations

import re

from .models import IndependentATSAudit, JDAnalysis, TailoredResume


def _norm(text: str) -> str:
    text = text.lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9+#./-]+", " ", text).strip()


def _tokens(text: str) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9][a-z0-9+#./-]{1,}", _norm(text))
        if len(token) >= 3
    }


def _resume_text(resume: TailoredResume) -> str:
    parts = [resume.title, resume.summary, *resume.skills, *resume.education]
    for exp in resume.experience:
        parts.extend([exp.title, exp.company, exp.dates, *exp.bullets])
    return "\n".join(str(part) for part in parts if str(part).strip())


def _keyword_candidates(jd: JDAnalysis) -> list[str]:
    # Prefer concrete skills/tools and then the JD's explicit raw keywords.
    values = [*jd.technical_skills, *jd.tools, *jd.raw_keywords]
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        value = str(value).strip()
        key = _norm(value)
        if len(key) >= 2 and key not in seen:
            seen.add(key)
            result.append(value)
    return result[:40]


def audit_independent_ats(
    *,
    jd: JDAnalysis,
    resume: TailoredResume,
    threshold: int = 60,
) -> IndependentATSAudit:
    """Return a second ATS signal without LLMs or the existing ATS algorithm.

    Return the canonical Pydantic ``IndependentATSAudit`` model used by
    ``PipelineResult``. Keeping one schema at the producer/consumer boundary
    prevents a dataclass/Pydantic mismatch from crashing the live pipeline.
    """
    threshold = max(0, min(100, int(threshold)))
    text = _norm(_resume_text(resume))
    resume_tokens = _tokens(text)
    keywords = _keyword_candidates(jd)

    matched: list[str] = []
    missing: list[str] = []
    for keyword in keywords:
        key_tokens = _tokens(keyword)
        if key_tokens and (keyword.lower() in text or key_tokens.issubset(resume_tokens)):
            matched.append(keyword)
        else:
            missing.append(keyword)

    keyword_coverage = int(round((len(matched) / len(keywords)) * 100)) if keywords else 0

    required_sections = {
        "title": bool(resume.title.strip()),
        "summary": bool(resume.summary.strip()),
        "skills": bool(resume.skills),
        "experience": bool(resume.experience),
        "education": bool(resume.education),
    }
    section_score = int(round(sum(required_sections.values()) / len(required_sections) * 100))

    issues: list[str] = []
    if not resume.title.strip():
        issues.append("Missing resume title/headline.")
    if not resume.summary.strip():
        issues.append("Missing summary/profile section.")
    if not resume.skills:
        issues.append("Missing skills section.")
    if not resume.experience:
        issues.append("Missing experience section.")
    if not resume.education:
        issues.append("Missing education section.")

    # Simple parser-safety checks: reject control characters and very long lines.
    raw = _resume_text(resume)
    control_chars = [ch for ch in raw if ord(ch) < 32 and ch not in "\n\t"]
    long_lines = [line for line in raw.splitlines() if len(line) > 180]
    parseability_score = 100
    if control_chars:
        parseability_score -= 50
        issues.append("Contains control characters that may confuse text parsers.")
    if long_lines:
        parseability_score -= 20
        issues.append("Contains unusually long text lines; parser/readability risk.")
    parseability_score = max(0, parseability_score)

    # Independent weighting: lexical 60%, structure 25%, parser safety 15%.
    score = int(round(
        keyword_coverage * 0.60
        + section_score * 0.25
        + parseability_score * 0.15
    ))
    score = max(0, min(100, score))

    return IndependentATSAudit(
        score=score,
        passed=score >= threshold,
        threshold=threshold,
        keyword_coverage=keyword_coverage,
        section_score=section_score,
        parseability_score=parseability_score,
        matched_keywords=matched,
        missing_keywords=missing,
        issues=issues,
    )

"""Responsibility-first JD qualification policy for Career OS.

This module deliberately separates *capability transfer* from unsupported claims.
A job may use a different implementation/tool from the candidate's prior employer
when the underlying capability is reasonably transferable, while deep specialist
or seniority requirements remain blockers.

The policy is deterministic and provider-neutral so it can be used before/after
LLM fit scoring and tested without an AI provider.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Iterable


@dataclass(frozen=True)
class Evidence:
    text: str
    kind: str = "professional"  # professional | project | knowledge
    employer: str | None = None
    strength: float = 1.0


@dataclass(frozen=True)
class RequirementAssessment:
    requirement: str
    status: str  # MATCH | TRANSFERABLE | LEARNABLE | UNCONFIRMED | BLOCKER | GAP
    reason: str
    evidence: tuple[str, ...] = ()


@dataclass
class ResponsibilityFit:
    score: int
    recommendation: str
    responsibilities_score: int
    skills_score: int
    transferability_score: int
    seniority_score: int
    blockers: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    assessments: list[RequirementAssessment] = field(default_factory=list)


# Capability families. These are deliberately conservative: they allow a related
# implementation to transfer, but never assert hands-on experience with the target
# product/tool unless evidence explicitly says so.
_CAPABILITY_FAMILIES: dict[str, set[str]] = {
    "sql": {"sql", "oracle", "pl/sql", "postgresql", "postgres", "mysql", "mssql", "sql server", "relational database"},
    "linux": {"linux", "unix", "aix", "rhel", "ubuntu", "shell", "bash"},
    "api": {"rest", "rest api", "api", "json", "postman", "web service", "web services"},
    "itsm": {"servicenow", "jira", "jira service management", "jsm", "itsm", "ticketing", "incident management", "problem management"},
    "scripting": {"python", "python scripting", "shell scripting", "automation scripting"},
    "scheduling": {"control-m", "control m", "job scheduling", "batch scheduling", "scheduler"},
    "support": {"application support", "production support", "technical support", "product support", "l1 support", "l2 support", "incident support", "troubleshooting"},
    "operations": {"operations", "service operations", "technical operations", "process improvement", "operational support"},
    "data": {"data validation", "data quality", "data analysis", "reporting", "research", "data operations"},
    "ai_automation": {"ai automation", "ai agents", "agents", "prompt engineering", "prompting", "llm", "llm automation", "workflow automation", "generative ai", "genai"},
}

_HARD_SPECIALIST = {
    "java development", "senior java engineer", "kubernetes administration", "salesforce apex",
    "salesforce lwc", "sap fico", "oracle ebs financials", "workday financials", "infor finacle",
    "cybersecurity incident response", "machine learning engineer", "data scientist",
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9+#./ -]", " ", text.lower())).strip()


def _tokens(text: str) -> set[str]:
    return {x for x in re.findall(r"[a-z0-9+#./-]+", _norm(text)) if len(x) > 1}


def _family_for(requirement: str) -> str | None:
    n = _norm(requirement)
    for family, terms in _CAPABILITY_FAMILIES.items():
        if any(term in n for term in terms):
            return family
    return None


def _evidence_text(evidence: Iterable[Evidence]) -> str:
    return " ".join(_norm(e.text) for e in evidence)


def assess_requirement(requirement: str, evidence: list[Evidence], *, required: bool = True) -> RequirementAssessment:
    n = _norm(requirement)
    corpus = _evidence_text(evidence)

    if not n:
        return RequirementAssessment(requirement, "GAP", "Empty requirement")

    # Exact/near-exact capability evidence wins first.
    if any(tok in corpus for tok in _tokens(n)):
        return RequirementAssessment(requirement, "MATCH", "Direct evidence of the requested capability", tuple(e.text for e in evidence if any(t in _norm(e.text) for t in _tokens(n))[:3]))

    family = _family_for(requirement)
    if family:
        family_terms = _CAPABILITY_FAMILIES[family]
        related = [e for e in evidence if any(term in _norm(e.text) for term in family_terms)]
        if related:
            # Project/knowledge evidence supports transferability, but cannot become
            # professional-experience wording by itself.
            status = "TRANSFERABLE" if family != "ai_automation" or any(e.kind == "project" for e in related) else "LEARNABLE"
            return RequirementAssessment(requirement, status, f"Related {family} capability is evidenced; target implementation is different", tuple(e.text for e in related[:3]))

    if any(s in n for s in _HARD_SPECIALIST):
        return RequirementAssessment(requirement, "BLOCKER" if required else "GAP", "Specialist/deep-domain requirement is not evidenced")

    return RequirementAssessment(requirement, "GAP" if required else "LEARNABLE", "No direct or sufficiently close evidence")


def qualify_job(
    responsibilities: list[str],
    required_skills: list[str],
    preferred_skills: list[str],
    evidence: list[Evidence],
    *,
    years_required: float | None = None,
    years_candidate: float | None = None,
    education_blocker: bool = False,
    location_eligible: bool = True,
) -> ResponsibilityFit:
    assessments: list[RequirementAssessment] = []
    for req in responsibilities:
        assessments.append(assess_requirement(req, evidence, required=True))
    for req in required_skills:
        assessments.append(assess_requirement(req, evidence, required=True))
    for req in preferred_skills:
        assessments.append(assess_requirement(req, evidence, required=False))

    resp = [a for a in assessments if a.requirement in responsibilities]
    skills = [a for a in assessments if a.requirement in required_skills]
    transferable = sum(a.status == "TRANSFERABLE" for a in assessments)
    strong = sum(a.status == "MATCH" for a in assessments)
    required_count = max(1, len(resp) + len(skills))
    covered = strong + transferable

    responsibilities_score = round(100 * (sum(a.status in {"MATCH", "TRANSFERABLE"} for a in resp) / max(1, len(resp))))
    skills_score = round(100 * (sum(a.status in {"MATCH", "TRANSFERABLE"} for a in skills) / max(1, len(skills))))
    transferability_score = round(100 * transferable / max(1, required_count))

    blockers: list[str] = []
    if not location_eligible:
        blockers.append("Location is not eligible")
    if education_blocker:
        blockers.append("Mandatory education requirement is not satisfied")
    blockers.extend(a.requirement for a in assessments if a.status == "BLOCKER")

    seniority_score = 100
    if years_required is not None and years_candidate is not None and years_required > years_candidate:
        ratio = years_candidate / max(years_required, 0.1)
        seniority_score = max(50, round(ratio * 100))
        # Years alone is not an automatic blocker; deep specialist responsibilities
        # or explicit senior-level scope should still be handled separately.

    score = round(
        responsibilities_score * 0.40
        + skills_score * 0.30
        + transferability_score * 0.15
        + seniority_score * 0.15
    )

    gaps = [a.requirement for a in assessments if a.status in {"GAP", "LEARNABLE", "UNCONFIRMED"}]
    if blockers:
        recommendation = "SKIP"
    elif score >= 75 and covered >= max(1, round(required_count * 0.55)):
        recommendation = "APPLY"
    elif score >= 60:
        recommendation = "APPLY-STRETCH"
    else:
        recommendation = "REVIEW"

    return ResponsibilityFit(
        score=max(0, min(100, score)),
        recommendation=recommendation,
        responsibilities_score=responsibilities_score,
        skills_score=skills_score,
        transferability_score=transferability_score,
        seniority_score=seniority_score,
        blockers=blockers,
        gaps=gaps,
        assessments=assessments,
    )

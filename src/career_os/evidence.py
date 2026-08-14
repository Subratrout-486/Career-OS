"""Minimal read-only Career Evidence retrieval helper.

Production mode returns only Professional-Confirmed evidence with
Confirmed-by-User or Confirmed-by-Document status.

Diagnostic mode surfaces related but excluded items with exclusion reasons.
Does not promote unconfirmed evidence. Preserves employer context.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Sequence

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

USABLE_PROFESSIONAL_STATUSES = frozenset({"Professional-Confirmed"})
USABLE_CONFIRMATION_STATUSES = frozenset({"Confirmed-by-User", "Confirmed-by-Document"})
EXPLICIT_REVIEW_MARKERS = (
    "needs-confirmation",
    "needs confirmation",
    "unconfirmed",
    "do not use on resume until confirmed",
)


@dataclass(frozen=True)
class EvidenceItem:
    claim: str
    category: str
    employer: str
    role: str
    employment_period: str
    professional_status: str
    usage_level: str
    context: str
    evidence_source: str
    confirmation_status: str
    safe_wording: str
    unsafe_wording: str = ""
    notes: str = ""

    @property
    def is_usable_professional(self) -> bool:
        status_is_usable = (
            self.professional_status in USABLE_PROFESSIONAL_STATUSES
            and self.confirmation_status in USABLE_CONFIRMATION_STATUSES
        )
        if not status_is_usable:
            return False
        # Some cached/legacy rows carry confirmed select values while their
        # context or safe wording still explicitly says the claim is pending
        # confirmation. The explicit review marker is authoritative; never
        # promote such a row into fit, resume, or ATS evidence.
        review_text = " ".join(
            value for value in (self.context, self.safe_wording, self.notes) if value
        ).lower()
        return not any(marker in review_text for marker in EXPLICIT_REVIEW_MARKERS)

    def searchable_text(self) -> str:
        parts = [
            self.claim,
            self.category,
            self.employer,
            self.role,
            self.context,
            self.safe_wording,
            self.notes,
        ]
        return " ".join(p for p in parts if p).lower()


@dataclass
class MatchedEvidence:
    item: EvidenceItem
    match_reason: str
    score: float = 0.0

    def as_dict(self) -> dict:
        return {
            "claim": self.item.claim,
            "category": self.item.category,
            "employer": self.item.employer,
            "role": self.item.role,
            "employment_period": self.item.employment_period,
            "professional_status": self.item.professional_status,
            "usage_level": self.item.usage_level,
            "context": self.item.context,
            "evidence_source": self.item.evidence_source,
            "confirmation_status": self.item.confirmation_status,
            "safe_wording": self.item.safe_wording,
            "match_reason": self.match_reason,
            "score": self.score,
        }


@dataclass
class ExcludedEvidence:
    item: EvidenceItem
    exclusion_reason: str
    match_reason: str
    score: float = 0.0

    def as_dict(self) -> dict:
        return {
            "claim": self.item.claim,
            "employer": self.item.employer,
            "professional_status": self.item.professional_status,
            "confirmation_status": self.item.confirmation_status,
            "match_reason": self.match_reason,
            "exclusion_reason": self.exclusion_reason,
            "score": self.score,
        }


@dataclass
class RetrievalResult:
    requirement: str
    matched: list[MatchedEvidence] = field(default_factory=list)
    excluded: list[ExcludedEvidence] = field(default_factory=list)
    has_usable_evidence: bool = False
    has_related_unconfirmed: bool = False

    def as_dict(self) -> dict:
        return {
            "requirement": self.requirement,
            "has_usable_evidence": self.has_usable_evidence,
            "has_related_unconfirmed": self.has_related_unconfirmed,
            "matched": [m.as_dict() for m in self.matched],
            "excluded": [e.as_dict() for e in self.excluded],
            "summary": self.summary(),
        }

    def summary(self) -> str:
        if self.has_usable_evidence:
            employers = sorted({m.item.employer for m in self.matched})
            return (
                f"{len(self.matched)} confirmed professional evidence item(s) "
                f"across employer(s): {', '.join(employers)}"
            )
        if self.has_related_unconfirmed:
            return (
                "NO CONFIRMED PROFESSIONAL EVIDENCE — "
                f"{len(self.excluded)} related item(s) exist but are excluded "
                "(unconfirmed / self-directed / rejected)."
            )
        return "NO EVIDENCE FOUND — no related items in the Career Evidence Vault."


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = text.replace("&", " and ")
    text = re.sub(r"[^\w\s/\-+.]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with",
    "at", "by", "from", "as", "is", "are", "was", "were", "be", "been",
    "this", "that", "these", "those", "it", "its", "into", "over", "under",
    "using", "use", "used", "via", "per", "vs", "etc",
})

# Generic words that alone should not establish a match.
WEAK_TOKENS = frozenset({
    "operations", "operation", "support", "management", "process", "system",
    "systems", "application", "applications", "data", "work", "role",
    "experience", "knowledge", "skills", "skill", "tools", "tool",
    "technical", "professional", "business", "service", "services",
    "escalation", "triage", "validation", "documentation",
})

# Seed terms that trigger synonym expansion for each group (must appear in requirement).
SYNONYM_SEEDS: list[tuple[frozenset[str], frozenset[str]]] = [
    (frozenset({"servicenow", "itsm"}), frozenset({"servicenow", "itsm", "incident", "ticket", "tickets", "triage", "escalation", "sla"})),
    (frozenset({"incident management", "ticket management", "incident", "ticket", "tickets", "rca"}), frozenset({"incident management", "ticket management", "ticket triage", "incident handling", "rca", "root cause", "incident", "ticket", "tickets", "sla"})),
    (frozenset({"sql", "oracle", "pl/sql", "plsql", "database"}), frozenset({"sql", "oracle", "pl/sql", "plsql", "database", "db", "query", "queries"})),
    (frozenset({"aws", "cloud"}), frozenset({"aws", "cloud", "cloud application", "cloud support", "cloud environment"})),
    (frozenset({"rest", "api", "apis", "json", "postman"}), frozenset({"rest", "api", "apis", "json", "postman", "integration"})),
    (frozenset({"linux", "unix"}), frozenset({"linux", "unix", "shell"})),
    (frozenset({"control-m", "controlm", "batch"}), frozenset({"control-m", "controlm", "batch", "scheduled job", "job scheduler"})),
    (frozenset({"uat", "release validation"}), frozenset({"uat", "release validation", "release", "defect"})),
    (frozenset({"sop", "runbook", "runbooks"}), frozenset({"sop", "runbook", "runbooks", "documentation", "knowledge"})),
    (frozenset({"l1", "l2", "product support", "application support", "technical support", "customer support", "troubleshooting", "troubleshoot"}), frozenset({"l1", "l2", "product support", "application support", "technical support", "customer support", "troubleshooting", "troubleshoot"})),
    (frozenset({"corporate governance", "shareholder", "sec", "10-k", "10-q", "proxy", "filings"}), frozenset({"corporate governance", "shareholder", "activism", "sec", "10-k", "10-q", "proxy", "filings", "research"})),
    (frozenset({"group reservation", "group reservations", "event operations", "event management", "proposals", "contracts", "proforma"}), frozenset({"group reservation", "group reservations", "event operations", "event management", "proposals", "contracts", "proforma"})),
    (frozenset({"excel", "spreadsheet"}), frozenset({"excel", "advanced excel", "spreadsheet", "data validation"})),
    (frozenset({"power bi", "powerbi", "power query", "dashboard", "dashboards"}), frozenset({"power bi", "powerbi", "dashboard", "dashboards", "power query"})),
    (frozenset({"python"}), frozenset({"python", "scripting"})),
    (frozenset({"tcp/ip", "dns", "dhcp", "wifi", "wi-fi", "vpn", "modem", "connectivity", "networking", "comcast", "xfinity"}), frozenset({"tcp/ip", "dns", "dhcp", "wifi", "wi-fi", "vpn", "modem", "connectivity", "networking", "comcast", "xfinity"})),
    (frozenset({"crm", "case management", "ticketing"}), frozenset({"crm", "case management", "ticketing"})),
]


def _expand_terms(requirement: str) -> set[str]:
    """Expand requirement into tokens + multi-word phrases + synonym relatives."""
    norm = _normalize(requirement)
    tokens = {t for t in norm.split() if t not in STOPWORDS}
    phrases: set[str] = set()
    if norm:
        phrases.add(norm)
    words = [w for w in norm.split() if w not in STOPWORDS]
    for i in range(len(words)):
        for j in range(i + 1, min(i + 4, len(words) + 1)):
            phrases.add(" ".join(words[i:j]))

    expanded = set(tokens) | phrases
    for seeds, group in SYNONYM_SEEDS:
        if any(
            seed == norm
            or seed in tokens
            or seed in phrases
            or (len(seed) > 3 and seed in norm)
            for seed in seeds
        ):
            expanded |= {t for t in group if t not in STOPWORDS}
    return expanded


def _score_item(requirement: str, item: EvidenceItem) -> tuple[float, str]:
    """Return (score, human-readable match reason). Score 0 = no match."""
    expanded = _expand_terms(requirement)
    haystack = item.searchable_text()
    norm_req = _normalize(requirement)
    claim_norm = _normalize(item.claim)

    hits: list[str] = []
    score = 0.0
    strong_hits = 0

    # Exact / near-exact phrase in claim or safe wording
    if norm_req and len(norm_req) > 8 and norm_req in haystack:
        score += 5.0
        strong_hits += 1
        hits.append("requirement phrase present in evidence text")

    # Token / synonym hits
    for term in sorted(expanded, key=len, reverse=True):
        if len(term) < 3 or term in STOPWORDS:
            continue
        pattern = r"(?<!\w)" + re.escape(term) + r"(?!\w)"
        if not (re.search(pattern, haystack) or term in haystack):
            continue

        is_weak = term in WEAK_TOKENS and len(term.split()) == 1
        weight = 2.0 if len(term.split()) > 1 else 1.0
        if term in claim_norm:
            weight += 1.5
            strong_hits += 1
        elif not is_weak:
            strong_hits += 1
        if is_weak:
            weight *= 0.2

        score += weight
        if term not in hits and len(hits) < 8 and not is_weak:
            hits.append(term)

    # Require at least one strong (non-weak) hit and a meaningful score
    if strong_hits == 0 or score < 1.5:
        return 0.0, ""

    reason = ", ".join(hits[:6]) if hits else "related terms"
    return score, reason


def _exclusion_reason(item: EvidenceItem) -> str:
    reasons = []
    if item.professional_status not in USABLE_PROFESSIONAL_STATUSES:
        reasons.append(f"Professional Status={item.professional_status}")
    if item.confirmation_status not in USABLE_CONFIRMATION_STATUSES:
        reasons.append(f"Confirmation Status={item.confirmation_status}")
    review_text = " ".join(
        value for value in (item.context, item.safe_wording, item.notes) if value
    ).lower()
    if any(marker in review_text for marker in EXPLICIT_REVIEW_MARKERS):
        reasons.append("explicit Needs-Confirmation / do-not-use marker")
    if not reasons:
        reasons.append("filtered by truth rules")
    return "; ".join(reasons)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def retrieve_evidence(
    requirement: str,
    vault: Sequence[EvidenceItem],
    *,
    employer: str | None = None,
    include_diagnostic: bool = False,
    min_score: float = 1.5,
) -> RetrievalResult:
    """Search the Career Evidence Vault for items supporting a JD requirement.

    Production defaults (include_diagnostic=False):
      - Only Professional-Confirmed + Confirmed-by-User/Document items are usable.
      - Employer filter applied when provided.
      - Items from different employers are returned as separate matches.

    Diagnostic mode also returns related but excluded items with reasons.
    """
    result = RetrievalResult(requirement=requirement)
    if not requirement or not requirement.strip():
        return result

    employer_norm = employer.lower().strip() if employer else None

    candidates: list[tuple[EvidenceItem, float, str]] = []
    for item in vault:
        if employer_norm and employer_norm not in item.employer.lower():
            continue
        score, reason = _score_item(requirement, item)
        if score >= min_score:
            candidates.append((item, score, reason))

    candidates.sort(key=lambda x: (-x[1], x[0].employer, x[0].claim))

    for item, score, reason in candidates:
        if item.is_usable_professional:
            result.matched.append(
                MatchedEvidence(item=item, match_reason=reason, score=round(score, 2))
            )
        else:
            result.excluded.append(
                ExcludedEvidence(
                    item=item,
                    exclusion_reason=_exclusion_reason(item),
                    match_reason=reason,
                    score=round(score, 2),
                )
            )

    result.has_usable_evidence = len(result.matched) > 0
    result.has_related_unconfirmed = any(
        not e.item.is_usable_professional for e in result.excluded
    )
    if not include_diagnostic:
        # Keep excluded only for summary distinction; clear detail for production callers
        # who did not request diagnostics. has_related_unconfirmed remains accurate.
        pass

    return result


def format_retrieval(result: RetrievalResult, *, show_excluded: bool = True) -> str:
    """Human-readable report for validation / review."""
    lines = [f"JD REQUIREMENT: {result.requirement}", f"SUMMARY: {result.summary()}", ""]
    if result.matched:
        lines.append("→ MATCHED EVIDENCE (usable professional):")
        for m in result.matched:
            lines.append(f"  • Claim: {m.item.claim}")
            lines.append(f"    Employer: {m.item.employer}")
            lines.append(
                f"    Status: {m.item.professional_status} / {m.item.confirmation_status}"
            )
            lines.append(f"    Why it matches: {m.match_reason}")
            lines.append(f"    Safe wording: {m.item.safe_wording}")
            lines.append("")
    if show_excluded and result.excluded:
        lines.append("→ RELATED EVIDENCE (excluded from professional use):")
        for e in result.excluded:
            lines.append(f"  • Claim: {e.item.claim}")
            lines.append(f"    Employer: {e.item.employer}")
            lines.append(
                f"    Status: {e.item.professional_status} / {e.item.confirmation_status}"
            )
            lines.append(f"    Exclusion reason: {e.exclusion_reason}")
            lines.append(f"    Why related: {e.match_reason}")
            lines.append("")
    if not result.matched and not result.excluded:
        lines.append("→ No related items found in the vault.")
    return "\n".join(lines)

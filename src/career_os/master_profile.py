"""Immutable Master Career Profile contracts.

The existing Evidence Vault remains the production source of truth. These
contracts provide a safe projection and proposal workflow for the browser
application: proposed facts are unverified by default, and approval creates a
new profile version instead of mutating historical facts.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


FactStatus = Literal["VERIFIED", "UNVERIFIED", "REJECTED"]
FactCategory = Literal[
    "employment", "project", "skill", "tool", "certification", "education",
    "achievement", "exposure", "preference", "other",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CareerFact(BaseModel):
    id: str
    category: FactCategory
    subject: str
    value: str
    source: str
    provenance: list[str] = Field(default_factory=list)
    confidence: float | None = None
    status: FactStatus = "UNVERIFIED"
    created_at: str = Field(default_factory=now_iso)
    supersedes_fact_id: str | None = None


class MasterCareerProfile(BaseModel):
    profile_id: str = "master"
    version: int = 1
    facts: tuple[CareerFact, ...] = ()
    preferences: dict[str, Any] = Field(default_factory=dict)
    source: str = "career-evidence-vault"
    updated_at: str = Field(default_factory=now_iso)

    def verified_facts(self) -> tuple[CareerFact, ...]:
        return tuple(fact for fact in self.facts if fact.status == "VERIFIED")

    def propose_fact(self, fact: CareerFact) -> "MasterCareerProfile":
        """Return a new profile with a non-authoritative proposed fact."""
        proposed = fact.model_copy(update={"status": "UNVERIFIED"})
        return self.model_copy(
            update={
                "version": self.version + 1,
                "facts": (*self.facts, proposed),
                "updated_at": now_iso(),
            }
        )

    def approve_fact(self, fact_id: str, *, approver: str) -> "MasterCareerProfile":
        """Return a new profile version with one fact verified.

        ``approver`` is recorded in provenance so a factual change remains
        explainable. The original profile object and its facts are unchanged.
        """
        found = False
        updated: list[CareerFact] = []
        for fact in self.facts:
            if fact.id != fact_id:
                updated.append(fact)
                continue
            found = True
            updated.append(fact.model_copy(update={
                "status": "VERIFIED",
                "provenance": (*fact.provenance, f"approved-by:{approver}"),
            }))
        if not found:
            raise KeyError(f"Unknown career fact: {fact_id}")
        return self.model_copy(update={"version": self.version + 1, "facts": tuple(updated), "updated_at": now_iso()})

    def reject_fact(self, fact_id: str, *, rejector: str) -> "MasterCareerProfile":
        """Return a new profile version marking a proposal rejected."""
        found = False
        updated: list[CareerFact] = []
        for fact in self.facts:
            if fact.id != fact_id:
                updated.append(fact)
                continue
            found = True
            updated.append(fact.model_copy(update={
                "status": "REJECTED",
                "provenance": (*fact.provenance, f"rejected-by:{rejector}"),
            }))
        if not found:
            raise KeyError(f"Unknown career fact: {fact_id}")
        return self.model_copy(update={"version": self.version + 1, "facts": tuple(updated), "updated_at": now_iso()})

    def facts_for_resume(self) -> tuple[CareerFact, ...]:
        """Expose only verified facts to resume generation callers."""
        return self.verified_facts()

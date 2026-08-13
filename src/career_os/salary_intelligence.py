"""Source-first, advisory salary intelligence for Career OS.

The module never invents compensation. It accepts explicit, dated observations,
keeps every source URL, and returns a draft-only SalaryIntelligence model that
must be reviewed by the user before any salary/CTC field is answered.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date
from statistics import median
from typing import Iterable

from .models import SalaryIntelligence


@dataclass(frozen=True)
class SalaryObservation:
    source_name: str
    source_url: str
    verified_on: str
    min_lpa: float | None = None
    max_lpa: float | None = None
    median_lpa: float | None = None
    currency: str = "INR"
    period: str = "annual"
    notes: str = ""

    def usable(self) -> bool:
        try:
            date.fromisoformat(self.verified_on)
        except (TypeError, ValueError):
            return False
        return bool(self.source_name.strip() and self.source_url.startswith("http")) and any(
            value is not None and value > 0
            for value in (self.min_lpa, self.max_lpa, self.median_lpa)
        )


def calculate_salary_intelligence(
    observations: Iterable[SalaryObservation],
    *,
    confirmed_experience_years: float | None = None,
) -> SalaryIntelligence:
    usable = [item for item in observations if item.usable() and item.currency == "INR" and item.period == "annual"]
    if not usable:
        return SalaryIntelligence(
            confidence="Low",
            researched_at=date.today().isoformat(),
            method="No usable dated source observations; user input required.",
            notes="DRAFT ONLY. Do not answer compensation questions from this record without explicit user confirmation.",
        )

    lows = [item.min_lpa for item in usable if item.min_lpa is not None]
    highs = [item.max_lpa for item in usable if item.max_lpa is not None]
    medians = [item.median_lpa for item in usable if item.median_lpa is not None]
    centers = medians or [((min(lows) if lows else 0) + (max(highs) if highs else 0)) / 2]
    market_low = min(lows + medians) if lows or medians else None
    market_high = max(highs + medians) if highs or medians else None
    center = float(median(centers))
    factor = 0.95 if confirmed_experience_years is not None and confirmed_experience_years < 3 else 1.0
    ask = round(center * factor, 2)
    stretch = round((market_high or center) * factor, 2)
    minimum = round((market_low or center) * factor, 2)
    confidence = "Medium" if len(usable) >= 2 else "Low"
    return SalaryIntelligence(
        market_low_lpa=market_low,
        market_high_lpa=market_high,
        recommended_ask_lpa=ask,
        stretch_target_lpa=stretch,
        minimum_discussion_lpa=minimum,
        confidence=confidence,
        researched_at=date.today().isoformat(),
        method="Median of explicit dated third-party observations; advisory only.",
        sources=[asdict(item) for item in usable],
        notes="DRAFT ONLY. Confirm employer band, total compensation, experience, and the user's target before answering Expected CTC or salary questions.",
    )

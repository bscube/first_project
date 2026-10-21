from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from .models import ICP, Account, Signal

# How much one fresh signal of each kind is worth (intent is capped at 100).
SIGNAL_WEIGHTS = {
    "funding": 30,
    "pain_point": 30,
    "leadership_change": 25,
    "hiring_gtm": 20,
    "expansion": 15,
    "tech_change": 10,
    "noise": 0,
}
HALF_LIFE_DAYS = 30
TIER_CUTOFFS = [("A", 70), ("B", 50), ("C", 0)]


@dataclass
class ScoredAccount:
    account: Account
    fit: float
    intent: float
    total: float
    tier: str
    reasons: list[str]


def fit_score(account: Account, icp: ICP) -> tuple[float, list[str]]:
    reasons = []
    vertical = icp.verticals.get(account.industry)
    v = vertical.score if vertical else 0
    if vertical:
        reasons.append(f"{account.industry} (value {vertical.deal_value}/5, access {vertical.accessibility}/5)")
    else:
        reasons.append(f"{account.industry} is outside the ICP")

    lo, hi = icp.employee_range
    # Lose fit gradually outside the band instead of falling off a cliff at its edge.
    if account.employees < lo:
        size = 100 * account.employees / lo
    elif account.employees > hi:
        size = 100 * hi / account.employees
    else:
        size = 100
    if size < 100:
        reasons.append(f"{account.employees} employees is outside {lo}-{hi}")

    region = 100 if account.region in icp.regions else 0
    if not region:
        reasons.append(f"{account.region} is not a target region")

    return round(0.5 * v + 0.3 * size + 0.2 * region, 1), reasons


def intent_score(signals: list[Signal], as_of: date) -> tuple[float, list[str]]:
    total, reasons = 0.0, []
    for s in sorted(signals, key=lambda s: s.date, reverse=True):
        age = (as_of - s.date).days
        if age < 0 or s.category == "noise":
            continue
        points = SIGNAL_WEIGHTS.get(s.category, 0) * 0.5 ** (age / HALF_LIFE_DAYS)
        total += points
        reasons.append(f"{s.category} {age}d ago (+{points:.0f})")
    return round(min(total, 100), 1), reasons


def tier_for(total: float) -> str:
    return next(name for name, cutoff in TIER_CUTOFFS if total >= cutoff)


def score_accounts(accounts: list[Account], signals: list[Signal], icp: ICP, as_of: date) -> list[ScoredAccount]:
    by_domain: dict[str, list[Signal]] = defaultdict(list)
    for s in signals:
        by_domain[s.domain].append(s)

    scored = []
    for a in accounts:
        fit, fit_reasons = fit_score(a, icp)
        intent, intent_reasons = intent_score(by_domain[a.domain], as_of)
        total = round(icp.weights["fit"] * fit + icp.weights["intent"] * intent, 1)
        scored.append(ScoredAccount(a, fit, intent, total, tier_for(total), fit_reasons + intent_reasons))
    return sorted(scored, key=lambda s: s.total, reverse=True)


@dataclass
class SegmentSummary:
    industry: str
    accounts: int
    tier_a: int
    avg_score: float
    vertical_score: float


def summarise_segments(scored: list[ScoredAccount], icp: ICP) -> list[SegmentSummary]:
    """Answer "which segment do we go after first?" from the scored list."""
    groups: dict[str, list[ScoredAccount]] = defaultdict(list)
    for s in scored:
        groups[s.account.industry].append(s)
    rows = [
        SegmentSummary(
            industry=industry,
            accounts=len(items),
            tier_a=sum(s.tier == "A" for s in items),
            avg_score=round(sum(s.total for s in items) / len(items), 1),
            vertical_score=icp.verticals[industry].score if industry in icp.verticals else 0,
        )
        for industry, items in groups.items()
    ]
    return sorted(rows, key=lambda r: (r.tier_a, r.avg_score), reverse=True)

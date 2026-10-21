"""Check the score against real outcomes and tune the fit/intent weights.

Takes a CSV of past opportunities (domain, outcome = won | lost) and asks:
does a higher score actually mean a higher chance of winning?
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .scoring import ScoredAccount


def load_outcomes(path: str | Path) -> dict[str, bool]:
    with open(path, newline="") as f:
        return {row["domain"].strip().lower(): row["outcome"].strip().lower() == "won" for row in csv.DictReader(f)}


def auc(pairs: list[tuple[float, bool]]) -> float | None:
    """Chance that a random won deal outscores a random lost one (0.5 = coin flip)."""
    won = [s for s, w in pairs if w]
    lost = [s for s, w in pairs if not w]
    if not won or not lost:
        return None
    wins = sum(1.0 if w > l else 0.5 if w == l else 0.0 for w in won for l in lost)
    return round(wins / (len(won) * len(lost)), 3)


@dataclass
class TierRow:
    tier: str
    deals: int
    won: int

    @property
    def win_rate(self) -> float:
        return round(100 * self.won / self.deals, 1) if self.deals else 0.0


@dataclass
class BacktestResult:
    matched: int
    current_weight: float
    current_auc: float | None
    tiers: list[TierRow]
    sweep: list[tuple[float, float | None]]  # (fit weight, AUC)

    @property
    def best(self) -> tuple[float, float | None]:
        scored = [row for row in self.sweep if row[1] is not None]
        # Ties go to the weight closest to the current one, so we only move when it helps.
        return max(scored, key=lambda r: (r[1], -abs(r[0] - self.current_weight))) if scored else (self.current_weight, None)


def _rescore(s: ScoredAccount, fit_weight: float) -> float:
    return fit_weight * s.fit + (1 - fit_weight) * s.intent


def backtest(scored: list[ScoredAccount], outcomes: dict[str, bool], fit_weight: float) -> BacktestResult:
    matched = [s for s in scored if s.account.domain in outcomes]
    pairs = [(s.total, outcomes[s.account.domain]) for s in matched]

    tiers = []
    for name in ("A", "B", "C"):
        in_tier = [s for s in matched if s.tier == name]
        tiers.append(TierRow(name, len(in_tier), sum(outcomes[s.account.domain] for s in in_tier)))

    sweep = []
    for step in range(11):
        w = step / 10
        sweep.append((w, auc([(_rescore(s, w), outcomes[s.account.domain]) for s in matched])))

    return BacktestResult(len(matched), fit_weight, auc(pairs), tiers, sweep)

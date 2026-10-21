from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


@dataclass
class Account:
    domain: str
    name: str
    industry: str
    employees: int
    region: str


@dataclass
class Signal:
    id: str
    domain: str
    date: date
    source: str
    text: str
    category: str = "unclassified"


@dataclass
class Vertical:
    """One row of the vertical prioritisation model (both scores are 1-5)."""

    deal_value: int
    accessibility: int

    @property
    def score(self) -> float:
        # 0-100: a big deal you can't reach is worth as little as an easy one that pays nothing.
        return self.deal_value * self.accessibility / 25 * 100


@dataclass
class ICP:
    verticals: dict[str, Vertical]
    employee_range: tuple[int, int]
    regions: list[str]
    weights: dict[str, float] = field(default_factory=lambda: {"fit": 0.6, "intent": 0.4})


def load_accounts(path: str | Path) -> list[Account]:
    with open(path, newline="") as f:
        return [
            Account(
                domain=row["domain"].strip().lower(),
                name=row["name"].strip(),
                industry=row["industry"].strip(),
                employees=int(row["employees"]),
                region=row["region"].strip(),
            )
            for row in csv.DictReader(f)
        ]


def load_signals(path: str | Path) -> list[Signal]:
    with open(path, newline="") as f:
        return [
            Signal(
                id=row["id"].strip(),
                domain=row["domain"].strip().lower(),
                date=date.fromisoformat(row["date"].strip()),
                source=row["source"].strip(),
                text=row["text"].strip(),
            )
            for row in csv.DictReader(f)
        ]


def load_icp(path: str | Path) -> ICP:
    raw = json.loads(Path(path).read_text())
    return ICP(
        verticals={name: Vertical(**v) for name, v in raw["verticals"].items()},
        employee_range=tuple(raw["employee_range"]),
        regions=raw["regions"],
        weights=raw.get("weights", {"fit": 0.6, "intent": 0.4}),
    )

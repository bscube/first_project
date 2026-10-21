from __future__ import annotations

import argparse
import csv
import os
from datetime import date

from .classify import classify
from .models import load_accounts, load_icp, load_signals
from .scoring import score_accounts, summarise_segments


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="signal_scout", description="Rank accounts by ICP fit and buying signals.")
    p.add_argument("--accounts", default="data/accounts.csv")
    p.add_argument("--signals", default="data/signals.csv")
    p.add_argument("--icp", default="data/icp.json")
    p.add_argument("--as-of", type=date.fromisoformat, default=date.today(), help="score as of this date (YYYY-MM-DD)")
    p.add_argument("--out", help="write the ranked list to this CSV")
    p.add_argument("--top", type=int, default=10)
    llm = p.add_mutually_exclusive_group()
    llm.add_argument("--llm", action="store_true", help="classify signals with Claude")
    llm.add_argument("--rules", action="store_true", help="classify signals with keyword rules only")
    args = p.parse_args(argv)

    use_llm = args.llm or (not args.rules and bool(os.environ.get("ANTHROPIC_API_KEY")))
    accounts = load_accounts(args.accounts)
    signals = classify(load_signals(args.signals), use_llm=use_llm)
    icp = load_icp(args.icp)
    scored = score_accounts(accounts, signals, icp, args.as_of)

    print(f"Classifier: {'Claude' if use_llm else 'keyword rules'} | as of {args.as_of}\n")
    print(f"{'#':>2}  {'Account':<22} {'Industry':<24} {'Fit':>5} {'Intent':>6} {'Score':>6}  Tier")
    for i, s in enumerate(scored[: args.top], 1):
        print(f"{i:>2}  {s.account.name:<22} {s.account.industry:<24} {s.fit:>5} {s.intent:>6} {s.total:>6}  {s.tier}")
        print(f"    {'; '.join(s.reasons)}")

    print(f"\n{'Segment':<24} {'Accts':>5} {'Tier A':>6} {'Avg':>6} {'Vertical':>8}")
    for r in summarise_segments(scored, icp):
        print(f"{r.industry:<24} {r.accounts:>5} {r.tier_a:>6} {r.avg_score:>6} {r.vertical_score:>8.0f}")

    if args.out:
        with open(args.out, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["rank", "domain", "name", "industry", "fit", "intent", "score", "tier", "reasons"])
            for i, s in enumerate(scored, 1):
                w.writerow([i, s.account.domain, s.account.name, s.account.industry,
                            s.fit, s.intent, s.total, s.tier, " | ".join(s.reasons)])
        print(f"\nWrote {len(scored)} accounts to {args.out}")


if __name__ == "__main__":
    main()

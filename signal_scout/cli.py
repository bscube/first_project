from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import date, timedelta

from .alerts import post_to_slack, slack_payload
from .backtest import backtest, load_outcomes
from .classify import classify
from .ingest import ingest, merge_into_csv
from .models import load_accounts, load_icp, load_signals
from .scoring import score_accounts, summarise_segments

COMMANDS = ("score", "ingest", "backtest")


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--accounts", default="data/accounts.csv")
    p.add_argument("--signals", default="data/signals.csv")
    p.add_argument("--icp", default="data/icp.json")
    p.add_argument("--as-of", type=date.fromisoformat, default=date.today(), help="score as of this date (YYYY-MM-DD)")
    llm = p.add_mutually_exclusive_group()
    llm.add_argument("--llm", action="store_true", help="classify signals with Claude")
    llm.add_argument("--rules", action="store_true", help="classify signals with keyword rules only")


def _score(args):
    use_llm = args.llm or (not args.rules and bool(os.environ.get("ANTHROPIC_API_KEY")))
    icp = load_icp(args.icp)
    signals = classify(load_signals(args.signals), use_llm=use_llm)
    scored = score_accounts(load_accounts(args.accounts), signals, icp, args.as_of)
    return scored, icp, use_llm


def cmd_score(args) -> None:
    scored, icp, use_llm = _score(args)

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

    if args.slack or args.slack_dry_run:
        payload = slack_payload(scored, tiers=tuple(args.slack_tiers))
        if payload is None:
            print(f"\nNo tier {'/'.join(args.slack_tiers)} accounts, nothing sent to Slack.")
        elif args.slack_dry_run:
            print("\nSlack payload (dry run):\n" + json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            webhook = os.environ.get("SLACK_WEBHOOK_URL")
            if not webhook:
                sys.exit("--slack needs SLACK_WEBHOOK_URL set to an incoming-webhook URL")
            post_to_slack(webhook, payload)
            print(f"\nPosted {len(payload['blocks']) - 1} account(s) to Slack.")


def cmd_ingest(args) -> None:
    accounts = load_accounts(args.accounts)
    since = date.today() - timedelta(days=args.days)
    print(f"Fetching news for {len(accounts)} accounts since {since}...")
    signals, errors = ingest(accounts, since=since)
    added = merge_into_csv(args.signals, signals)
    print(f"Found {len(signals)} matching items, added {added} new signal(s) to {args.signals}")
    for e in errors:
        print(f"  skipped {e}", file=sys.stderr)


def cmd_backtest(args) -> None:
    scored, icp, _ = _score(args)
    r = backtest(scored, load_outcomes(args.outcomes), icp.weights["fit"])
    if r.matched == 0:
        sys.exit("No outcome rows matched an account domain.")

    print(f"Backtest on {r.matched} closed deals\n")
    print(f"{'Tier':<5} {'Deals':>5} {'Won':>4} {'Win rate':>9}")
    for t in r.tiers:
        print(f"{t.tier:<5} {t.deals:>5} {t.won:>4} {t.win_rate:>8}%")

    print(f"\nAUC at current weights (fit {r.current_weight:.1f}): {r.current_auc}")
    print("  (1.0 = every won deal outscored every lost one, 0.5 = no better than a coin flip)\n")
    print(f"{'Fit weight':>10} {'AUC':>6}")
    for w, a in r.sweep:
        marker = "  <- current" if abs(w - r.current_weight) < 1e-9 else ""
        print(f"{w:>10.1f} {a if a is not None else '-':>6}{marker}")
    best_w, best_auc = r.best
    if best_auc is not None and r.current_auc is not None and best_auc > r.current_auc:
        print(f"\nSuggestion: set weights to fit {best_w:.1f} / intent {1 - best_w:.1f} in {args.icp} "
              f"(AUC {r.current_auc} -> {best_auc}).")
    else:
        print("\nCurrent weights are already as good as any in the sweep.")
    if r.matched < 30:
        print(f"Note: {r.matched} deals is a small sample, so treat this as directional.")


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    # `python -m signal_scout --rules` keeps working: no subcommand means score.
    if not argv or argv[0] not in COMMANDS + ("-h", "--help"):
        argv = ["score", *argv]

    p = argparse.ArgumentParser(prog="signal_scout", description="Rank accounts by ICP fit and buying signals.")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("score", help="rank accounts (default)")
    _add_common(s)
    s.add_argument("--out", help="write the ranked list to this CSV")
    s.add_argument("--top", type=int, default=10)
    s.add_argument("--slack", action="store_true", help="post top accounts to SLACK_WEBHOOK_URL")
    s.add_argument("--slack-dry-run", action="store_true", help="print the Slack message instead of sending it")
    s.add_argument("--slack-tiers", nargs="+", default=["A"], choices=["A", "B", "C"])
    s.set_defaults(func=cmd_score)

    i = sub.add_parser("ingest", help="pull recent news for every account into the signals CSV")
    i.add_argument("--accounts", default="data/accounts.csv")
    i.add_argument("--signals", default="data/signals.csv")
    i.add_argument("--days", type=int, default=30, help="only keep items from the last N days")
    i.set_defaults(func=cmd_ingest)

    b = sub.add_parser("backtest", help="check scores against won/lost deals and tune weights")
    _add_common(b)
    b.add_argument("--outcomes", default="data/outcomes.csv")
    b.set_defaults(func=cmd_backtest)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()

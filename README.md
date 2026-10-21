# Signal Scout

**Rank B2B accounts by how well they fit your ICP and how loudly they're signalling intent right now.**

Most outbound lists are sorted by firmographics alone. Signal Scout adds the second half: funding rounds, new
sales leaders, GTM hiring, expansion news and prospects publicly describing the pain you solve. It decays each
signal by age and combines the two into one score, a tier, and a plain-English reason for every account. It
then rolls the results up by segment, so you can see which vertical to go after first.

It's a small, readable version of the signal pipelines I've built for GTM teams (scrapers → LLM classifier →
scored alerts). It's packaged here so the scoring logic is easy to inspect and adapt.

## How the score works

```
score = 0.6 × fit + 0.4 × intent          (weights set in data/icp.json)
```

**Fit (0–100)** comes from a vertical prioritisation model, not just a yes/no industry list.

| Component | Weight | Logic |
|---|---|---|
| Vertical | 50% | `deal_value × buyer_accessibility` (each 1–5). A huge deal you can't reach scores as low as an easy one that pays nothing. |
| Company size | 30% | 100 inside the employee band, falling off proportionally outside it (no cliff edge). |
| Region | 20% | Target region or not. |

**Intent (0–100, capped)** adds up recent signals, each halving in value every 30 days.

| Signal | Points when fresh |
|---|---|
| `funding`, `pain_point` | 30 |
| `leadership_change` | 25 |
| `hiring_gtm` | 20 |
| `expansion` | 15 |
| `tech_change` | 10 |
| `noise` | 0 |

**Tiers:** A ≥ 70, B ≥ 50, C below that.

## Signal classification

Raw signal text (a LinkedIn post, a news headline, a job listing) has to become a category first.

- **Claude** (`--llm`, or automatically when `ANTHROPIC_API_KEY` is set): signals are labelled in batches of 40
  using structured JSON output, so every response matches the category schema. Any signal the model skips or
  declines falls back to the rules.
- **Keyword rules** (`--rules`): a regex baseline that needs no API key, so the project runs anywhere.

## Quick start

```bash
pip install -r requirements.txt

# Runs on the sample data in data/ with keyword rules
python -m signal_scout --rules --as-of 2026-10-21

# Classify signals with Claude and export the full ranked list
export ANTHROPIC_API_KEY=...
python -m signal_scout --llm --out ranked.csv

# Tests
python -m pytest
```

## The full pipeline: ingest → score → alert → backtest

```bash
# 1. Pull the last 30 days of news for every account into data/signals.csv
python -m signal_scout ingest --days 30

# 2. Score, and post tier-A accounts to Slack (preview first with --slack-dry-run)
export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
python -m signal_scout score --llm --slack

# 3. Check the scores against closed deals and tune the weights
python -m signal_scout backtest --outcomes data/outcomes.csv
```

**Ingest** builds a Google News search feed for each account name. It keeps only headlines that mention the
company as a whole word (so "Acme" doesn't match "Acmeville"), and appends new items to the signals CSV. Item
ids come from a hash of the link, so re-running never duplicates a signal. A feed that times out is skipped
and reported; the run carries on. Any RSS or Atom feed is parsed the same way.

**Alerts** send one Slack message per run, listing each picked account with its score and the reasons
behind it, so a rep knows *why* to call today, not just *who*. Use `--slack-tiers A B` to include B-tier.

**Backtest** answers the question every scoring model should face: *does a higher score actually mean
a higher chance of winning?*

```
Tier  Deals  Won  Win rate
A         1    1    100.0%
B         5    4     80.0%
C         6    0      0.0%

AUC at current weights (fit 0.6): 0.943
```

AUC is the chance that a random won deal outscores a random lost one (0.5 = a coin flip, 1.0 = perfect).
The command then tries every fit/intent split from 0.0 to 1.0. It only suggests changing the weights in
`icp.json` when another split scores a higher AUC, and it warns when the sample is too small to trust.
The sample `outcomes.csv` is fictional; for real use, score accounts as of the date each deal opened.

Sample output:

```
 #  Account                Industry                   Fit Intent  Score  Tier
 1  IronForge Fabrication  Industrial Manufacturing  90.0   40.6   70.2  A
    Industrial Manufacturing (value 5/5, access 4/5); leadership_change 7d ago (+21); funding 19d ago (+19)
 2  Precision Axle Co      Industrial Manufacturing  90.0   34.9   68.0  B
    Industrial Manufacturing (value 5/5, access 4/5); pain_point 3d ago (+28); hiring_gtm 46d ago (+7)
 ...

Segment                  Accts Tier A    Avg Vertical
Industrial Manufacturing     3      1   61.9       80
B2B SaaS                     2      0   55.3       60
Logistics                    3      0   55.2       64
```

## Using your own data

| File | Columns |
|---|---|
| `data/accounts.csv` | `domain, name, industry, employees, region` |
| `data/signals.csv` | `id, domain, date (YYYY-MM-DD), source, text` |
| `data/icp.json` | verticals with `deal_value` / `accessibility`, `employee_range`, `regions`, `weights` |
| `data/outcomes.csv` | `domain, outcome (won / lost)`, used only by `backtest` |

Point the CLI at your own files with `--accounts`, `--signals` and `--icp`. Accounts and signals join on `domain`.
The sample companies are fictional.

## Project layout

```
signal_scout/
  models.py     data classes + CSV/JSON loaders
  classify.py   keyword-rules and Claude signal classifiers
  scoring.py    fit, intent, tiers, segment roll-up
  ingest.py     RSS / Atom news ingestion with dedupe
  alerts.py     Slack Block Kit alerts
  backtest.py   tier win rates, AUC and weight sweep
  cli.py        command-line entry point (score / ingest / backtest)
data/           sample ICP, accounts, signals and outcomes
tests/          unit tests for every module
```

## Ideas for next steps

- More signal sources: job boards and LinkedIn (via Apify) next to the news feed.
- Push A-tier accounts straight into HubSpot as tasks for the account owner.
- Schedule the pipeline daily with GitHub Actions or n8n.

---

Built by [B. S. S. Srikar](https://linkedin.com/in/srikar-bezwada), a growth and GTM engineering lead.

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

Point the CLI at your own files with `--accounts`, `--signals` and `--icp`. Accounts and signals join on `domain`.
The sample companies are fictional.

## Project layout

```
signal_scout/
  models.py     data classes + CSV/JSON loaders
  classify.py   keyword-rules and Claude signal classifiers
  scoring.py    fit, intent, tiers, segment roll-up
  cli.py        command-line entry point
data/           sample ICP, accounts and signals
tests/          unit tests for scoring and classification
```

## Ideas for next steps

- Pull signals live (RSS, job boards, LinkedIn via Apify) instead of from a CSV.
- Push A-tier accounts to HubSpot or a Slack channel with their reasons attached.
- Backtest the weights against closed-won deals to tune them from data instead of judgement.

---

Built by [B. S. S. Srikar](https://linkedin.com/in/srikar-bezwada), a growth and GTM engineering lead.

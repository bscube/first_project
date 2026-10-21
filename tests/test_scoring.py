from datetime import date

from signal_scout.classify import classify_rules
from signal_scout.models import ICP, Account, Signal, Vertical
from signal_scout.scoring import HALF_LIFE_DAYS, fit_score, intent_score, score_accounts, tier_for

ICP_ = ICP(
    verticals={"Logistics": Vertical(deal_value=5, accessibility=5), "SaaS": Vertical(deal_value=2, accessibility=5)},
    employee_range=(50, 500),
    regions=["UAE"],
)
TODAY = date(2026, 10, 21)


def sig(cat, days_ago, domain="a.example", text=""):
    return Signal(id=f"{cat}{days_ago}", domain=domain, date=date.fromordinal(TODAY.toordinal() - days_ago),
                  source="test", text=text, category=cat)


def test_perfect_fit_scores_100():
    fit, _ = fit_score(Account("a.example", "A", "Logistics", 200, "UAE"), ICP_)
    assert fit == 100


def test_out_of_icp_industry_and_region_lose_fit():
    fit, reasons = fit_score(Account("a.example", "A", "Retail", 200, "Europe"), ICP_)
    assert fit == 30  # only the size component remains
    assert any("outside the ICP" in r for r in reasons)


def test_size_decays_outside_band():
    small, _ = fit_score(Account("a.example", "A", "Logistics", 25, "UAE"), ICP_)
    big, _ = fit_score(Account("a.example", "A", "Logistics", 1000, "UAE"), ICP_)
    assert small == big == 85  # half the size points either side


def test_intent_halves_every_half_life():
    fresh, _ = intent_score([sig("funding", 0)], TODAY)
    old, _ = intent_score([sig("funding", HALF_LIFE_DAYS)], TODAY)
    assert old == fresh / 2


def test_intent_ignores_noise_and_future_signals_and_caps_at_100():
    assert intent_score([sig("noise", 0), sig("funding", -3)], TODAY)[0] == 0
    assert intent_score([sig("funding", 0)] * 10, TODAY)[0] == 100


def test_tiers():
    assert [tier_for(x) for x in (85, 70, 69.9, 50, 10)] == ["A", "A", "B", "B", "C"]


def test_ranking_prefers_fit_plus_intent():
    accounts = [
        Account("hot.example", "Hot", "Logistics", 200, "UAE"),
        Account("cold.example", "Cold", "Logistics", 200, "UAE"),
        Account("off.example", "Off", "SaaS", 200, "UAE"),
    ]
    signals = [sig("funding", 1, "hot.example"), sig("pain_point", 2, "hot.example"), sig("funding", 1, "off.example")]
    ranked = [s.account.domain for s in score_accounts(accounts, signals, ICP_, TODAY)]
    assert ranked[0] == "hot.example"


def test_rules_classifier():
    cases = {
        "Acme raises $10M Series A": "funding",
        "Acme appoints Jo as new CMO": "leadership_change",
        "We're hiring SDRs for our sales team": "hiring_gtm",
        "Our pipeline is dry and we struggle to find buyers": "pain_point",
        "Acme opens new office in Dubai": "expansion",
        "Moving on: switching from Pipedrive to HubSpot": "tech_change",
        "Happy Friday everyone": "noise",
    }
    signals = [Signal(id=str(i), domain="x", date=TODAY, source="t", text=t) for i, t in enumerate(cases)]
    labels = classify_rules(signals)
    assert [labels[str(i)] for i in range(len(cases))] == list(cases.values())

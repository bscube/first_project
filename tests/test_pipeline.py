import csv
from datetime import date

from signal_scout.alerts import slack_payload
from signal_scout.backtest import auc, backtest
from signal_scout.ingest import ingest, merge_into_csv, parse_feed, signals_for
from signal_scout.models import Account, Signal
from signal_scout.scoring import ScoredAccount

ACME = Account("acme.example", "Acme", "Logistics", 200, "UAE")

RSS = b"""<?xml version="1.0"?><rss><channel>
<item><title>Acme raises $20M Series B</title><link>https://n.example/1</link>
  <pubDate>Mon, 19 Oct 2026 08:00:00 GMT</pubDate></item>
<item><title>Acmeville council meets</title><link>https://n.example/2</link>
  <pubDate>Mon, 19 Oct 2026 08:00:00 GMT</pubDate></item>
<item><title>Acme opens new office</title><link>https://n.example/3</link>
  <pubDate>Mon, 01 Jun 2026 08:00:00 GMT</pubDate></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Acme appoints new CRO</title><link href="https://n.example/4"/>
  <updated>2026-10-18T10:00:00Z</updated></entry></feed>"""


def test_parse_rss_and_atom():
    rss = parse_feed(RSS)
    assert rss[0] == {"title": "Acme raises $20M Series B", "link": "https://n.example/1", "date": date(2026, 10, 19)}
    assert parse_feed(ATOM)[0]["date"] == date(2026, 10, 18)


def test_signals_keep_only_whole_name_mentions_after_since():
    sigs = signals_for(ACME, parse_feed(RSS), "news", since=date(2026, 9, 21))
    assert [s.text for s in sigs] == ["Acme raises $20M Series B"]  # not "Acmeville", not June


def test_ingest_survives_a_bad_feed():
    other = Account("b.example", "Beta", "SaaS", 100, "UAE")

    def fetcher(url):
        if "Beta" in url:
            raise OSError("timeout")
        return RSS

    sigs, errors = ingest([ACME, other], since=date(2026, 9, 1), fetcher=fetcher)
    assert len(sigs) == 1 and errors == ["Beta: timeout"]


def test_merge_dedupes_by_id(tmp_path):
    path = tmp_path / "signals.csv"
    s = Signal("rss-1", "acme.example", date(2026, 10, 19), "news", "Acme raises")
    assert merge_into_csv(path, [s, s]) == 1
    assert merge_into_csv(path, [s]) == 0
    with open(path) as f:
        assert len(list(csv.DictReader(f))) == 1


def _scored(domain, fit, intent, tier):
    total = round(0.6 * fit + 0.4 * intent, 1)
    return ScoredAccount(Account(domain, domain, "Logistics", 100, "UAE"), fit, intent, total, tier, ["why"])


def test_slack_payload_only_includes_requested_tiers():
    scored = [_scored("a", 90, 80, "A"), _scored("b", 60, 40, "B")]
    payload = slack_payload(scored)
    assert len(payload["blocks"]) == 2 and "*a*" in payload["blocks"][1]["text"]["text"]
    assert slack_payload([_scored("b", 60, 40, "B")]) is None


def test_auc():
    assert auc([(9, True), (1, False)]) == 1.0
    assert auc([(1, True), (9, False)]) == 0.0
    assert auc([(5, True), (5, False)]) == 0.5
    assert auc([(5, True)]) is None


def test_backtest_finds_the_weight_that_separates_outcomes():
    # Wins have high intent, losses high fit: intent-only weighting should win.
    scored = [_scored("w1", 30, 70, "B"), _scored("w2", 35, 75, "B"),
              _scored("l1", 100, 0, "B"), _scored("l2", 95, 5, "B")]
    outcomes = {"w1": True, "w2": True, "l1": False, "l2": False}
    r = backtest(scored, outcomes, fit_weight=0.6)
    assert r.matched == 4
    best_w, best_auc = r.best
    assert best_auc == 1.0 and best_w < 0.6
    assert r.current_auc < 1.0
    assert r.tiers[1].deals == 4 and r.tiers[1].win_rate == 50.0

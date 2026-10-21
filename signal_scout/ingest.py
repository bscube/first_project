"""Pull fresh signals from RSS / Atom feeds.

By default each account gets a Google News search feed for its name, so a
signal list can be built from nothing but accounts.csv.
"""

from __future__ import annotations

import csv
import hashlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

from .models import Account, Signal

ATOM = "{http://www.w3.org/2005/Atom}"


def google_news_feed(account: Account) -> str:
    query = urllib.parse.quote(f'"{account.name}"')
    return f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).date()  # RSS: RFC 822
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()  # Atom: ISO 8601
    except ValueError:
        return None


def parse_feed(xml: bytes | str) -> list[dict]:
    """Return {title, link, date} for every item in an RSS or Atom document."""
    root = ET.fromstring(xml)
    items = []
    for el in root.iter("item"):
        items.append({
            "title": (el.findtext("title") or "").strip(),
            "link": (el.findtext("link") or "").strip(),
            "date": _parse_date(el.findtext("pubDate")),
        })
    for el in root.iter(f"{ATOM}entry"):
        link = el.find(f"{ATOM}link")
        items.append({
            "title": (el.findtext(f"{ATOM}title") or "").strip(),
            "link": link.get("href", "") if link is not None else "",
            "date": _parse_date(el.findtext(f"{ATOM}updated") or el.findtext(f"{ATOM}published")),
        })
    return items


def fetch(url: str, timeout: float = 15) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "signal-scout/0.2"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _mentions(account: Account, title: str) -> bool:
    # A search feed returns loose matches; keep only items that name the company.
    return re.search(rf"\b{re.escape(account.name.lower())}\b", title.lower()) is not None


def signals_for(account: Account, items: list[dict], source: str, since: date | None) -> list[Signal]:
    out = []
    for item in items:
        if not item["date"] or not _mentions(account, item["title"]):
            continue
        if since and item["date"] < since:
            continue
        sid = "rss-" + hashlib.sha1((item["link"] or item["title"]).encode()).hexdigest()[:10]
        out.append(Signal(id=sid, domain=account.domain, date=item["date"], source=source, text=item["title"]))
    return out


def ingest(accounts: list[Account], since: date | None = None, fetcher=fetch) -> tuple[list[Signal], list[str]]:
    """Fetch every account's feed. Returns (signals, errors); one bad feed never stops the run."""
    signals, errors = [], []
    for a in accounts:
        try:
            items = parse_feed(fetcher(google_news_feed(a)))
        except Exception as e:  # network, HTTP or malformed XML
            errors.append(f"{a.name}: {e}")
            continue
        signals.extend(signals_for(a, items, "news", since))
    return signals, errors


def merge_into_csv(path: str | Path, new: list[Signal]) -> int:
    """Append signals whose id isn't already in the CSV. Returns how many were added."""
    path = Path(path)
    existing = set()
    if path.exists():
        with open(path, newline="") as f:
            existing = {row["id"] for row in csv.DictReader(f)}
    fresh = [s for s in {s.id: s for s in new}.values() if s.id not in existing]
    write_header = not path.exists()
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(["id", "domain", "date", "source", "text"])
        for s in fresh:
            w.writerow([s.id, s.domain, s.date.isoformat(), s.source, s.text])
    return len(fresh)

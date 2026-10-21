"""Send the accounts worth acting on today to a Slack channel."""

from __future__ import annotations

import json
import urllib.request

from .scoring import ScoredAccount


def slack_payload(scored: list[ScoredAccount], tiers: tuple[str, ...] = ("A",), limit: int = 10) -> dict | None:
    picks = [s for s in scored if s.tier in tiers][:limit]
    if not picks:
        return None
    blocks = [{
        "type": "header",
        "text": {"type": "plain_text", "text": f"Signal Scout: {len(picks)} account(s) to work today"},
    }]
    for s in picks:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (f"*{s.account.name}* ({s.account.domain}): tier {s.tier}, score {s.total}\n"
                         f"Fit {s.fit} | Intent {s.intent}\n• " + "\n• ".join(s.reasons)),
            },
        })
    # `text` is the fallback shown in notifications.
    return {"text": f"{len(picks)} tier-{'/'.join(tiers)} accounts from Signal Scout", "blocks": blocks}


def post_to_slack(webhook_url: str, payload: dict, timeout: float = 15) -> None:
    req = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Slack returned {resp.status}")

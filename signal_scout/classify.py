"""Turn raw signal text into a category.

Two classifiers share one interface: a keyword baseline that needs nothing,
and a Claude classifier used when ANTHROPIC_API_KEY (or another Anthropic
credential) is available.
"""

from __future__ import annotations

import json
import re

from .models import Signal

CATEGORIES = {
    "funding": "Raised money or announced revenue milestones",
    "hiring_gtm": "Hiring sales, marketing, RevOps or growth roles",
    "leadership_change": "New CXO / VP in a buying role",
    "expansion": "New market, office, product line or plant",
    "tech_change": "Adopting, replacing or evaluating relevant tools",
    "pain_point": "Publicly describing the problem we solve",
    "noise": "Nothing a seller should act on",
}

_RULES = [
    ("funding", r"\b(raise[sd]?|series [a-e]|seed round|funding|investment|backed by)\b"),
    ("leadership_change", r"\b(appoint(s|ed)?|joins as|new (cmo|cro|ceo|vp|head)|named .*(chief|vp))\b"),
    ("hiring_gtm", r"\b(hiring|job opening|we're looking for).*(sales|sdr|bdr|marketing|growth|revops|demand)"),
    ("pain_point", r"\b(struggl|frustrat|can't find|hard to|pipeline is|no leads|losing deals|manual)\w*"),
    ("expansion", r"\b(expand|opens? (a )?new|launch(es|ed)? in|entering|new plant|new office)\w*"),
    ("tech_change", r"\b(migrat|switch(ed|ing)? (from|to)|evaluating|rolled out|implement)\w*"),
]


def classify_rules(signals: list[Signal]) -> dict[str, str]:
    out = {}
    for s in signals:
        text = s.text.lower()
        out[s.id] = next((cat for cat, pat in _RULES if re.search(pat, text)), "noise")
    return out


_SCHEMA = {
    "type": "object",
    "properties": {
        "labels": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "category": {"type": "string", "enum": list(CATEGORIES)},
                },
                "required": ["id", "category"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["labels"],
    "additionalProperties": False,
}


def classify_claude(signals: list[Signal], model: str = "claude-opus-5-5", batch_size: int = 40) -> dict[str, str]:
    import anthropic

    client = anthropic.Anthropic()
    guide = "\n".join(f"- {k}: {v}" for k, v in CATEGORIES.items())
    out: dict[str, str] = {}

    for i in range(0, len(signals), batch_size):
        batch = signals[i : i + batch_size]
        items = "\n".join(json.dumps({"id": s.id, "source": s.source, "text": s.text}) for s in batch)
        response = client.beta.messages.create(
            model=model,
            max_tokens=4096,
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": _SCHEMA}},
            # On a safety decline the API retries on a fallback model within the same call.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=(
                "You label B2B buying signals for an outbound team. Pick the single category "
                "a seller would act on; use noise when there is nothing to act on.\n\n" + guide
            ),
            messages=[{"role": "user", "content": f"Label every signal below.\n\n{items}"}],
        )
        if response.stop_reason == "refusal":
            out.update(classify_rules(batch))
            continue
        text = next(b.text for b in response.content if b.type == "text")
        out.update({row["id"]: row["category"] for row in json.loads(text)["labels"]})

    # Anything the model skipped gets the rules label rather than silently vanishing.
    missing = [s for s in signals if s.id not in out]
    out.update(classify_rules(missing))
    return out


def classify(signals: list[Signal], use_llm: bool) -> list[Signal]:
    labels = classify_claude(signals) if use_llm else classify_rules(signals)
    for s in signals:
        s.category = labels[s.id]
    return signals

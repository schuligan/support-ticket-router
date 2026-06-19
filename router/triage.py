"""Auto-triage: classify category, priority, intent and extract fields.

Two paths:

* **LLM path** (key present) — one structured Claude call returns the triage.
* **Mock path** (no key) — deterministic keyword heuristics produce the same
  shape so the demo and tests run offline. The mock banner is printed once.
"""

from __future__ import annotations

import re
from typing import Any

from .config import Config
from .llm import MOCK_BANNER, LLMUnavailable, call_json
from .models import Category, InboundMessage, Priority, Triage

# JSON schema the LLM must satisfy.
_TRIAGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "category": {
            "type": "string",
            "enum": [c.value for c in Category],
        },
        "priority": {
            "type": "string",
            "enum": [p.value for p in Priority],
        },
        "intent": {"type": "string"},
        "customer": {"type": "string"},
        "product_area": {"type": "string"},
        "summary": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": [
        "category",
        "priority",
        "intent",
        "customer",
        "product_area",
        "summary",
        "confidence",
    ],
    "additionalProperties": False,
}

_SYSTEM = (
    "You are a support triage agent for the SaaS product 'Acme Cloud'. "
    "Classify the inbound message into a category, priority, and intent, and "
    "extract the customer name, the affected product area, and a one-sentence "
    "summary. Priority must reflect business impact: outages and data loss are "
    "urgent; blocked workflows are high; routine questions are normal; "
    "nice-to-haves are low. Return JSON only."
)


# --- Mock-path keyword tables ------------------------------------------------

_CATEGORY_KEYWORDS: list[tuple[Category, tuple[str, ...]]] = [
    (Category.OUTAGE, ("down", "503", "outage", "502", "not responding")),
    (Category.BILLING, ("invoice", "charge", "billed", "refund", "payment")),
    (Category.BUG, ("error", "401", "broken", "bug", "fails", "throwing")),
    (Category.FEATURE_REQUEST, ("feature", "idea", "would love", "nice-to-have")),
    (Category.ACCOUNT, ("notification email", "account settings", "profile")),
    (Category.HOW_TO, ("how do i", "where do i", "how to", "where is", "point me")),
]

# "urgent" is matched as a whole word so "not urgent" does not trigger it.
_URGENT_HINTS = ("down", "503", "outage", "immediately", "all of our customers")
_HIGH_HINTS = (
    "blocked", "401", "can't", "cannot", "broken", "double charged", "refund",
)
_LOW_HINTS = ("nice-to-have", "not urgent", "idea", "would love", "feature")


def _mock_category(text: str) -> Category:
    for category, words in _CATEGORY_KEYWORDS:
        if any(w in text for w in words):
            return category
    return Category.OTHER


def _has_urgent_word(text: str) -> bool:
    # Whole-word "urgent" so that "not urgent" does not count.
    return bool(re.search(r"\burgent\b", text)) and "not urgent" not in text


def _mock_priority(text: str, category: Category) -> Priority:
    # Low/feature intent wins first so a stray "urgent" substring can't override
    # an explicit nice-to-have.
    if category is Category.FEATURE_REQUEST or any(w in text for w in _LOW_HINTS):
        return Priority.LOW
    if (
        category is Category.OUTAGE
        or _has_urgent_word(text)
        or any(w in text for w in _URGENT_HINTS)
    ):
        return Priority.URGENT
    if any(w in text for w in _HIGH_HINTS) or category in (
        Category.BUG,
        Category.BILLING,
    ):
        return Priority.HIGH
    return Priority.NORMAL


def _mock_triage(msg: InboundMessage) -> Triage:
    text = f"{msg.subject}\n{msg.body}".lower()
    category = _mock_category(text)
    priority = _mock_priority(text, category)
    summary = msg.subject.strip() or msg.body.strip()[:80]
    return Triage(
        category=category,
        priority=priority,
        intent=f"{category.value}_request",
        customer=msg.sender_name,
        product_area="Acme Cloud",
        summary=summary,
        confidence=0.6,
        source="mock",
    )


def _from_llm_dict(d: dict[str, Any]) -> Triage:
    return Triage(
        category=Category(d["category"]),
        priority=Priority(d["priority"]),
        intent=str(d["intent"]),
        customer=str(d["customer"]),
        product_area=str(d["product_area"]),
        summary=str(d["summary"]),
        confidence=float(d["confidence"]),
        source="llm",
    )


def triage_message(msg: InboundMessage, config: Config) -> Triage:
    """Triage a single message via Claude or the deterministic mock."""
    if config.mock_mode:
        return _mock_triage(msg)
    user_content = (
        f"Channel: {msg.channel.value}\n"
        f"From: {msg.sender_name} <{msg.sender_email}>\n"
        f"Subject: {msg.subject}\n\n{msg.body}"
    )
    try:
        result = call_json(
            api_key=config.api_key or "",
            model_id=config.model_id,
            system=_SYSTEM,
            user_content=user_content,
            schema=_TRIAGE_SCHEMA,
        )
        return _from_llm_dict(result)
    except (LLMUnavailable, KeyError, ValueError):
        # Never fail the pipeline on an LLM hiccup — fall back to the mock.
        return _mock_triage(msg)


def banner_if_mock(config: Config) -> str | None:
    """Return the mock banner string when running offline, else ``None``."""
    return MOCK_BANNER if config.mock_mode else None

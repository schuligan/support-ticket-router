"""Domain models for the support ticket router.

Plain dataclasses with explicit serialization helpers. Kept dependency-light so
the mock path and the tests have zero external requirements beyond pydantic
(used for validation at the ingest boundary).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class Channel(StrEnum):
    """Where an inbound message originated."""

    EMAIL = "email"
    SLACK = "slack"


class Category(StrEnum):
    """Coarse triage category for an inbound message."""

    BILLING = "billing"
    BUG = "bug"
    HOW_TO = "how_to"
    ACCOUNT = "account"
    OUTAGE = "outage"
    FEATURE_REQUEST = "feature_request"
    OTHER = "other"


class Priority(StrEnum):
    """SLA-bearing priority. Ordering matters for escalation policy."""

    URGENT = "urgent"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class TicketStatus(StrEnum):
    """Lifecycle states for a ticket in the mock store."""

    OPEN = "open"
    RESOLVED = "resolved"
    AWAITING_HUMAN = "awaiting_human"
    ESCALATED = "escalated"


# SLA response windows per priority, in minutes. These define when a ticket is
# considered breached if still unresolved / unhandled.
SLA_MINUTES: dict[Priority, int] = {
    Priority.URGENT: 60,
    Priority.HIGH: 240,
    Priority.NORMAL: 1440,
    Priority.LOW: 4320,
}


# ---------------------------------------------------------------------------
# Inbound message
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InboundMessage:
    """A normalized inbound support message from email or Slack."""

    id: str
    channel: Channel
    sender_name: str
    sender_email: str
    subject: str
    body: str
    received_at: datetime

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["channel"] = self.channel.value
        d["received_at"] = self.received_at.isoformat()
        return d


# ---------------------------------------------------------------------------
# Triage result
# ---------------------------------------------------------------------------


@dataclass
class Triage:
    """Structured triage output for a message."""

    category: Category
    priority: Priority
    intent: str
    customer: str
    product_area: str
    summary: str
    confidence: float
    source: str  # "llm" or "mock"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["category"] = self.category.value
        d["priority"] = self.priority.value
        return d


# ---------------------------------------------------------------------------
# Resolution attempt
# ---------------------------------------------------------------------------


@dataclass
class Resolution:
    """Outcome of the auto-resolution attempt against the KB."""

    resolved: bool
    confidence: float
    kb_article_id: str | None
    draft_reply: str | None
    handoff_reason: str | None
    source: str  # "llm" or "mock"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Ticket
# ---------------------------------------------------------------------------


@dataclass
class Ticket:
    """A ticket in the mock ("Jira-style") store."""

    id: str
    message_id: str
    channel: Channel
    customer: str
    sender_email: str
    subject: str
    category: Category
    priority: Priority
    status: TicketStatus
    summary: str
    created_at: datetime
    sla_due_at: datetime
    resolved_at: datetime | None = None
    escalated_at: datetime | None = None
    kb_article_id: str | None = None
    draft_reply: str | None = None
    handoff_reason: str | None = None
    history: list[dict[str, Any]] = field(default_factory=list)

    @staticmethod
    def sla_due(created_at: datetime, priority: Priority) -> datetime:
        return created_at + timedelta(minutes=SLA_MINUTES[priority])

    def is_breached(self, now: datetime) -> bool:
        """Open/awaiting tickets past their SLA window are breached.

        Resolved and already-escalated tickets are never (re)flagged.
        """
        if self.status in (TicketStatus.RESOLVED, TicketStatus.ESCALATED):
            return False
        return now >= self.sla_due_at

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["channel"] = self.channel.value
        d["category"] = self.category.value
        d["priority"] = self.priority.value
        d["status"] = self.status.value
        d["created_at"] = self.created_at.isoformat()
        d["sla_due_at"] = self.sla_due_at.isoformat()
        d["resolved_at"] = self.resolved_at.isoformat() if self.resolved_at else None
        d["escalated_at"] = (
            self.escalated_at.isoformat() if self.escalated_at else None
        )
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Ticket:
        return cls(
            id=d["id"],
            message_id=d["message_id"],
            channel=Channel(d["channel"]),
            customer=d["customer"],
            sender_email=d["sender_email"],
            subject=d["subject"],
            category=Category(d["category"]),
            priority=Priority(d["priority"]),
            status=TicketStatus(d["status"]),
            summary=d["summary"],
            created_at=_parse_dt(d["created_at"]),
            sla_due_at=_parse_dt(d["sla_due_at"]),
            resolved_at=_parse_dt(d["resolved_at"]) if d.get("resolved_at") else None,
            escalated_at=(
                _parse_dt(d["escalated_at"]) if d.get("escalated_at") else None
            ),
            kb_article_id=d.get("kb_article_id"),
            draft_reply=d.get("draft_reply"),
            handoff_reason=d.get("handoff_reason"),
            history=d.get("history", []),
        )


def _parse_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt

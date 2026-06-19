"""SLA reminder + escalation policy.

Policy
------
Every ticket carries an SLA window derived from its priority (see
``models.SLA_MINUTES``):

    urgent  -> 60 minutes
    high    -> 4 hours
    normal  -> 24 hours
    low     -> 72 hours

A ticket that is still ``open`` or ``awaiting_human`` when its SLA window
elapses is **escalated**: its status becomes ``escalated`` and an audit entry is
written. Resolved tickets and already-escalated tickets are never re-flagged.
"""

from __future__ import annotations

from datetime import datetime

from .audit import AuditLog
from .models import Ticket, TicketStatus
from .store import TicketStore


def find_breached(store: TicketStore, now: datetime) -> list[Ticket]:
    """Tickets past their SLA window that are not yet resolved/escalated."""
    return [t for t in store.all() if t.is_breached(now)]


def escalate(
    store: TicketStore, audit: AuditLog, now: datetime
) -> list[Ticket]:
    """Escalate all breached tickets and return the ones that changed."""
    escalated: list[Ticket] = []
    for ticket in find_breached(store, now):
        overdue_min = int((now - ticket.sla_due_at).total_seconds() // 60)
        ticket.status = TicketStatus.ESCALATED
        ticket.escalated_at = now
        ticket.history.append(
            {
                "ts": now.isoformat(),
                "event": "escalated",
                "overdue_minutes": overdue_min,
            }
        )
        store.update(ticket)
        audit.record(
            "escalate",
            now,
            ticket_id=ticket.id,
            priority=ticket.priority.value,
            overdue_minutes=overdue_min,
        )
        escalated.append(ticket)
    return escalated

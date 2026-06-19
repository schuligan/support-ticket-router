"""SLA escalation triggers, driven by the injectable clock."""

from __future__ import annotations

from router.escalation import escalate, find_breached
from router.models import Priority, TicketStatus
from router.pipeline import process_message

from .helpers import make_message


def _open_unresolved_high_ticket(config, store, audit, articles, clock):
    # A billing double-charge triages HIGH (4h SLA) and hands off (no KB resolve
    # at full confidence for this phrasing), so it stays open and can breach.
    msg = make_message(
        subject="Need a manual refund decision",
        body="I was billed twice but the amounts differ slightly; please review.",
    )
    result = process_message(
        msg, store=store, audit=audit, articles=articles, config=config, clock=clock
    )
    return result.ticket


def test_no_escalation_before_sla(config, store, audit, articles, clock):
    ticket = _open_unresolved_high_ticket(config, store, audit, articles, clock)
    assert ticket.status is TicketStatus.AWAITING_HUMAN
    # 1 hour in, a 4h-SLA ticket is not yet breached.
    clock.advance(minutes=60)
    assert find_breached(store, clock.now()) == []
    changed = escalate(store, audit, clock.now())
    assert changed == []


def test_escalates_after_sla_window(config, store, audit, articles, clock):
    ticket = _open_unresolved_high_ticket(config, store, audit, articles, clock)
    assert ticket.priority is Priority.HIGH
    # Advance past the 4h HIGH SLA window.
    clock.advance(minutes=241)
    breached = find_breached(store, clock.now())
    assert ticket.id in [t.id for t in breached]
    changed = escalate(store, audit, clock.now())
    assert len(changed) == 1
    assert store.get(ticket.id).status is TicketStatus.ESCALATED


def test_resolved_tickets_never_escalate(config, store, audit, articles, clock):
    msg = make_message(
        subject="Reset API key",
        body="where do I regenerate my api key credentials in settings",
    )
    result = process_message(
        msg, store=store, audit=audit, articles=articles, config=config, clock=clock
    )
    assert result.ticket.status is TicketStatus.RESOLVED
    clock.advance(days=30)
    assert escalate(store, audit, clock.now()) == []


def test_escalation_is_audited(config, store, audit, articles, clock):
    _open_unresolved_high_ticket(config, store, audit, articles, clock)
    clock.advance(minutes=300)
    escalate(store, audit, clock.now())
    assert any(e["action"] == "escalate" for e in audit.read_all())
